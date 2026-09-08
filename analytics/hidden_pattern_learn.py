"""Hidden-pattern learning loop — auto-adjust detector weights + final p_up blend.

Discovers which underlying anomaly families actually predict trade outcomes, then:
  1. Up-weights successful detector families (idio / vol_div / regime / iforest / seq / motif / entropy)
  2. Soft-blends cached pattern direction into live p_up (final calculation)
  3. Attaches pattern features so next retrain can learn them
  4. Updates sequence_discover family weights when a seq:* reason was present

Never deletes models or shrinks coverage — additive only.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS_PATH = ROOT / "data" / "intel" / "hidden_pattern_weights.json"
ENTRY_SNAP_PATH = ROOT / "data" / "intel" / "hidden_pattern_entry_snaps.json"

# Detector family keys used when aggregating analyze_symbol strengths.
DEFAULT_DETECTOR_WEIGHTS: dict[str, float] = {
    "idio": 1.0,
    "vol_div": 0.9,
    "regime": 0.85,
    "iforest": 1.0,
    "seq": 0.8,
    "motif": 0.9,
    "entropy": 0.75,
    "corr_flip": 0.85,
    "gen": 1.05,
}

_REASON_FAMILY = (
    ("idio_z", "idio"),
    ("return_z", "idio"),
    ("vol_div", "vol_div"),
    ("quiet_vol", "vol_div"),
    ("ac1_break", "regime"),
    ("vol_regime", "regime"),
    ("iforest", "iforest"),
    ("mahal_z", "iforest"),
    ("seq:", "seq"),
    ("motif", "motif"),
    ("entropy", "entropy"),
    ("corr_flip", "corr_flip"),
    ("gen:", "gen"),
    ("shared_resid", "gen"),
    ("vol_echo", "gen"),
    ("delayed_echo", "gen"),
    ("resid_leadlag", "gen"),
)


def _b(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_detector_weights() -> dict[str, float]:
    """Learned multiplicative weights per detector family (clamped)."""
    doc = _load_json(WEIGHTS_PATH)
    w = dict(DEFAULT_DETECTOR_WEIGHTS)
    stored = doc.get("detectors") or {}
    for k, v in stored.items():
        try:
            w[str(k)] = float(v)
        except (TypeError, ValueError):
            continue
    # Clamp so one family never dominates permanently
    lo, hi = _f("HIDDEN_PATTERN_W_MIN", 0.35), _f("HIDDEN_PATTERN_W_MAX", 2.2)
    return {k: float(min(hi, max(lo, v))) for k, v in w.items()}


def family_from_reason(reason: str) -> str | None:
    r = (reason or "").lower()
    for needle, fam in _REASON_FAMILY:
        if needle in r:
            return fam
    return None


def families_from_hit(hit: dict[str, Any] | None) -> list[str]:
    if not hit:
        return []
    out: list[str] = []
    for reason in hit.get("reasons") or []:
        fam = family_from_reason(str(reason))
        if fam and fam not in out:
            out.append(fam)
    for fam in hit.get("detectors") or []:
        s = str(fam).strip().lower()
        if s and s not in out:
            out.append(s)
    # Persist tags encoded as det_{i}_{family}=1.0 in features
    feats = hit.get("features") or {}
    for k in feats:
        ks = str(k)
        if ks.startswith("det_") and "_" in ks[4:]:
            fam = ks.split("_", 2)[-1].strip().lower()
            if fam and fam not in out:
                out.append(fam)
    return out


def snapshot_entry_pattern(symbol: str, *, side: str = "LONG") -> None:
    """Remember which hidden patterns were active when we entered — for outcome credit."""
    if not _b("HIDDEN_ANOMALY_LEARN", True):
        return
    try:
        from analytics.hidden_pattern_anomaly import load_hits

        doc = load_hits()
        row = (doc.get("by_symbol") or {}).get(symbol.strip().upper())
        if not row:
            return
        snaps = _load_json(ENTRY_SNAP_PATH)
        by = snaps.setdefault("by_symbol", {})
        by[symbol.strip().upper()] = {
            "ts": time.time(),
            "side": side.upper(),
            "score": float(row.get("score") or 0),
            "direction": int(row.get("direction") or 0),
            "reasons": list(row.get("reasons") or [])[:6],
            "detectors": families_from_hit(row),
        }
        snaps["updated"] = time.time()
        _save_json(ENTRY_SNAP_PATH, snaps)
    except Exception:
        pass


def learn_from_trade_outcome(
    symbol: str,
    side: str,
    realized_return: float,
    *,
    bars_held: int = 1,
) -> dict[str, Any]:
    """Credit/penalize detector families that were active at entry (or latest cache)."""
    if not _b("HIDDEN_ANOMALY_LEARN", True):
        return {"applied": False, "reason": "disabled"}

    sym = symbol.strip().upper()
    snaps = _load_json(ENTRY_SNAP_PATH)
    snap = (snaps.get("by_symbol") or {}).pop(sym, None)
    if snap is None:
        try:
            from analytics.hidden_pattern_anomaly import load_hits

            row = (load_hits().get("by_symbol") or {}).get(sym)
            if row:
                snap = {
                    "score": float(row.get("score") or 0),
                    "direction": int(row.get("direction") or 0),
                    "reasons": list(row.get("reasons") or [])[:6],
                    "detectors": families_from_hit(row),
                }
        except Exception:
            snap = None
    if snap:
        snaps["by_symbol"] = snaps.get("by_symbol") or {}
        _save_json(ENTRY_SNAP_PATH, snaps)

    if not snap or float(snap.get("score") or 0) < 0.2:
        return {"applied": False, "reason": "no_pattern"}

    direction = int(snap.get("direction") or 0)
    ret = float(realized_return)
    # Did the pattern direction agree with the trade outcome?
    side_u = (side or "LONG").upper()
    signed = ret if side_u in ("LONG", "BUY") else -ret
    pattern_signed = signed * (1.0 if direction >= 0 else -1.0)
    success = pattern_signed > 0.0

    lr = _f("HIDDEN_PATTERN_LEARN_LR", 0.08)
    # Stronger update when pattern score was high
    amp = lr * (0.5 + float(snap.get("score") or 0.5))
    amp = min(0.25, amp * (1.0 + min(2.0, abs(ret) * 20.0)))

    doc = _load_json(WEIGHTS_PATH)
    detectors = dict(DEFAULT_DETECTOR_WEIGHTS)
    detectors.update({k: float(v) for k, v in (doc.get("detectors") or {}).items()})
    fams = list(snap.get("detectors") or families_from_hit(snap))
    if not fams:
        fams = ["idio"]

    for fam in fams:
        cur = float(detectors.get(fam, 1.0))
        if success:
            detectors[fam] = cur * (1.0 + amp)
        else:
            detectors[fam] = cur * (1.0 - amp * 0.85)

    lo, hi = _f("HIDDEN_PATTERN_W_MIN", 0.35), _f("HIDDEN_PATTERN_W_MAX", 2.8)
    detectors = {k: float(min(hi, max(lo, v))) for k, v in detectors.items()}

    # Soft nudge to RANK_W effective scale stored alongside (read by p_blend / rank)
    blend_max = _f("HIDDEN_PATTERN_BLEND_SCALE_MAX", 2.4)
    blend_scale = float(doc.get("blend_scale") or 1.0)
    if success:
        blend_scale = min(blend_max, blend_scale * (1.0 + amp * 0.65))
    else:
        blend_scale = max(0.5, blend_scale * (1.0 - amp * 0.35))

    hist = list(doc.get("history") or [])
    hist.append(
        {
            "ts": time.time(),
            "symbol": sym,
            "side": side_u,
            "ret": ret,
            "success": success,
            "families": fams,
            "bars_held": bars_held,
        }
    )
    doc = {
        "updated": time.time(),
        "detectors": detectors,
        "blend_scale": blend_scale,
        "history": hist[-200:],
        "n_updates": int(doc.get("n_updates") or 0) + 1,
    }
    _save_json(WEIGHTS_PATH, doc)

    # Sequence family weights when seq reason was present
    if any(str(r).startswith("seq:") for r in (snap.get("reasons") or [])):
        try:
            from analytics.sequence_discover import update_weights

            # Lightweight Rule-like stub: only family string is used by callers that check family
            class _H:
                family = "seq"
                name = "hidden_outcome"

            seq_w = dict(doc.get("seq_family_weights") or {})
            update_weights(seq_w, _H(), success)  # type: ignore[arg-type]
            doc["seq_family_weights"] = seq_w
            _save_json(WEIGHTS_PATH, doc)
        except Exception:
            pass

    return {
        "applied": True,
        "success": success,
        "families": fams,
        "blend_scale": blend_scale,
        "detectors": {k: detectors[k] for k in fams},
    }


def blend_scale() -> float:
    doc = _load_json(WEIGHTS_PATH)
    try:
        blend_max = _f("HIDDEN_PATTERN_BLEND_SCALE_MAX", 2.4)
        return float(min(blend_max, max(0.5, float(doc.get("blend_scale") or 1.0))))
    except (TypeError, ValueError):
        return 1.0


def pattern_evidence(symbol: str) -> dict[str, Any]:
    """Raw pattern-implied probability + weight (no fuse into base — ULE owns LEA)."""
    meta: dict[str, Any] = {"applied": False}
    if not _b("USE_HIDDEN_PATTERN_ANOMALY", True):
        return meta
    w = _f("HIDDEN_ANOMALY_P_BLEND", 0.14)
    if w <= 1e-9:
        return meta
    try:
        from analytics.hidden_pattern_anomaly import load_hits

        doc = load_hits()
        age = time.time() - float(doc.get("ts") or 0)
        max_age = _f("HIDDEN_ANOMALY_MAX_AGE_SEC", 7200)
        if age > max_age:
            return {**meta, "stale": True}
        row = (doc.get("by_symbol") or {}).get(symbol.strip().upper())
        if not row:
            return meta
        score = float(row.get("score") or 0)
        direction = int(row.get("direction") or 0)
        if score < _f("HIDDEN_ANOMALY_P_BLEND_MIN_SCORE", 0.38) or direction == 0:
            return meta
        # Pattern-implied probability: 0.5 + 0.5 * direction * score
        p_pat = 0.5 + 0.5 * float(direction) * score
        w_cap = _f("HIDDEN_ANOMALY_P_BLEND_MAX", 0.35)
        w_eff = min(w_cap, w * score * blend_scale())
        return {
            "applied": True,
            "w_eff": float(w_eff),
            "p_pattern": float(p_pat),
            "score": score,
            "direction": direction,
            "reasons": list(row.get("reasons") or [])[:4],
        }
    except Exception as e:
        return {"applied": False, "error": str(e)[:120]}


def hidden_pattern_p_blend(symbol: str, p_up: float) -> tuple[float, dict[str, Any]]:
    """Soft-blend cached hidden pattern into final p_up (legacy path when ULE off)."""
    ev = pattern_evidence(symbol)
    if not ev.get("applied"):
        return float(p_up), ev
    p_pat = float(ev["p_pattern"])
    w_eff = float(ev["w_eff"])
    try:
        from analytics.vector_math import lea_enabled, logit_pair_blend

        if lea_enabled():
            p_new = logit_pair_blend(float(p_up), p_pat, w_eff)
        else:
            p_new = (1.0 - w_eff) * float(p_up) + w_eff * p_pat
    except Exception:
        p_new = (1.0 - w_eff) * float(p_up) + w_eff * p_pat
    p_new = float(min(0.99, max(0.01, p_new)))
    return p_new, {
        **ev,
        "p_before": float(p_up),
        "p_after": p_new,
        "fuse": "logit",
    }

def attach_hidden_pattern_features(df, symbol: str):
    """Attach pattern columns. Default zeros in train — live scan is not historical."""
    import pandas as pd

    if df is None or getattr(df, "empty", True):
        return df
    zeros = (
        "hidden_anomaly_score",
        "hidden_anomaly_dir",
        "hidden_pattern_blend_scale",
    )
    live = os.getenv("HIDDEN_PATTERN_BROADCAST_HISTORY", "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not live or not _b("USE_HIDDEN_PATTERN_FEATURES", True):
        df = df.copy()
        for c in zeros:
            if c not in df.columns:
                df[c] = 0.0
        return df
    score = 0.0
    direction = 0.0
    try:
        from analytics.hidden_pattern_anomaly import load_hits

        doc = load_hits()
        age = time.time() - float(doc.get("ts") or 0)
        if age <= _f("HIDDEN_ANOMALY_MAX_AGE_SEC", 7200):
            row = (doc.get("by_symbol") or {}).get(str(symbol).strip().upper())
            if row:
                score = float(row.get("score") or 0)
                direction = float(row.get("direction") or 0)
    except Exception:
        pass
    df = df.copy()
    df["hidden_anomaly_score"] = float(score)
    df["hidden_anomaly_dir"] = float(direction)
    df["hidden_pattern_blend_scale"] = float(blend_scale())
    return df


def weighted_detector_strength(
    family: str,
    raw_strength: float,
    weights: dict[str, float] | None = None,
) -> float:
    """Apply learned family weight to a raw detector strength."""
    w = weights or load_detector_weights()
    return float(raw_strength) * float(w.get(family, 1.0))
