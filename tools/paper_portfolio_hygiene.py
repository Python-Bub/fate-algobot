#!/usr/bin/env python3
"""One pass: cut shorts, losers, and off-quality holdings on Alpaca paper."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
_deploy = ROOT / "data" / "deploy_scale.env"
if _deploy.is_file():
    load_dotenv(_deploy, override=True)

from fortress_portfolio import paper_portfolio_hygiene
from utils import log


def main() -> None:
    r = paper_portfolio_hygiene()
    log.info("[HYGIENE] %s", r)


if __name__ == "__main__":
    main()
