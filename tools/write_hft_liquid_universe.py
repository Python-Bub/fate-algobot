#!/usr/bin/env python3
"""Write data/ops/hft_rest_tickers.txt — liquid names HFT can rotate (not already held).

Alpaca IEX WS is capped ~15 symbols; overflow is REST. 200 orders/min needs many
names so we never retry the same cancelled IOC. Does not shrink the train universe.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = Path(os.getenv("HFT_REST_TICKERS_FILE", str(ROOT / "data" / "ops" / "hft_rest_tickers.txt")))

# Liquid single-names HFT can actually fill — not the fortress mega-cap book.
# Cheap names first: 15¢ TP ticks clear IEX spread (edge-cost). Expensive
# names (INTU/NOW) skip-all because 15 ticks is only a few bps.
_LIQUID = (
    "SOFI,MARA,RIOT,NIO,LCID,RIVN,HOOD,SNAP,ROKU,AAL,F,T,PFE,KEY,RF,HBAN,"
    "DAL,UAL,LUV,CCL,NCLH,MGM,WYNN,HAL,SLB,OXY,INTC,CSCO,BA,GE,C,WFC,USB,"
    "PINS,U,PATH,NU,GOLD,GM,RCL,MAR,HLT,PNC,SCHW,PYPL,DIS,NKE,IBM,ORCL,"
    "INTU,NOW,PANW,CRWD,PLTR,COIN,UBER,ABNB,SHOP,CAT,RTX,HON,DE,UNH,LLY,"
    "PEP,AMAT,LRCX,KLAC,ADI,TXN,AVGO,CRM,ADBE,SNOW,NET,DDOG,ZS,OKTA,TEAM,"
    "WDAY,XYZ,MELI,SE,ARM,APP,SMCI,MSTR,MDB,TTD,ZG,BKNG,"
    "CVX,COP,MPC,VLO,PSX,MRK,ABBV,BMY,GILD,AMGN,REGN,VRTX,ISRG,SYK,BSX,"
    "MDT,TMO,DHR,ELV,CI,HUM,CVS,COST,TGT,HD,LOW,SBUX,MCD,CMG,YUM,"
    "AXP,V,MA,BLK,GS,MS,ICE,CME,SPGI,MCO,NDAQ,UNP,UPS,FDX,CSX,NSC,LMT,NOC,GD"
)


def _held() -> set[str]:
    out: set[str] = set()
    try:
        from alpaca_broker import list_positions

        for p in list_positions() or []:
            s = str(p.get("symbol") or "").replace("/", "-").upper()
            if s and float(p.get("qty") or 0) > 0:
                out.add(s)
    except Exception:
        pass
    return out


def _banned() -> set[str]:
    raw = os.getenv(
        "HFT_BAN_INDEX_ETFS",
        os.getenv("FORTRESS_BAN_INDEX_ETFS", "SPY,QQQ,IWM,DIA,VOO,VTI,SOXX,XLK,XLF,XLE"),
    )
    return {s.strip().upper() for s in raw.split(",") if s.strip()}


def write_file(*, cap: int = 120) -> Path:
    held = _held()
    banned = _banned()
    seen: set[str] = set()
    ordered: list[str] = []

    extra = [s.strip().upper() for s in _LIQUID.split(",") if s.strip()]
    top: list[str] = []
    try:
        from fortress_universe import load_top100_symbols

        top = [str(s).upper() for s in load_top100_symbols()]
    except Exception:
        pass

    for s in extra + top:
        if not s or s in seen or s in banned or s in held:
            continue
        seen.add(s)
        ordered.append(s)
        if len(ordered) >= cap:
            break

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(",".join(ordered) + "\n", encoding="utf-8")
    return OUT


def main() -> int:
    path = write_file(cap=int(os.getenv("HFT_REST_TICKER_CAP", "120")))
    n = len(path.read_text(encoding="utf-8").split(","))
    print(f"[hft-universe] {n} rest tickers → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
