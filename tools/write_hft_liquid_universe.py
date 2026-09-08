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
_LIQUID = (
    "INTU,NOW,PANW,CRWD,PLTR,COIN,UBER,ABNB,SHOP,BA,CAT,GE,RTX,HON,DE,UNH,LLY,"
    "PEP,DIS,NKE,PYPL,IBM,ORCL,CSCO,INTC,AMAT,LRCX,KLAC,ADI,TXN,AVGO,CRM,ADBE,"
    "SNOW,NET,DDOG,ZS,OKTA,TEAM,WDAY,SQ,XYZ,MELI,SE,ARM,APP,SMCI,HOOD,SOFI,"
    "RIVN,LCID,NIO,MARA,RIOT,MSTR,COIN,ROKU,SNAP,PINS,U,PATH,CFLT,ESTC,MDB,"
    "TTD,ZG,BKNG,ABNB,DAL,UAL,AAL,LUV,F,GM,RCL,MAR,HLT,NCLH,CCL,WYNN,MGM,"
    "CVX,COP,SLB,HAL,OXY,MPC,VLO,PSX,PFE,MRK,ABBV,BMY,GILD,AMGN,REGN,VRTX,"
    "ISRG,SYK,BSX,MDT,TMO,DHR,UNH,ELV,CI,HUM,CVS,WBA,COST,TGT,HD,LOW,NKE,"
    "SBUX,MCD,CMG,YUM,BKNG,AXP,V,MA,BLK,GS,MS,C,WFC,USB,PNC,SCHW,ICE,CME,"
    "SPGI,MCO,ICE,NDAQ,DE,CAT,GE,HON,UNP,UPS,FDX,CSX,NSC,BA,LMT,NOC,GD,RTX"
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


def write_file(*, cap: int = 80) -> Path:
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
    path = write_file(cap=int(os.getenv("HFT_REST_TICKER_CAP", "80")))
    n = len(path.read_text(encoding="utf-8").split(","))
    print(f"[hft-universe] {n} rest tickers → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
