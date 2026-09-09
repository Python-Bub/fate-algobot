"""Online neural ensemble for paper/live adaptation from realized trade moves.

Implements a small set of opt-in PyTorch models:
- LSTM
- CNN (1D temporal conv)
- GA-LSTM (gated-attention LSTM)
- CNN-BiLSTM
- DQN (Q-network over {SHORT, HOLD, LONG})

The ensemble is trained incrementally from replay entries persisted to
`data/online_learning/neural_replay.jsonl` and exposes a single averaged
`p_up` estimate for blending into existing decision logic.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from utils import log

try:  # Optional runtime dependency.
    import torch
    from torch import nn
    from torch.nn import functional as F

    _TORCH_OK = True
except Exception:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    _TORCH_OK = False


REPLAY_PATH = Path(os.getenv("NEURAL_REPLAY_FILE", "data/online_learning/neural_replay.jsonl"))
MODEL_DIR = Path(os.getenv("NEURAL_MODEL_DIR", "models/neural_ensemble"))

# Stable feature order for all models.
FEATURE_COLS = [
    "p_up_base",
    "p_short_model",
    "p_long_model",
    "execution_confidence",
    "sentiment",
    "news_factor",
    "transcript_factor",
    "volume_ratio",
    "momentum_5d",
    "rs_spy",
    "dip_signal",
    "atr_14",
    "alpha_proxy_20",
]

ACTION_TO_IDX = {"SHORT": 0, "HOLD": 1, "LONG": 2}
IDX_TO_ACTION = {0: "SHORT", 1: "HOLD", 2: "LONG"}
BINARY_MODEL_KEYS = ("lstm", "cnn", "ga_lstm", "cnn_bilstm", "transformer")
ALL_MODEL_KEYS = (*BINARY_MODEL_KEYS, "dqn")
GLOBAL_TICKER = "_GLOBAL_"
_TORCH_MODEL_CACHE: dict[str, tuple] = {}

# Fill / fortress state dicts use different keys than FEATURE_COLS. Map them
# so replay is not a wall of zeros (that killed online neural learning).
_FEAT_ALIASES: dict[str, tuple[str, ...]] = {
    "p_up_base": ("p_up_base", "p_up", "p_long_model", "p_long"),
    "p_short_model": ("p_short_model", "p_short"),
    "p_long_model": ("p_long_model", "p_long", "p_up", "p_up_base"),
    "execution_confidence": ("execution_confidence", "exec_conf", "exec_c"),
    "sentiment": ("sentiment", "sentiment_impulse", "sentiment_intensity"),
    "news_factor": ("news_factor", "nf_f"),
    "transcript_factor": ("transcript_factor",),
    "volume_ratio": ("volume_ratio", "vol_regime_ratio"),
    "momentum_5d": ("momentum_5d", "mom_5d", "mom_20"),
    "rs_spy": ("rs_spy", "beta_proxy_60"),
    "dip_signal": ("dip_signal",),
    "atr_14": ("atr_14",),
    "alpha_proxy_20": ("alpha_proxy_20",),
}


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def use_neural_ensemble() -> bool:
    return _TORCH_OK and _b("USE_NEURAL_ENSEMBLE", True)


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _safe_float(v, default: float = 0.0) -> float:
    try:
        x = float(v)
        if np.isnan(x) or np.isinf(x):
            return default
        return x
    except Exception:
        return default


def _feat(state: dict, col: str) -> float:
    st = state or {}
    for k in _FEAT_ALIASES.get(col, (col,)):
        if k in st and st.get(k) is not None:
            return _safe_float(st.get(k), 0.0)
    return 0.0


def _state_vec(state: dict) -> np.ndarray:
    return np.asarray([_feat(state, c) for c in FEATURE_COLS], dtype=np.float32)


@dataclass
class NeuralTrainReport:
    ticker: str
    applied: bool
    reason: str
    n_samples: int
    lstm_loss: float = 0.0
    cnn_loss: float = 0.0
    ga_lstm_loss: float = 0.0
    cnn_bilstm_loss: float = 0.0
    transformer_loss: float = 0.0
    dqn_loss: float = 0.0


class _LSTMHead(nn.Module):
    def __init__(self, n_features: int, hidden: int = 64, num_layers: int = 2) -> None:
        super().__init__()
        layers = max(1, int(num_layers))
        drop = 0.2 if layers > 1 else 0.0
        self.lstm = nn.LSTM(n_features, hidden, num_layers=layers, batch_first=True, dropout=drop)
        self.fc = nn.Sequential(nn.Linear(hidden, max(16, hidden // 2)), nn.ReLU(), nn.Linear(max(16, hidden // 2), 1))

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :]).squeeze(-1)


class _CNNHead(nn.Module):
    def __init__(self, n_features: int, channels: int = 64) -> None:
        super().__init__()
        ch = max(16, int(channels))
        self.c1 = nn.Conv1d(n_features, ch, kernel_size=3, padding=1)
        self.c2 = nn.Conv1d(ch, ch, kernel_size=3, padding=1)
        self.fc = nn.Sequential(nn.Linear(ch, max(16, ch // 2)), nn.ReLU(), nn.Linear(max(16, ch // 2), 1))

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        # [B,T,F] -> [B,F,T]
        z = x.transpose(1, 2)
        z = F.relu(self.c1(z))
        z = F.relu(self.c2(z))
        z = z.mean(dim=-1)
        return self.fc(z).squeeze(-1)


class _GALSTMHead(nn.Module):
    """Gated-attention LSTM (GA-LSTM)."""

    def __init__(self, n_features: int, hidden: int = 64, num_layers: int = 1) -> None:
        super().__init__()
        layers = max(1, int(num_layers))
        drop = 0.2 if layers > 1 else 0.0
        self.lstm = nn.LSTM(n_features, hidden, num_layers=layers, batch_first=True, dropout=drop)
        self.attn = nn.Linear(hidden, 1)
        self.gate = nn.Sequential(nn.Linear(hidden, hidden), nn.Sigmoid())
        self.fc = nn.Sequential(nn.Linear(hidden, max(16, hidden // 2)), nn.ReLU(), nn.Linear(max(16, hidden // 2), 1))

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        out, _ = self.lstm(x)  # [B,T,H]
        w = torch.softmax(self.attn(out).squeeze(-1), dim=-1).unsqueeze(-1)  # [B,T,1]
        ctx = (out * w).sum(dim=1)  # [B,H]
        g = self.gate(ctx)
        ctx = ctx * g
        return self.fc(ctx).squeeze(-1)


class _CNNBiLSTMHead(nn.Module):
    def __init__(self, n_features: int, hidden: int = 48, channels: int = 48, num_layers: int = 1) -> None:
        super().__init__()
        ch = max(16, int(channels))
        hid = max(16, int(hidden))
        layers = max(1, int(num_layers))
        drop = 0.2 if layers > 1 else 0.0
        self.conv = nn.Conv1d(n_features, ch, kernel_size=3, padding=1)
        self.bilstm = nn.LSTM(ch, hid, num_layers=layers, batch_first=True, bidirectional=True, dropout=drop)
        self.fc = nn.Sequential(nn.Linear(hid * 2, max(16, hid)), nn.ReLU(), nn.Linear(max(16, hid), 1))

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        z = F.relu(self.conv(x.transpose(1, 2))).transpose(1, 2)  # [B,T,48]
        out, _ = self.bilstm(z)  # [B,T,2H]
        return self.fc(out[:, -1, :]).squeeze(-1)


class _DQN(nn.Module):
    def __init__(self, n_features: int, width: int = 64) -> None:
        super().__init__()
        w = max(16, int(width))
        self.net = nn.Sequential(
            nn.Linear(n_features, w),
            nn.ReLU(),
            nn.Linear(w, w),
            nn.ReLU(),
            nn.Linear(w, 3),
        )

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        return self.net(x)


class _TransformerHead(nn.Module):
    """Temporal encoder — extra vote, does not replace LSTM/CNN checkpoints."""

    def __init__(
        self,
        n_features: int,
        d_model: int = 32,
        nhead: int = 4,
        nlayers: int = 2,
        ff: int = 64,
    ) -> None:
        super().__init__()
        d_model = max(16, int(d_model))
        nhead = max(1, int(nhead))
        if d_model % nhead != 0:
            nhead = 4 if d_model % 4 == 0 else 1
        ff = max(d_model, int(ff))
        self.proj = nn.Linear(n_features, d_model)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=ff,
            dropout=0.1,
            batch_first=True,
        )
        self.enc = nn.TransformerEncoder(layer, num_layers=max(1, int(nlayers)))
        self.fc = nn.Sequential(nn.Linear(d_model, max(16, d_model // 2)), nn.ReLU(), nn.Linear(max(16, d_model // 2), 1))

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        z = self.enc(self.proj(x))
        return self.fc(z[:, -1, :]).squeeze(-1)


def _train_arch() -> dict:
    """Capacity for *new* checkpoints. Missing keys on disk stay at legacy sizes."""
    return {
        "lstm_hidden": _i("NEURAL_LSTM_HIDDEN", 128),
        "lstm_layers": _i("NEURAL_LSTM_LAYERS", 3),
        "cnn_channels": _i("NEURAL_CNN_CHANNELS", 96),
        "ga_hidden": _i("NEURAL_GA_HIDDEN", 128),
        "ga_layers": _i("NEURAL_GA_LAYERS", 2),
        "bilstm_hidden": _i("NEURAL_BILSTM_HIDDEN", 64),
        "bilstm_channels": _i("NEURAL_BILSTM_CHANNELS", 64),
        "bilstm_layers": _i("NEURAL_BILSTM_LAYERS", 2),
        "tf_d_model": _i("NEURAL_TF_D_MODEL", 64),
        "tf_nhead": _i("NEURAL_TF_NHEAD", 4),
        "tf_nlayers": _i("NEURAL_TF_NLAYERS", 3),
        "tf_ff": _i("NEURAL_TF_FF", 128),
        "dqn_width": _i("NEURAL_DQN_WIDTH", 128),
    }


def _make_head(key: str, n_feat: int, arch: dict | None = None) -> "nn.Module":
    a = arch or {}
    if key == "lstm":
        return _LSTMHead(
            n_feat,
            hidden=int(a.get("lstm_hidden", 64)),
            num_layers=int(a.get("lstm_layers", 2)),
        )
    if key == "cnn":
        return _CNNHead(n_feat, channels=int(a.get("cnn_channels", 64)))
    if key == "ga_lstm":
        return _GALSTMHead(
            n_feat,
            hidden=int(a.get("ga_hidden", 64)),
            num_layers=int(a.get("ga_layers", 1)),
        )
    if key == "cnn_bilstm":
        return _CNNBiLSTMHead(
            n_feat,
            hidden=int(a.get("bilstm_hidden", 48)),
            channels=int(a.get("bilstm_channels", 48)),
            num_layers=int(a.get("bilstm_layers", 1)),
        )
    if key == "transformer":
        return _TransformerHead(
            n_feat,
            d_model=int(a.get("tf_d_model", 32)),
            nhead=int(a.get("tf_nhead", 4)),
            nlayers=int(a.get("tf_nlayers", 2)),
            ff=int(a.get("tf_ff", 64)),
        )
    if key == "dqn":
        return _DQN(n_feat, width=int(a.get("dqn_width", 64)))
    raise KeyError(key)


# Share replay + checkpoints across class-share tickers (Alpaca vs Yahoo naming).
_NEURAL_SYMBOL_SIBLINGS: dict[str, tuple[str, ...]] = {
    "GOOG": ("GOOGL",),
    "GOOGL": ("GOOG",),
}


def _neural_symbols(ticker: str) -> tuple[str, ...]:
    t = ticker.strip().upper()
    sibs = _NEURAL_SYMBOL_SIBLINGS.get(t, ())
    return tuple(dict.fromkeys((t, *sibs)))


def _checkpoint_path(ticker: str, key: str) -> Path:
    """Write path — never GLOBAL. Inference uses `_model_paths` fallbacks."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    return MODEL_DIR / f"{ticker.strip().upper()}_{key}.pt"


