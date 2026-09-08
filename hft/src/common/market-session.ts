/**
 * US equity session gate (mirrors analytics/market_session.py).
 * TRADE_SESSION_MODE=rth | extended | always
 */
import { CFG } from "./config.js";

export type Session = "closed" | "pre_market" | "regular" | "post_market";

function mode(name: string, fallback: string): string {
  const v = process.env[name];
  return (v == null || v === "" ? fallback : v).trim().toLowerCase();
}

function nowEtParts(): { wd: number; mins: number } {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = fmt.formatToParts(new Date());
  const wdMap: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  const wd = wdMap[parts.find((p) => p.type === "weekday")?.value ?? "Sun"] ?? 0;
  const hour = Number(parts.find((p) => p.type === "hour")?.value ?? 0);
  const minute = Number(parts.find((p) => p.type === "minute")?.value ?? 0);
  return { wd, mins: hour * 60 + minute };
}

export function currentSession(): Session {
  const { wd, mins } = nowEtParts();
  if (wd === 0 || wd === 6) return "closed";
  if (mins >= 4 * 60 && mins < 9 * 60 + 30) return "pre_market";
  if (mins >= 9 * 60 + 30 && mins < 16 * 60) return "regular";
  if (mins >= 16 * 60 && mins < 20 * 60) return "post_market";
  return "closed";
}

function inMode(sess: Session, m: string): boolean {
  if (m === "always" || m === "24x7" || m === "any") return true;
  if (m === "extended") return sess === "pre_market" || sess === "regular" || sess === "post_market";
  return sess === "regular";
}

function parseEtTime(raw: string | undefined): number | null {
  if (!raw?.trim()) return null;
  const p = raw.trim().split(":");
  if (p.length < 2) return null;
  const h = Number(p[0]);
  const m = Number(p[1]);
  if (!Number.isFinite(h) || !Number.isFinite(m)) return null;
  return h * 60 + m;
}

function withinTradeWindow(): boolean {
  const startRaw =
    process.env.HFT_TRADE_START_ET?.trim() || process.env.TRADE_START_ET?.trim();
  const endRaw = process.env.TRADE_END_ET?.trim();
  const start = parseEtTime(startRaw);
  const end = parseEtTime(endRaw);
  const { wd, mins } = nowEtParts();
  if (wd === 0 || wd === 6) return false;
  const buyMode = mode("HFT_TRADE_SESSION", mode("TRADE_SESSION_MODE", "rth"));
  // always/24x7: weekday clock window only (broker may still reject off-hours).
  if (buyMode === "always" || buyMode === "24x7" || buyMode === "any") {
    if (start != null && mins < start) return false;
    if (end != null && mins >= end) return false;
    return true;
  }
  // Weekday 24/5: prefer explicit ET window; else Alpaca extended 04:00–20:00.
  const w24 =
    process.env.TRADE_WEEKDAY_24X5 != null &&
    ["1", "true", "yes", "on"].includes(process.env.TRADE_WEEKDAY_24X5.toLowerCase());
  if (w24) {
    const winStart = start ?? 4 * 60;
    const winEnd = end ?? 20 * 60;
    if (mins < winStart || mins >= winEnd) return false;
    return true;
  }
  if (start == null && end == null) return true;
  if (start != null && mins < start) return false;
  if (end != null && mins >= end) return false;
  return true;
}

export function ordersAllowed(side: "buy" | "sell" | "any" = "buy"): boolean {
  const sess = currentSession();
  const buyMode = mode("HFT_TRADE_SESSION", mode("TRADE_SESSION_MODE", "rth"));
  const exitMode = mode("TRADE_EXIT_SESSION_MODE", buyMode);
  const blockExits = mode("TRADE_BLOCK_EXITS_UNTIL_START", "false") === "true";
  const windowOk = withinTradeWindow();
  if (!windowOk) {
    if (side === "sell" && !blockExits) {
      /* exits may still run before TRADE_START_ET */
    } else if (side !== "sell" || blockExits) {
      return false;
    }
  }
  if (side === "sell") return inMode(sess, exitMode);
  // Morning sweet spot: no new buys before ~06:00 ET (bleed zone).
  if (side === "buy" || side === "any") {
    if (mode("MORNING_SWEET_SPOT", "true") === "true") {
      const { mins } = nowEtParts();
      const start = parseHm(process.env.MORNING_SWEET_START_ET ?? "06:00", 6 * 60);
      if (sess === "pre_market" && mins < start) {
        if (mode("HFT_ALLOW_PRE_SWEET", "false") !== "true") return false;
      }
    }
  }
  if (side === "any") return inMode(sess, buyMode) || inMode(sess, exitMode);
  return inMode(sess, buyMode);
}

function parseHm(raw: string, fallbackMins: number): number {
  const m = /^(\d{1,2}):(\d{2})$/.exec(raw.trim());
  if (!m) return fallbackMins;
  return Number(m[1]) * 60 + Number(m[2]);
}

/** True when working DAY tickets must rest until they fill (no cancel→reissue). */
export function fillPersistEnabled(): boolean {
  const v = String(process.env.HFT_FILL_PERSIST ?? process.env.FILL_PERSIST ?? "true").toLowerCase();
  return v !== "false" && v !== "0" && v !== "off" && v !== "no";
}

/** Entry TIF. Fill-persist always rests DAY; IOC recycles slots but misses on IEX paper. */
export function hftLimitTif(): "day" | "ioc" {
  if (fillPersistEnabled()) return "day";
  const sess = currentSession();
  const pref = (process.env.HFT_LIMIT_TIF || "day").toLowerCase();
  if (sess !== "regular") return "day";
  return pref === "ioc" ? "ioc" : "day";
}

/** Cancel an unfilled entry only for true IOC. DAY tickets stay on the book. */
export function mayCancelUnfilled(explicit: boolean): boolean {
  if (!explicit) return false;
  if (fillPersistEnabled()) return false;
  return (process.env.HFT_LIMIT_TIF || "day").toLowerCase() === "ioc";
}

/** TTL cancel of a working DAY buy. Persist leaves it until fill or session end. */
export function shouldTtlCancelWorking(): boolean {
  if (fillPersistEnabled()) return false;
  const maxMs = Number(process.env.HFT_ENTRY_WORKING_TTL_MS ?? 180_000);
  return Number.isFinite(maxMs) && maxMs > 0;
}

/** Exits must rest. IOC max-hold retries burned the 200/min cap and 429'd Alpaca. */
export function hftExitTif(): "day" | "ioc" {
  const pref = (process.env.HFT_EXIT_TIF || "day").toLowerCase();
  return pref === "ioc" ? "ioc" : "day";
}

/** Send Alpaca extended_hours=true only in pre/post — not all day. */
export function hftExtendedHoursFlag(): boolean {
  if (process.env.HFT_EXTENDED_HOURS === "false") return false;
  const sess = currentSession();
  return sess === "pre_market" || sess === "post_market";
}

/** No-op export so CFG import isn't tree-shaken in bundlers that care. */
void CFG;
