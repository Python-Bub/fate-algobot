"""Homemade Gainz brain — trained from scratch on our public teacher.

Same idea as OpenAI: we own the weights, so inference has no vendor rate limit.
Teacher labels come from analytics.gainz_v2.assess (published math only).
Never downloads invite-only V2. Never calls OpenAI.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CKPT = ROOT / "data" / "self_improve" / "gainz_brain.pt"
META = ROOT / "data" / "self_improve" / "gainz_brain.json"
FEAT_DIM = 12
SIDES = ("none", "buy", "sell")

try:
    import torch
    from torch import nn

    _TORCH_OK = True
except Exception:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_OK = False


class GainzNet(nn.Module if _TORCH_OK else object):  # type: ignore[misc]
    def __init__(self, d: int = FEAT_DIM, h: int = 64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(d, h),
            nn.ReLU(),
            nn.Linear(h, h),
            nn.ReLU(),
            nn.Linear(h, 3),
        )

    def forward(self, x):
        return self.net(x)


def features(df: pd.DataFrame) -> np.ndarray:
    if df is None or len(df) < 22:
        return np.zeros(FEAT_DIM, dtype=np.float32)
    c = df["Close"].astype(float)
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    v = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(0.0, index=df.index)
    px = float(c.iloc[-1])
    prev = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev).abs(), (l - prev).abs()], axis=1).max(axis=1)
    atr = float(tr.ewm(span=14, adjust=False).mean().iloc[-1] or 0.0)
    roc5 = float(c.iloc[-1] / max(float(c.iloc[-6]), 1e-9) - 1.0) if len(c) >= 6 else 0.0
    roc1 = float(c.iloc[-1] / max(float(c.iloc[-2]), 1e-9) - 1.0)
    e9 = float(c.ewm(span=9, adjust=False).mean().iloc[-1])
    e21 = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
    tp = (h + l + c) / 3.0
    vw = float((tp * v).cumsum().iloc[-1] / max(float(v.cumsum().iloc[-1]), 1e-9))
    delta = np.sign(c.diff().fillna(0.0).to_numpy())
    cvd = float((v.to_numpy() * delta).cumsum()[-1] or 0.0)
    vol_med = float(v.iloc[-20:].median()) if len(v) >= 20 else float(v.iloc[-1] or 1.0)
    atr_pct = atr / max(px, 1e-9)
    thr = 0.004 * (1.0 + atr_pct * 2.0)
    x = np.array(
        [
            roc5,
            roc1,
            atr_pct,
            (e9 - e21) / max(px, 1e-9),
            (px - vw) / max(px, 1e-9),
            np.tanh(cvd / 1e6),
            float(v.iloc[-1] / max(vol_med, 1e-9)),
            1.0 if abs(roc5) >= thr else 0.0,
            1.0 if e9 > e21 else 0.0,
            1.0 if px > vw else 0.0,
            1.0 if roc5 > 0 else 0.0,
            1.0 if cvd > 0 else 0.0,
        ],
        dtype=np.float32,
    )
    return np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)


def _label(df: pd.DataFrame, symbol: str = "BRN") -> int:
    from analytics.gainz_v2 import assess

    g = assess(df, symbol=symbol)
    return SIDES.index(g.side if g.side in SIDES else "none")


def _batch(n: int, *, start_seed: int = 0) -> tuple[Any, Any]:
    from self_modify.gainz_evolver import _sample_bars

    xs: list[np.ndarray] = []
    ys: list[int] = []
    drifts = (0.02, 0.12, -0.10, 0.08, -0.08, 0.0, 0.05, -0.04)
    for i in range(n):
        seed = int(start_seed + i * 17 + 3)
        df = _sample_bars(seed=seed, drift=drifts[i % len(drifts)])
        xs.append(features(df))
        ys.append(_label(df, symbol=f"B{seed % 997}"))
    x = torch.tensor(np.stack(xs), dtype=torch.float32)
    y = torch.tensor(ys, dtype=torch.long)
    return x, y


def _load_net() -> tuple[Any, dict[str, Any]]:
    net = GainzNet()
    meta: dict[str, Any] = {"steps": 0, "loss": None, "acc": None}
    if META.is_file():
        try:
            meta.update(json.loads(META.read_text(encoding="utf-8")))
        except Exception:
            pass
    if CKPT.is_file():
        try:
            net.load_state_dict(torch.load(CKPT, map_location="cpu", weights_only=True))
        except Exception:
            try:
                net.load_state_dict(torch.load(CKPT, map_location="cpu"))
            except Exception:
                pass
    return net, meta


def _save(net: Any, meta: dict[str, Any]) -> None:
    CKPT.parent.mkdir(parents=True, exist_ok=True)
    torch.save(net.state_dict(), CKPT)
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def train_steps(n: int | None = None) -> dict[str, Any]:
    """SGD on synthetic 1m tapes labeled by the public teacher. Local only."""
    if not _TORCH_OK:
        return {"ok": False, "reason": "no_torch"}
    n = int(n if n is not None else os.getenv("GAINZ_BRAIN_STEPS", "16"))
    n = max(4, min(n, 256))
    net, meta = _load_net()
    net.train()
    opt = torch.optim.Adam(net.parameters(), lr=float(os.getenv("GAINZ_BRAIN_LR", "0.002")))
    loss_fn = nn.CrossEntropyLoss()
    last_loss = 0.0
    correct = 0
    total = 0
    t0 = time.time()
    bs = max(8, min(int(os.getenv("GAINZ_BRAIN_BATCH", "16")), 64))
    for i in range(n):
        x, y = _batch(bs, start_seed=int(meta.get("steps") or 0) + i * bs)
        opt.zero_grad()
        logits = net(x)
        loss = loss_fn(logits, y)
        loss.backward()
        opt.step()
        last_loss = float(loss.item())
        pred = logits.argmax(dim=1)
        correct += int((pred == y).sum().item())
        total += int(y.numel())
    acc = correct / max(total, 1)
    meta.update(
        {
            "steps": int(meta.get("steps") or 0) + n,
            "loss": last_loss,
            "acc": acc,
            "updated": time.time(),
            "owned": True,
            "teacher": "analytics.gainz_v2.assess",
            "rate_limit": "none — local weights",
        }
    )
    _save(net, meta)
    return {
        "ok": True,
        "loss": round(last_loss, 4),
        "acc": round(acc, 4),
        "steps": meta["steps"],
        "sec": round(time.time() - t0, 2),
    }


def predict(df: pd.DataFrame) -> dict[str, Any]:
    if not _TORCH_OK:
        return {"side": "none", "confidence": 0.0, "ok": False}
    net, _ = _load_net()
    net.eval()
    x = torch.tensor(features(df), dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        logits = net(x)
        prob = torch.softmax(logits, dim=1).squeeze(0).tolist()
    idx = int(np.argmax(prob))
    return {"side": SIDES[idx], "confidence": float(prob[idx]), "probs": dict(zip(SIDES, prob)), "ok": True}