def _model_paths(ticker: str) -> dict[str, Path]:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    keys = ALL_MODEL_KEYS

    def _pick_path(sym: str, key: str) -> Path:
        return MODEL_DIR / f"{sym.upper()}_{key}.pt"

    out: dict[str, Path] = {}
    for key in keys:
        chosen = _pick_path(ticker, key)
        for sym in (*_neural_symbols(ticker), GLOBAL_TICKER):
            alt = _pick_path(sym, key)
            if alt.is_file():
                chosen = alt
                break
        out[key] = chosen
    return out


def _load_replay(ticker: str | None = None, max_samples: int = 8000) -> list[dict]:
    if not REPLAY_PATH.is_file():
        return []
    out: list[dict] = []
    sym_set: set[str] | None = None
    if ticker:
        sym_set = set(_neural_symbols(ticker))
    try:
        with open(REPLAY_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    j = json.loads(line)
                except Exception:
                    continue
                if sym_set and str(j.get("ticker", "")).upper() not in sym_set:
                    continue
                out.append(j)
    except Exception as e:
        log.warning("[NEURAL] replay load failed: %s", e)
        return []
    if len(out) > max_samples:
        out = out[-max_samples:]
    out.sort(key=lambda x: _safe_float(x.get("ts", 0.0), 0.0))
    return out


def record_neural_experience(
    ticker: str,
    state: dict,
    action: str,
    realized_return: float,
    reward: float,
) -> None:
    if not use_neural_ensemble():
        return
    row = {
        "ts": time.time(),
        "ticker": ticker.upper(),
        "state": {k: _feat(state, k) for k in FEATURE_COLS},
        "action": action.upper(),
        "realized_return": _safe_float(realized_return, 0.0),
        "reward": _safe_float(reward, 0.0),
    }
    REPLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPLAY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _state_from_report_row(r: dict) -> dict:
    return {
        "p_up_base": _safe_float(r.get("p_up", 0.5), 0.5),
        "p_short_model": _safe_float(r.get("p_short_model", r.get("p_down", 0.5)), 0.5),
        "p_long_model": _safe_float(r.get("p_long_model", r.get("p_up", 0.5)), 0.5),
        "execution_confidence": _safe_float(r.get("execution_confidence", 0.5), 0.5),
        "sentiment": _safe_float(r.get("sentiment", 0.0), 0.0),
        "news_factor": _safe_float(r.get("news_factor", 0.0), 0.0),
        "transcript_factor": _safe_float(r.get("transcript_factor", 0.0), 0.0),
        "volume_ratio": _safe_float(r.get("volume_ratio", 1.0), 1.0),
        "momentum_5d": _safe_float(r.get("momentum_5d", 0.0), 0.0),
        "rs_spy": _safe_float(r.get("rs_spy", 1.0), 1.0),
        "dip_signal": _safe_float(r.get("dip_signal", 0.0), 0.0),
        "atr_14": _safe_float(r.get("atr_14", 1.0), 1.0),
        "alpha_proxy_20": _safe_float(r.get("rs_spy", 1.0), 1.0) - 1.0,
    }


def bootstrap_replay_from_reports(max_files: int = 14) -> int:
    """Seed replay from historical `reports/paper_sim_*.json` moves."""
    if not use_neural_ensemble():
        return 0
    rep_dir = Path("reports")
    if not rep_dir.is_dir():
        return 0
    files = sorted(rep_dir.glob("paper_sim_*.json"))[-max_files:]
    added = 0
    for fp in files:
        try:
            j = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows = j.get("rows", [])
        if not isinstance(rows, list):
            continue
        for r in rows:
            if not isinstance(r, dict):
                continue
            act = str(r.get("action", "")).upper()
            if act not in ("BUY", "SHORT"):
                continue
            side = "LONG" if act == "BUY" else "SHORT"
            state = r.get("online_state") if isinstance(r.get("online_state"), dict) else _state_from_report_row(r)
            rr = _safe_float(r.get("fwd_1d_return", 0.0), 0.0)
            reward = rr if side == "LONG" else -rr
            record_neural_experience(
                ticker=str(r.get("ticker", "")),
                state=state,
                action=side,
                realized_return=rr,
                reward=reward,
            )
            added += 1
    return added


def _build_windows(rows: list[dict], seq_len: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return seq_X, y_up, dqn_state, dqn_target_action."""
    if len(rows) < seq_len + 1:
        z_seq = np.empty((0, seq_len, len(FEATURE_COLS)), dtype=np.float32)
        z_vec = np.empty((0, len(FEATURE_COLS)), dtype=np.float32)
        z_y = np.empty((0,), dtype=np.float32)
        z_a = np.empty((0,), dtype=np.int64)
        return z_seq, z_y, z_vec, z_a

    feats = np.asarray([_state_vec(r.get("state", {})) for r in rows], dtype=np.float32)
    # Long-direction label: up move is positive.
    y_up = np.asarray(
        [1.0 if _safe_float(r.get("realized_return", 0.0), 0.0) > 0 else 0.0 for r in rows],
        dtype=np.float32,
    )
    acts = np.asarray([ACTION_TO_IDX.get(str(r.get("action", "HOLD")).upper(), 1) for r in rows], dtype=np.int64)
    rews = np.asarray([_safe_float(r.get("reward", 0.0), 0.0) for r in rows], dtype=np.float32)

    seqs: list[np.ndarray] = []
    ys: list[float] = []
    dqn_states: list[np.ndarray] = []
    dqn_actions: list[int] = []
    dqn_targets: list[np.ndarray] = []

    gamma = _f("NEURAL_DQN_GAMMA", 0.95)
    for i in range(seq_len - 1, len(rows) - 1):
        seq = feats[i - seq_len + 1 : i + 1]
        seqs.append(seq)
        ys.append(float(y_up[i]))
        s = feats[i]
        a = int(acts[i])
        r = float(rews[i])
        # Bootstrapped target approximated from immediate next reward sign.
        nret = _safe_float(rows[i + 1].get("realized_return", 0.0), 0.0)
        v_next = 1.0 if nret > 0 else (-1.0 if nret < 0 else 0.0)
        q = np.zeros((3,), dtype=np.float32)
        q[a] = r + gamma * v_next
        dqn_states.append(s)
        dqn_actions.append(a)
        dqn_targets.append(q)

    return (
        np.asarray(seqs, dtype=np.float32),
        np.asarray(ys, dtype=np.float32),
        np.asarray(dqn_states, dtype=np.float32),
        np.asarray(dqn_actions, dtype=np.int64),
    )


def train_neural_ensemble_for_ticker(ticker: str) -> NeuralTrainReport:
    if not use_neural_ensemble():
        return NeuralTrainReport(ticker=ticker, applied=False, reason="disabled_or_torch_missing", n_samples=0)

    seq_len = _i("NEURAL_SEQ_LEN", 48)
    min_n = _i("NEURAL_MIN_SAMPLES", 80)
    rows = _load_replay(ticker=ticker, max_samples=_i("NEURAL_MAX_SAMPLES", 6000))
    X, y, dqn_s, dqn_a = _build_windows(rows, seq_len=seq_len)
    save_as = ticker
    if len(X) < min_n:
        rows = _load_replay(ticker=None, max_samples=_i("NEURAL_MAX_SAMPLES", 6000))
        X, y, dqn_s, dqn_a = _build_windows(rows, seq_len=seq_len)
        save_as = GLOBAL_TICKER
        if len(X) < min_n:
            return NeuralTrainReport(
                ticker=ticker,
                applied=False,
                reason=f"too_few_samples:{len(X)}",
                n_samples=int(len(X)),
            )

    paths = {k: _checkpoint_path(save_as, k) for k in ALL_MODEL_KEYS}
    dev = torch.device("cuda" if torch.cuda.is_available() and _b("NEURAL_CUDA", True) else "cpu")
    n_feat = X.shape[-1]
    epochs = _i("NEURAL_EPOCHS", 12)
    bs = _i("NEURAL_BATCH", 128)
    lr = _f("NEURAL_LR", 1e-3)
    arch = _train_arch()

    def _fit_binary(model: nn.Module, key: str) -> float:
        model.to(dev)
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
        loss_fn = nn.BCEWithLogitsLoss()
        Xt = torch.from_numpy(X).to(dev)
        yt = torch.from_numpy(y).to(dev)
        model.train()
        last_loss = 0.0
        for _ in range(epochs):
            idx = torch.randperm(len(Xt))
            for s in range(0, len(idx), bs):
                sel = idx[s : s + bs]
                opt.zero_grad()
                logit = model(Xt[sel])
                loss = loss_fn(logit, yt[sel])
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                last_loss = float(loss.item())
        torch.save(
            {"state_dict": {k: v.detach().cpu() for k, v in model.state_dict().items()}, "seq_len": seq_len, "n_feat": n_feat, "arch": arch},
            paths[key],
        )
        return last_loss

    lstm = _make_head("lstm", n_feat, arch)
    cnn = _make_head("cnn", n_feat, arch)
    ga = _make_head("ga_lstm", n_feat, arch)
    cb = _make_head("cnn_bilstm", n_feat, arch)

    rep = NeuralTrainReport(ticker=ticker, applied=True, reason="updated" if save_as == ticker else "updated_global", n_samples=int(len(X)))
    rep.lstm_loss = _fit_binary(lstm, "lstm")
    rep.cnn_loss = _fit_binary(cnn, "cnn")
    rep.ga_lstm_loss = _fit_binary(ga, "ga_lstm")
    rep.cnn_bilstm_loss = _fit_binary(cb, "cnn_bilstm")
    try:
        tr = _make_head("transformer", n_feat, arch)
        rep.transformer_loss = _fit_binary(tr, "transformer")
    except Exception as e:
        log.debug("[NEURAL] transformer skip: %s", e)

    # DQN fit (supervised Bellman-ish target from replay).
    if len(dqn_s) > 10:
        dqn = _make_head("dqn", n_feat, arch).to(dev)
        opt = torch.optim.AdamW(dqn.parameters(), lr=lr, weight_decay=1e-4)
        dqn_s_t = torch.from_numpy(dqn_s).to(dev)
        dqn_a_t = torch.from_numpy(dqn_a).to(dev)
        rr = np.asarray([_safe_float(r.get("realized_return", 0.0), 0.0) for r in rows[-len(dqn_s) :]], dtype=np.float32)
        rw = np.asarray([_safe_float(r.get("reward", 0.0), 0.0) for r in rows[-len(dqn_s) :]], dtype=np.float32)
        q_sel = np.clip(rw + rr * 2.0, -2.0, 2.0).astype(np.float32)
        q_sel_t = torch.from_numpy(q_sel).to(dev)
        dqn.train()
        last = 0.0
        for _ in range(max(1, epochs)):
            idx = torch.randperm(len(dqn_s_t))
            for s in range(0, len(idx), bs):
                sel = idx[s : s + bs]
                opt.zero_grad()
                q = dqn(dqn_s_t[sel])
                q_a = q.gather(1, dqn_a_t[sel].unsqueeze(1)).squeeze(1)
                loss = F.mse_loss(q_a, q_sel_t[sel])
                loss.backward()
                nn.utils.clip_grad_norm_(dqn.parameters(), 1.0)
                opt.step()
                last = float(loss.item())
        rep.dqn_loss = last
        torch.save(
            {"state_dict": {k: v.detach().cpu() for k, v in dqn.state_dict().items()}, "n_feat": n_feat, "arch": arch},
            paths["dqn"],
        )

    return rep


def _load_model(path: Path, model: nn.Module | None = None, *, key: str | None = None) -> nn.Module | None:
    if not path.is_file():
        return None
    cache_on = os.getenv("NEURAL_MODEL_CACHE", "true").lower() in ("1", "true", "yes")
    cache_key = str(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    if cache_on:
        hit = _TORCH_MODEL_CACHE.get(cache_key)
        if hit is not None and hit[0] == mtime:
            return hit[1]
    try:
        b = torch.load(path, map_location="cpu")
        n_feat = int(b.get("n_feat") or 0) or len(FEATURE_COLS)
        arch = b.get("arch") if isinstance(b.get("arch"), dict) else {}
        if model is None:
            if not key:
                return None
            model = _make_head(key, n_feat, arch)
        model.load_state_dict(b["state_dict"])
        model.eval()
    except Exception:
        return None
    if cache_on:
        max_sz = int(os.getenv("NEURAL_MODEL_CACHE_SIZE", "128"))
        if len(_TORCH_MODEL_CACHE) >= max_sz > 0:
            _TORCH_MODEL_CACHE.pop(next(iter(_TORCH_MODEL_CACHE)))
        _TORCH_MODEL_CACHE[cache_key] = (mtime, model)
    return model


def _prepare_inference_tensors(
    ticker: str,
    current_state: dict,
) -> tuple[np.ndarray, np.ndarray, int] | None:
    """Build [1,T,F] sequence and [1,F] last-bar vector for inference.

    If this ticker has little replay, tile the live state so GLOBAL / sibling
    checkpoints still produce a p_up instead of silently returning None.
    """
    rows = _load_replay(ticker=ticker, max_samples=_i("NEURAL_PRED_MAX_SAMPLES", 2000))
    seq_len = _i("NEURAL_SEQ_LEN", 48)
    n_feat = len(FEATURE_COLS)
    cur = _state_vec(current_state)
    if not rows:
        recent = [cur] * seq_len
    else:
        recent = [_state_vec(r.get("state", {})) for r in rows[-(seq_len - 1) :]]
        recent.append(cur)
        while len(recent) < seq_len:
            recent.insert(0, recent[0])
    seq = np.asarray(recent[-seq_len:], dtype=np.float32)[None, :, :]
    vec = seq[:, -1, :]
    return seq, vec, n_feat


def _infer_all_models(
    ticker: str,
    seq: np.ndarray,
    vec: np.ndarray,
    n_feat: int,
) -> tuple[dict[str, dict], list[float]]:
    """Run all available checkpoints; return per-model dicts and p_up list for ensemble."""
    paths = _model_paths(ticker)
    models_out: dict[str, dict] = {}
    preds: list[float] = []
    dev = torch.device("cpu")
    xt = torch.from_numpy(seq).to(dev)
    xv = torch.from_numpy(vec).to(dev)

    with torch.no_grad():
        for key, _factory in (
            ("lstm", _LSTMHead),
            ("cnn", _CNNHead),
            ("ga_lstm", _GALSTMHead),
            ("cnn_bilstm", _CNNBiLSTMHead),
            ("transformer", _TransformerHead),
        ):
            m = _load_model(paths[key], key=key)
            if m is None:
                models_out[key] = {"loaded": False}
                continue
            p = float(torch.sigmoid(m(xt)).item())
            preds.append(p)
            models_out[key] = {"loaded": True, "p_up": round(p, 4)}

        m = _load_model(paths["dqn"], key="dqn")
        if m is None:
            models_out["dqn"] = {"loaded": False}
        else:
            q = m(xv)
            probs = torch.softmax(q, dim=-1)[0]
            p_short = float(probs[ACTION_TO_IDX["SHORT"]].item())
            p_hold = float(probs[ACTION_TO_IDX["HOLD"]].item())
            p_long = float(probs[ACTION_TO_IDX["LONG"]].item())
            action_idx = int(torch.argmax(probs).item())
            preds.append(p_long)
            models_out["dqn"] = {
                "loaded": True,
                "p_up": round(p_long, 4),
                "p_short": round(p_short, 4),
                "p_hold": round(p_hold, 4),
                "p_long": round(p_long, 4),
                "action": IDX_TO_ACTION.get(action_idx, "HOLD"),
            }

    return models_out, preds


def _blend_preds(arr: np.ndarray) -> tuple[float, float]:
    """Median-centered Gaussian weights — outliers (disagreement) get less vote."""
    if arr.size == 0:
        return 0.5, 0.0
    if arr.size == 1:
        return float(np.clip(float(arr[0]), 0.0, 1.0)), 0.0
    std = float(arr.std())
    med = float(np.median(arr))
    scale = max(std, 0.04)
    w = np.exp(-((arr - med) / scale) ** 2)
    w = w / float(w.sum() or 1.0)
    return float(np.clip(float((w * arr).sum()), 0.0, 1.0)), std


def neural_ensemble_details(
    ticker: str,
    current_state: dict,
) -> dict | None:
    """Per-model probabilities, ensemble mean, and disagreement metrics."""
    if not use_neural_ensemble():
        return None

    prepared = _prepare_inference_tensors(ticker, current_state)
    if prepared is None:
        return None
    seq, vec, n_feat = prepared
    models_out, preds = _infer_all_models(ticker, seq, vec, n_feat)
    if not preds:
        return None

    arr = np.asarray(preds, dtype=np.float64)
    p_ens, disagree = _blend_preds(arr)
    return {
        "ticker": ticker.upper(),
        "ensemble_p_up": p_ens,
        "disagreement_std": disagree,
        "disagreement_range": float(arr.max() - arr.min()) if len(arr) > 1 else 0.0,
        "n_models_loaded": len(preds),
        "blend_weight": _f("NEURAL_BLEND_WEIGHT", 0.35),
        "models": models_out,
    }


def neural_ensemble_p_up(
    ticker: str,
    current_state: dict,
) -> float | None:
    """Return averaged p_up across {LSTM, CNN, GA-LSTM, CNN-BiLSTM, DQN}."""
    details = neural_ensemble_details(ticker, current_state)
    if not details:
        return None
    return details.get("ensemble_p_up")


def model_win_rates_for_ticker(
    ticker: str,
    eval_frac: float | None = None,
) -> dict[str, dict]:
    """Chronological holdout directional accuracy per architecture."""
    if not use_neural_ensemble():
        return {}

    rows = _load_replay(ticker=ticker, max_samples=_i("NEURAL_MAX_SAMPLES", 6000))
    seq_len = _i("NEURAL_SEQ_LEN", 48)
    X, y, dqn_s, _ = _build_windows(rows, seq_len=seq_len)
    min_eval = _i("NEURAL_WINRATE_MIN_EVAL", 12)
    if len(X) < min_eval + 5:
        return {}

    frac = eval_frac if eval_frac is not None else _f("NEURAL_WINRATE_EVAL_FRAC", 0.3)
    frac = float(np.clip(frac, 0.1, 0.5))
    split = max(min_eval, int(len(X) * (1.0 - frac)))
    if split >= len(X):
        split = len(X) - min_eval
    Xe, ye = X[split:], y[split:]
    dqn_e = dqn_s[split:]
    y_bin = (ye >= 0.5).astype(np.int64)

    paths = _model_paths(ticker)
    n_feat = X.shape[-1]
    dev = torch.device("cpu")
    out: dict[str, dict] = {}

    with torch.no_grad():
        for key in ("lstm", "cnn", "ga_lstm", "cnn_bilstm", "transformer"):
            m = _load_model(paths[key], key=key)
            if m is None:
                continue
            p = torch.sigmoid(m(torch.from_numpy(Xe).to(dev))).cpu().numpy()
            pred = (p >= 0.5).astype(np.int64)
            correct = int((pred == y_bin).sum())
            n = int(len(y_bin))
            out[key] = {
                "win_rate": round(correct / n, 4) if n else 0.0,
                "n": n,
                "correct": correct,
            }

        m = _load_model(paths["dqn"], key="dqn")
        if m is not None:
            q = m(torch.from_numpy(dqn_e).to(dev))
            p_long = torch.softmax(q, dim=-1)[:, ACTION_TO_IDX["LONG"]].cpu().numpy()
            pred = (p_long >= 0.5).astype(np.int64)
            correct = int((pred == y_bin).sum())
            n = int(len(y_bin))
            out["dqn"] = {
                "win_rate": round(correct / n, 4) if n else 0.0,
                "n": n,
                "correct": correct,
            }

    return out


def aggregate_model_win_rates() -> dict[str, dict]:
    """Pool holdout accuracy across tickers that have trained checkpoints."""
    if not use_neural_ensemble():
        return {}

    rows = _load_replay(ticker=None)
    tickers = sorted({str(r.get("ticker", "")).upper() for r in rows if r.get("ticker")})
    pooled: dict[str, dict[str, int | float]] = {
        k: {"correct": 0, "n": 0} for k in ALL_MODEL_KEYS
    }
    per_ticker: dict[str, dict] = {}

    for t in tickers:
        wr = model_win_rates_for_ticker(t)
        if not wr:
            continue
        per_ticker[t] = wr
        for k, v in wr.items():
            if k not in pooled:
                continue
            pooled[k]["correct"] += int(v.get("correct", 0))
            pooled[k]["n"] += int(v.get("n", 0))

    global_wr: dict[str, dict] = {}
    for k, acc in pooled.items():
        n = int(acc["n"])
        if n <= 0:
            continue
        c = int(acc["correct"])
        global_wr[k] = {
            "win_rate": round(c / n, 4),
            "n": n,
            "correct": c,
        }

    leaderboard = sorted(
        [{"model": k, **v} for k, v in global_wr.items()],
        key=lambda x: (-x["win_rate"], -x["n"]),
    )
    return {
        "global": global_wr,
        "leaderboard": leaderboard,
        "tickers_evaluated": len(per_ticker),
        "per_ticker": per_ticker,
    }


def build_neural_dashboard(
    scored_rows: list[dict],
    *,
    top_disagreement: int = 15,
) -> dict:
    """Aggregate neural metrics for paper-sim report JSON."""
    from datetime import datetime, timezone

    wr = aggregate_model_win_rates()
    with_breakdown = [r for r in scored_rows if isinstance(r.get("neural_breakdown"), dict)]
    loaded = [r for r in with_breakdown if r["neural_breakdown"].get("n_models_loaded", 0) > 0]

    by_disagreement = sorted(
        loaded,
        key=lambda r: -float(r["neural_breakdown"].get("disagreement_std", 0.0)),
    )[:top_disagreement]

    picks = [
        r for r in scored_rows
        if str(r.get("action", "")).upper() in ("BUY", "SHORT")
        and r.get("neural_p_up") is not None
    ]

    def _brief(r: dict) -> dict:
        nb = r.get("neural_breakdown") or {}
        return {
            "ticker": r.get("ticker"),
            "action": r.get("action"),
            "p_up": round(float(r.get("p_up", 0.0)), 4),
            "neural_p_up": r.get("neural_p_up"),
            "ensemble_p_up": nb.get("ensemble_p_up"),
            "disagreement_std": nb.get("disagreement_std"),
            "n_models_loaded": nb.get("n_models_loaded"),
        }

    replay_n = len(_load_replay(ticker=None, max_samples=100_000))
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "replay_n_samples": replay_n,
        "symbols_with_neural": len(with_breakdown),
        "model_win_rates": wr.get("global", {}),
        "model_leaderboard": wr.get("leaderboard", []),
        "tickers_evaluated_for_win_rate": wr.get("tickers_evaluated", 0),
        "highest_disagreement": [_brief(r) for r in by_disagreement],
        "trade_picks_neural": [_brief(r) for r in picks[:30]],
    }


def print_neural_dashboard_summary(dashboard: dict | None) -> None:
    """Concise console summary after paper sim."""
    if not dashboard:
        return
    print("\n=== Neural ensemble dashboard ===")
    print(f"Replay samples: {dashboard.get('replay_n_samples', 0)}")
    print(f"Symbols scored with neural: {dashboard.get('symbols_with_neural', 0)}")
    lb = dashboard.get("model_leaderboard") or []
    if lb:
        print("Model holdout win-rates (p_up direction vs realized move):")
        for row in lb:
            print(
                f"  {row['model']:12} win_rate={row['win_rate']:.3f}  n={row['n']}"
            )
    else:
        print("Model win-rates: insufficient replay/checkpoints")
    hi = dashboard.get("highest_disagreement") or []
    if hi:
        print("Highest model disagreement (std of p_up):")
        for r in hi[:8]:
            print(
                f"  {r.get('ticker','?'):6} std={float(r.get('disagreement_std',0)):.3f} "
                f"neural={r.get('neural_p_up')} blended_p_up={r.get('p_up')}"
            )

