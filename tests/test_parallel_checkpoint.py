"""Checkpoint persist must not crash the writer (overnight train stall)."""
from __future__ import annotations

import json
from pathlib import Path

from parallel_train import _atomic_write_json, _load_checkpoint


def test_atomic_write_json_roundtrip(tmp_path, monkeypatch):
    dest = tmp_path / "intraday_train_checkpoint.json"
    monkeypatch.setattr("parallel_train.ROOT", tmp_path)
    payload = {"done": ["AAPL", "MSFT"], "failed": {"ZZZ": "skip"}}
    _atomic_write_json(dest, payload)
    assert dest.is_file()
    assert not list(tmp_path.glob(".*.tmp"))
    done, failed = _load_checkpoint(str(dest))
    assert done == {"AAPL", "MSFT"}
    assert failed == {"ZZZ": "skip"}


def test_atomic_write_json_overwrites(tmp_path):
    dest = tmp_path / "train_checkpoint.json"
    _atomic_write_json(dest, {"done": ["A"], "failed": {}})
    _atomic_write_json(dest, {"done": ["A", "B"], "failed": {}})
    data = json.loads(Path(dest).read_text(encoding="utf-8"))
    assert data["done"] == ["A", "B"]
