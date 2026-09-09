"""Optional LSTM/RNN meta head — non-linear sequence head over the same FEATURE matrix.

This is **opt-in**: enable with `USE_LSTM_HEAD=true`. Disabled by default to keep
training fast on the universe. When enabled, `train_lstm_head(ticker)` trains a
small LSTM over the last `LSTM_SEQ_LEN` bars of features and saves a per-ticker
checkpoint to `models/lstm/{TICKER}_lstm.pt`. Inference happens via
`lstm_proba_up(ticker, df)` and the result is blended into the meta-stack input
when `BLEND_LSTM_INTO_META=true`.

Architecture: LSTM(`LSTM_HIDDEN`×`LSTM_LAYERS`, default 128×3) → Dropout → Linear
→ sigmoid. Trained chronologically (last 20% bars held out) with early stopping
on holdout accuracy; the **best** weights are saved (not the last epoch).
Checkpoints store `hidden`/`num_layers` so older 64×2 heads still load.
Falls back to no-op when PyTorch is unavailable or the bundle is missing.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from utils import log

try:  # PyTorch is optional; the rest of the bot must work without it.
    import torch
    from torch import nn

    _TORCH_OK = True
except Exception:  # pragma: no cover - import-time guard
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_OK = False


MODEL_DIR = Path("models/lstm")


def lstm_model_path(ticker: str) -> Path:
    return MODEL_DIR / f"{ticker.strip().upper()}_lstm.pt"


def has_lstm_head(ticker: str, *, min_bytes: int = 1000) -> bool:
    """True if an on-disk LSTM checkpoint exists (size gate only — used at serve time)."""
    p = lstm_model_path(ticker)
    try:
        return p.is_file() and p.stat().st_size >= min_bytes
    except OSError:
        return False


def has_quality_lstm_head(ticker: str, *, min_bytes: int = 1000) -> bool:
    """Training-complete gate: size + optional holdout accuracy (LSTM_MIN_TEST_ACC)."""
    if not has_lstm_head(ticker, min_bytes=min_bytes):
        return False
    min_acc = float(os.getenv("LSTM_MIN_TEST_ACC", "0.45") or 0.45)
    if min_acc <= 0:
        return True
    q = lstm_head_quality(ticker)
    return bool(q.get("ok"))


def lstm_head_quality(ticker: str) -> dict:
    """Inspect one head — used by audit / requeue (never deletes models)."""
    p = lstm_model_path(ticker)
    out: dict = {"ticker": ticker.upper(), "path": str(p), "ok": False}
    try:
        if not p.is_file():
            out["reason"] = "missing"
            return out
        out["bytes"] = int(p.stat().st_size)
        if out["bytes"] < 1000:
            out["reason"] = "tiny_file"
            return out
        if not _TORCH_OK:
            out["reason"] = "no_torch"
            out["ok"] = True  # size gate only
            return out
        bundle = torch.load(p, map_location="cpu", weights_only=False)  # type: ignore[misc]
        if not isinstance(bundle, dict) or "state_dict" not in bundle:
            out["reason"] = "no_state_dict"
            return out
        ta = bundle.get("test_acc")
        out["test_acc"] = float(ta) if ta is not None else None
        out["feat_cols"] = len(bundle.get("feat_cols") or [])
        out["seq_len"] = bundle.get("seq_len")
        min_acc = float(os.getenv("LSTM_MIN_TEST_ACC", "0.45") or 0.45)
        if out["test_acc"] is None:
            out["reason"] = "no_test_acc"
            return out
        if out["test_acc"] < min_acc:
            out["reason"] = "weak_test_acc"
            return out
        out["ok"] = True
        out["reason"] = "ok"
        return out
    except Exception as e:
        out["reason"] = f"load_error:{type(e).__name__}"
        return out


def _b(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes")


def _lstm_arch() -> tuple[int, int, float]:
    hidden = int(os.getenv("LSTM_HIDDEN", "128") or 128)
    layers = int(os.getenv("LSTM_LAYERS", "3") or 3)
    dropout = float(os.getenv("LSTM_DROPOUT", "0.2") or 0.2)
    hidden = max(16, hidden)
    layers = max(1, min(8, layers))
    if layers <= 1:
        dropout = 0.0
    return hidden, layers, dropout


def _torch_device():
    if not _TORCH_OK:
        return None
    want = (os.getenv("LSTM_CUDA", "true") or "true").strip().lower() in ("1", "true", "yes")
    if want and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


class _LSTMNet(nn.Module if _TORCH_OK else object):  # type: ignore[misc]
    def __init__(self, n_features: int, hidden: int = 128, num_layers: int = 3, dropout: float = 0.2):
        super().__init__()
        self.hidden = int(hidden)
        self.num_layers = int(num_layers)
        self.dropout_p = float(dropout if num_layers > 1 else 0.0)
        self.lstm = nn.LSTM(
            input_size=n_features,
            hidden_size=self.hidden,
            num_layers=self.num_layers,
            batch_first=True,
            dropout=self.dropout_p,
        )
        self.head = nn.Sequential(
            nn.Linear(self.hidden, max(16, self.hidden // 2)),
            nn.ReLU(),
            nn.Dropout(float(dropout)),
            nn.Linear(max(16, self.hidden // 2), 1),
        )

    def forward(self, x: "torch.Tensor") -> "torch.Tensor":
        out, _ = self.lstm(x)
        last = out[:, -1, :]
        logit = self.head(last).squeeze(-1)
        return logit


def _build_sequences(
    X: np.ndarray, y: np.ndarray, seq_len: int
) -> tuple[np.ndarray, np.ndarray]:
    if len(X) <= seq_len:
        return np.empty((0, seq_len, X.shape[1]), dtype=np.float32), np.empty((0,), dtype=np.float32)
    seqs = np.lib.stride_tricks.sliding_window_view(X, window_shape=seq_len, axis=0)
    seqs = np.swapaxes(seqs, 1, 2)
    y_aligned = y[seq_len - 1 :]
    return seqs.astype(np.float32), y_aligned.astype(np.float32)


def train_lstm_head(
    ticker: str,
    df: pd.DataFrame,
    feat_cols: list[str],
    target_col: str = "target_long",
    seq_len: int | None = None,
    epochs: int | None = None,
    lr: float | None = None,
    *,
    force: bool = False,
) -> dict:
    """Train a small LSTM on `df[feat_cols]` predicting `target_col`.

    Returns a dict summary; saves the checkpoint to `models/lstm/{TICKER}_lstm.pt`.
    """
    if not _TORCH_OK:
        return {"skipped": "torch_unavailable"}
    if not force and not _b("USE_LSTM_HEAD", False):
        return {"skipped": "USE_LSTM_HEAD=false"}
    if df.empty or target_col not in df.columns:
        return {"skipped": "no_target"}

    seq_len = int(seq_len or os.getenv("LSTM_SEQ_LEN", "60"))
    epochs = int(epochs or os.getenv("LSTM_EPOCHS", "20"))
    lr = float(lr or os.getenv("LSTM_LR", "1e-3"))
    hidden, num_layers, dropout = _lstm_arch()

    use_cols = [c for c in feat_cols if c in df.columns]
    if len(use_cols) < 4:
        return {"skipped": "too_few_features"}

    work = df.dropna(subset=[target_col]).copy().sort_index()
    X_full = work[use_cols].replace([np.inf, -np.inf], 0).fillna(0).to_numpy(dtype=np.float32)
    y_full = work[target_col].astype(np.float32).to_numpy()

    min_over = int(os.getenv("LSTM_MIN_ROWS_OVER_SEQ", "40"))
    min_seqs = int(os.getenv("LSTM_MIN_SEQUENCES", "30"))
    # Short listings (e.g. SPCX): shrink seq_len instead of permanently skipping.
    if len(X_full) < seq_len + min_over and os.getenv("LSTM_ADAPT_SHORT", "true").lower() in (
        "1",
        "true",
        "yes",
    ):
        adapt_min = int(os.getenv("LSTM_ADAPT_MIN_SEQ", "8"))
        # Need enough rows for adapt_min seq + a few holdout sequences.
        need = adapt_min + max(5, int(os.getenv("LSTM_ADAPT_MIN_EXTRA", "10")))
        if len(X_full) >= need:
            seq_len = max(adapt_min, min(seq_len, len(X_full) - max(5, min_over // 4)))
            min_over = max(5, min(min_over, len(X_full) - seq_len))
            min_seqs = max(5, min(min_seqs, max(5, len(X_full) - seq_len)))

    if len(X_full) < seq_len + min_over:
        return {"skipped": "too_few_rows"}

    seqs, labels = _build_sequences(X_full, y_full, seq_len)
    if len(seqs) < min_seqs:
        return {"skipped": "too_few_sequences"}

    # Chronological holdout — last 20% of *sequences* (no random shuffle).
    # Drop an embargo of sequences from the train tail so 20d labels cannot
    # peek into the holdout window (same idea as daily TRAIN_EMBARGO_*).
    n = len(seqs)
    k = max(1, int(n * 0.8))
    emb = int(os.getenv("LSTM_EMBARGO_SEQS", os.getenv("TRAIN_EMBARGO_LONG", "20")))
    train_end = k
    min_train = max(8, int(n * 0.4))
    if emb > 0:
        train_end = min(k, max(min_train, k - emb))
    X_tr, X_te = seqs[:train_end], seqs[k:]
    y_tr, y_te = labels[:train_end], labels[k:]

    # Per-feature z-score using only training rows (no leakage).
    mu = X_tr.reshape(-1, X_tr.shape[-1]).mean(axis=0)
    sd = X_tr.reshape(-1, X_tr.shape[-1]).std(axis=0) + 1e-6
    X_tr = (X_tr - mu) / sd
    X_te = (X_te - mu) / sd

    device = _torch_device()
    net = _LSTMNet(
        n_features=len(use_cols), hidden=hidden, num_layers=num_layers, dropout=dropout
    ).to(device)
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    loss_fn = nn.BCEWithLogitsLoss()
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="max", factor=0.5, patience=2)

    Xt = torch.from_numpy(X_tr).to(device)
    yt = torch.from_numpy(y_tr).to(device)
    Xe = torch.from_numpy(X_te).to(device)
    ye = torch.from_numpy(y_te).to(device)

    batch = int(os.getenv("LSTM_BATCH", "256"))
    patience = int(os.getenv("LSTM_EARLY_STOP_PATIENCE", "5") or 5)
    best_test_acc = -1.0
    best_state = None
    stale = 0
    for ep in range(epochs):
        net.train()
        idx = torch.randperm(len(Xt))
        for s in range(0, len(idx), batch):
            sel = idx[s : s + batch]
            opt.zero_grad()
            logit = net(Xt[sel])
            loss = loss_fn(logit, yt[sel])
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
        net.eval()
        with torch.no_grad():
            if len(Xe) > 0:
                p_te = torch.sigmoid(net(Xe))
                acc = float(((p_te > 0.5).float() == ye).float().mean().item())
            else:
                p_tr = torch.sigmoid(net(Xt))
                acc = float(((p_tr > 0.5).float() == yt).float().mean().item())
        sched.step(acc)
        if acc > best_test_acc:
            best_test_acc = acc
            best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
            stale = 0
        else:
            stale += 1
        log.info("[LSTM] %s ep=%d test_acc=%.4f best=%.4f", ticker, ep + 1, acc, best_test_acc)
        if patience > 0 and stale >= patience:
            log.info("[LSTM] %s early-stop at ep=%d", ticker, ep + 1)
            break

    if best_state is not None:
        net.load_state_dict(best_state)
    if best_test_acc < 0:
        best_test_acc = 0.0

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out_path = lstm_model_path(ticker)
    torch.save(
        {
            "state_dict": {k: v.cpu() for k, v in net.state_dict().items()},
            "feat_cols": use_cols,
            "seq_len": seq_len,
            "mu": mu.tolist(),
            "sd": sd.tolist(),
            "target_col": target_col,
            "test_acc": best_test_acc,
            "hidden": hidden,
            "num_layers": num_layers,
            "dropout": dropout,
        },
        out_path,
    )
    return {
        "saved": str(out_path),
        "test_acc": best_test_acc,
        "rows": int(n),
        "hidden": hidden,
        "num_layers": num_layers,
        "seq_len": seq_len,
    }


def _load_bundle(ticker: str):
    if not _TORCH_OK:
        return None
    p = lstm_model_path(ticker)
    if not p.is_file():
        return None
    try:
        return torch.load(p, map_location="cpu")
    except Exception as e:
        log.debug("[LSTM] load failed %s: %s", ticker, e)
        return None


def lstm_proba_up(ticker: str, df: pd.DataFrame) -> float | None:
    """Return calibrated-ish probability of up move from the LSTM head, or None when unavailable."""
    if not _TORCH_OK:
        return None
    if not has_lstm_head(ticker) and not _b("USE_LSTM_HEAD", False):
        return None
    bundle = _load_bundle(ticker)
    if bundle is None:
        return None
    feat_cols = list(bundle.get("feat_cols") or [])
    seq_len = int(bundle.get("seq_len") or 60)
    if df.empty or not feat_cols:
        return None
    missing = [c for c in feat_cols if c not in df.columns]
    if missing:
        for c in missing:
            df = df.copy()
            df[c] = 0.0
    X = df[feat_cols].astype(np.float32).replace([np.inf, -np.inf], 0).fillna(0).to_numpy()
    if len(X) < seq_len:
        return None
    mu = np.asarray(bundle["mu"], dtype=np.float32)
    sd = np.asarray(bundle["sd"], dtype=np.float32)
    seq = ((X[-seq_len:] - mu) / sd)[None, :, :]

    hidden = int(bundle.get("hidden") or 64)
    num_layers = int(bundle.get("num_layers") or 2)
    dropout = float(bundle.get("dropout") or 0.2)
    net = _LSTMNet(
        n_features=len(feat_cols), hidden=hidden, num_layers=num_layers, dropout=dropout
    )
    net.load_state_dict(bundle["state_dict"])
    net.eval()
    with torch.no_grad():
        logit = net(torch.from_numpy(seq))
        p = float(torch.sigmoid(logit).item())
    return p
