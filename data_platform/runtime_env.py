"""Layered dotenv: files last-wins among themselves, process env always wins.

`.env` is the base. `data/deploy_scale.env` overrides `.env` so the Mac observe /
GCP paper split stays last-wins in files. Keys already present in ``os.environ``
(operator export, Cloud/container env, pytest monkeypatch) are never overwritten.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]


def layered_dotenv_values() -> dict[str, str]:
    """Merge ``.env`` then ``data/deploy_scale.env`` (later file wins)."""
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}
    layered: dict[str, str] = {}
    for path in (ROOT / ".env", ROOT / "data" / "deploy_scale.env"):
        if not path.is_file():
            continue
        try:
            vals = dotenv_values(path) or {}
        except Exception:
            continue
        for key, val in vals.items():
            if val is None:
                continue
            layered[str(key)] = str(val)
    return layered


def load_runtime_env(*, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Apply layered file env without clobbering process / test pins.

    Returns the keys that were newly written into ``os.environ``.
    """
    dest = os.environ if environ is None else environ  # type: ignore[assignment]
    preexisting = set(dest.keys())
    applied: dict[str, str] = {}
    for key, val in layered_dotenv_values().items():
        if key in preexisting:
            continue
        dest[key] = val
        applied[key] = val
    return applied
