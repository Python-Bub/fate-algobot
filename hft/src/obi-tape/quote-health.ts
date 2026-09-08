/**
 * Dirty-data / stale-quote filter for the OBI hot path.
 *
 * Separates software/data bugs from execution slippage: reject impossible or
 * aged quotes before any strategy decision or simulated fill.
 */
import type { L2Book } from "./l2-book.js";

export type QuoteRejectReason = "stale" | "crossed" | "shock" | "invalid";

export interface QuoteHealth {
  ok: boolean;
  reason?: QuoteRejectReason;
  detail?: string;
  ageMs?: number;
  moveBps?: number;
  /** Always true for a valid NBBO — caller must refresh fair-value even on skip. */
  adoptMid?: boolean;
}

function maxQuoteAgeMs(): number {
  return Number(process.env.HFT_MAX_QUOTE_AGE_MS ?? 2500);
}

function maxShockBps(): number {
  return Number(process.env.HFT_MAX_MID_SHOCK_BPS ?? 500);
}

function skipQuoteHealth(): boolean {
  return process.env.HFT_SKIP_QUOTE_HEALTH === "true";
}

/** Reject crossed or empty books before OBI / MR decisions. */
export function assessQuoteHealth(
  book: L2Book,
  exchangeTsMs: number,
  prevMid?: number,
): QuoteHealth {
  if (skipQuoteHealth()) return { ok: true, adoptMid: true };

  if (!(book.bestBid > 0 && book.bestAsk > 0 && book.mid > 0)) {
    return { ok: false, reason: "invalid", detail: "missing_nbbo", adoptMid: false };
  }
  if (book.bestAsk < book.bestBid) {
    return {
      ok: false,
      reason: "crossed",
      detail: `bid=${book.bestBid} ask=${book.bestAsk}`,
      adoptMid: false,
    };
  }

  const nowMs = Date.now();
  // Prefer the fresher of exchange vs local receive. Alpaca IEX WS often sends
  // `t` as an ISO string; `Number(iso)` → NaN left lastExchangeTsMs stuck while
  // lastUpdateMs kept updating — every quote rejected as "stale" (~hours old).
  const refTs = Math.max(
    exchangeTsMs > 0 && Number.isFinite(exchangeTsMs) ? exchangeTsMs : 0,
    book.lastUpdateMs > 0 ? book.lastUpdateMs : 0,
  );
  if (refTs > 0) {
    const ageMs = Math.max(0, nowMs - refTs);
    if (ageMs > maxQuoteAgeMs()) {
      return { ok: false, reason: "stale", detail: "quote_age", ageMs, adoptMid: false };
    }
  }

  if (prevMid != null && prevMid > 0 && book.mid > 0) {
    const moveBps = (Math.abs(book.mid - prevMid) / prevMid) * 10_000;
    const spr =
      book.bestAsk > book.bestBid && book.mid > 0
        ? ((book.bestAsk - book.bestBid) / book.mid) * 10_000
        : Number.POSITIVE_INFINITY;
    const ageMs = refTs > 0 ? Math.max(0, nowMs - refTs) : 0;
    // Isolated bad tick: huge jump AND a wide/crossed book. A 6% session drift
    // vs a sticky lastGoodMid is NOT a shock — locking lastGoodMid was why
    // MELI/SE/MRK were quote-rejected thousands of times with the same bps.
    const wide = spr > Number(process.env.HFT_SHOCK_WIDE_SPREAD_BPS ?? 80);
    if (moveBps > maxShockBps() && wide) {
      return {
        ok: false,
        reason: "shock",
        detail: "mid_jump",
        moveBps,
        ageMs,
        adoptMid: false,
      };
    }
    if (moveBps > maxShockBps() && !wide) {
      return { ok: true, moveBps, ageMs, adoptMid: true, detail: "gap_adopt" };
    }
  }

  return {
    ok: true,
    ageMs: refTs > 0 ? Math.max(0, nowMs - refTs) : undefined,
    adoptMid: true,
  };
}
