"""Four-chart HFT pattern stack (candlestick, line, HLOC bar, point-and-figure).

Mirrors ``hft/src/obi-tape/advanced-charts.ts``. No lookahead: vote at bar i
uses only bars[:i+1].

Votes are event-driven (pattern just formed). Live bias requires cross-family
agreement: bar geometry (candle or HLOC) AND close-path (line or PnF).

Literature: raw candlesticks ≈ coin-flip. We keep them as one vote among four
and amplify only when they agree with a different encoding of the same tape.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ChartVote:
    candle: float
    line: float
    hloc: float
    pnf: float
    hidden: float
    score: float
    n_agree: int
    cross_family: bool
    bias: int


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return float(max(lo, min(hi, x)))


def _sign3(x: float, eps: float = 0.08) -> int:
    if x > eps:
        return 1
    if x < -eps:
        return -1
    return 0


def _sma_at(c: np.ndarray, end: int, win: int) -> float:
    w = min(win, end + 1)
    if w <= 0:
        return 0.0
    return float(np.mean(c[end + 1 - w : end + 1]))


def candle_vote(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, i: int, jp_bias: int = 0) -> float:
    if i < 1:
        return 0.0
    o1, h1, l1, c1 = float(o[i]), float(h[i]), float(l[i]), float(c[i])
    o0, h0, l0, c0 = float(o[i - 1]), float(h[i - 1]), float(l[i - 1]), float(c[i - 1])
    rng = h1 - l1
    if rng <= 0 or c1 <= 0:
        return jp_bias * 0.55 if jp_bias else 0.0
    body = abs(c1 - o1)
    upper = h1 - max(o1, c1)
    lower = min(o1, c1) - l1
    green = c1 >= o1
    v = 0.0
    if jp_bias:
        v += jp_bias * 0.55
    if body / rng > 0.85 and upper / rng < 0.08 and lower / rng < 0.08:
        v += 0.45 if green else -0.45
    if lower / rng > 0.6 and body / rng < 0.35 and upper / rng < 0.15:
        v += 0.4
    if upper / rng > 0.6 and body / rng < 0.35 and lower / rng < 0.15:
        v -= 0.4
    body0 = abs(c0 - o0)
    if c0 < o0 and c1 > o1 and o1 <= c0 and c1 >= o0 and body > body0:
        v += 0.42
    if c0 > o0 and c1 < o1 and o1 >= c0 and c1 <= o0 and body > body0:
        v -= 0.42
    mid0 = (o0 + c0) / 2.0
    if c0 < o0 and c1 > o1 and o1 < c0 and c1 > mid0:
        v += 0.32
    if c0 > o0 and c1 < o1 and o1 > c0 and c1 < mid0:
        v -= 0.32
    if c1 > 0 and abs(l1 - l0) / c1 < 0.0015 and c0 < o0 and green:
        v += 0.22
    if c1 > 0 and abs(h1 - h0) / c1 < 0.0015 and c0 > o0 and not green:
        v -= 0.22
    if (
        body0 > 0
        and body < 0.5 * body0
        and max(o1, c1) < max(o0, c0)
        and min(o1, c1) > min(o0, c0)
    ):
        v *= 0.35
    if i >= 2:
        o2, c2 = float(o[i - 2]), float(c[i - 2])
        g2, g1, g0 = c2 > o2, c0 > o0, green
        if g2 and g1 and g0 and c1 > c0 > c2:
            v += 0.35
        if (not g2) and (not g1) and (not g0) and c1 < c0 < c2:
            v -= 0.35
        h2, l2 = float(h[i - 2]), float(l[i - 2])
        body2 = abs(c2 - o2)
        rng2 = h2 - l2
        small1 = abs(c0 - o0) < 0.35 * max(body2, rng2 * 0.4)
        if c2 < o2 and small1 and green and c1 > (o2 + c2) / 2.0:
            v += 0.38
        if c2 > o2 and small1 and not green and c1 < (o2 + c2) / 2.0:
            v -= 0.38
    return _clamp(v)


def line_vote(c: np.ndarray, i: int) -> float:
    if i < 9:
        return 0.0
    last = float(c[i])
    prev = float(c[i - 1])
    if last <= 0 or prev <= 0:
        return 0.0
    v = 0.0
    s8 = _sma_at(c, i, 8)
    s21 = _sma_at(c, i, 21)
    p8 = _sma_at(c, i - 1, 8)
    p21 = _sma_at(c, i - 1, 21)
    if p8 <= p21 and s8 > s21:
        v += 0.42
    if p8 >= p21 and s8 < s21:
        v -= 0.42
    lb = min(20, i - 1)
    if lb >= 8:
        window = c[i - lb : i]
        hi = float(np.max(window))
        lo = float(np.min(window))
        if last > hi and prev < hi:
            v += 0.45
        if last < lo and prev > lo:
            v -= 0.45
    if i >= 21 and s8 > s21 and prev < p8 and last > s8:
        v += 0.28
    if i >= 21 and s8 < s21 and prev > p8 and last < s8:
        v -= 0.28
    return _clamp(v)


def hloc_vote(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, i: int) -> float:
    if i < 2:
        return 0.0
    o1, h1, l1, c1 = float(o[i]), float(h[i]), float(l[i]), float(c[i])
    o0, h0, l0, c0 = float(o[i - 1]), float(h[i - 1]), float(l[i - 1]), float(c[i - 1])
    rng = h1 - l1
    if rng <= 0:
        return 0.0
    v = 0.0
    inside = h1 < h0 and l1 > l0
    outside = h1 > h0 and l1 < l0
    if c0 < o0 and c1 > h0:
        v += 0.5
    if c0 > o0 and c1 < l0:
        v -= 0.5
    if outside:
        v += 0.32 if c1 > o1 else -0.32
    if i >= 3:
        mother_h, mother_l = float(h[i - 2]), float(l[i - 2])
        was_inside = h0 < mother_h and l0 > mother_l
        if was_inside and c1 > mother_h:
            v += 0.4
        if was_inside and c1 < mother_l:
            v -= 0.4
    if inside:
        v *= 0.15
    if i >= 7:
        r1 = rng
        prior = h[i - 7 : i] - l[i - 7 : i]
        if float(np.min(prior)) > 0 and r1 < float(np.min(prior)):
            v += 0.28 if c1 > o1 else -0.28
    return _clamp(v)


class PointAndFigure:
    def __init__(self, box_pct: float = 0.002, reversal: int = 3) -> None:
        self.box_pct = float(box_pct)
        self.reversal = max(1, int(reversal))
        self.dir = 0
        self.col_high = 0.0
        self.col_low = 0.0
        self.last_px = 0.0
        self.x_highs: list[float] = []
        self.o_lows: list[float] = []

    def reset(self) -> None:
        self.dir = 0
        self.col_high = 0.0
        self.col_low = 0.0
        self.last_px = 0.0
        self.x_highs.clear()
        self.o_lows.clear()

    def _box(self, px: float) -> float:
        return max(px * self.box_pct, 0.01)

    def on_close(self, px: float) -> float:
        if px <= 0:
            return 0.0
        box = self._box(px)
        prev_dir = self.dir
        prev_high = self.col_high
        prev_low = self.col_low
        if self.dir == 0:
            if self.last_px > 0:
                if px >= self.last_px + box:
                    self.dir = 1
                    self.col_high = px
                    self.col_low = self.last_px
                elif px <= self.last_px - box:
                    self.dir = -1
                    self.col_low = px
                    self.col_high = self.last_px
            self.last_px = px
            return float(self.dir) * 0.4 if self.dir else 0.0
        rev = self.reversal * box
        reversed_col = False
        if self.dir > 0:
            if px > self.col_high:
                self.col_high = px
            elif px <= self.col_high - rev:
                self.x_highs.append(self.col_high)
                self.x_highs = self.x_highs[-6:]
                self.dir = -1
                self.col_low = px
                reversed_col = True
        else:
            if px < self.col_low or self.col_low == 0:
                self.col_low = px
            elif px >= self.col_low + rev:
                self.o_lows.append(self.col_low)
                self.o_lows = self.o_lows[-6:]
                self.dir = 1
                self.col_high = px
                reversed_col = True
        self.last_px = px
        v = 0.0
        if reversed_col:
            v += self.dir * 0.7
        if self.dir > 0 and self.x_highs:
            prior = max(self.x_highs)
            if self.col_high > prior and prev_high <= prior:
                v += 0.45
        if self.dir < 0 and self.o_lows:
            prior = min(self.o_lows)
            if self.col_low < prior and (prev_low >= prior or prev_dir >= 0):
                v -= 0.45
        if self.dir > 0 and len(self.x_highs) >= 2:
            a, b = self.x_highs[-1], self.x_highs[-2]
            if a > 0 and abs(a - b) / a < 0.004 and self.col_high > max(a, b) and prev_high <= max(a, b):
                v += 0.25
        return _clamp(v)


def hidden_vote(candle: float, line: float, hloc: float, pnf: float) -> tuple[float, int]:
    signs = [_sign3(candle), _sign3(line), _sign3(hloc), _sign3(pnf)]
    up = sum(1 for s in signs if s > 0)
    down = sum(1 for s in signs if s < 0)
    n_agree = max(up, down)
    direction = 1 if up > down else (-1 if down > up else 0)
    if n_agree < 2 or direction == 0:
        return 0.0, n_agree
    amp = 0.85 if n_agree >= 4 else (0.55 if n_agree >= 3 else 0.28)
    hidden = direction * amp
    if _sign3(candle) and _sign3(pnf) and _sign3(candle) != _sign3(pnf):
        hidden *= 0.25
    return hidden, n_agree


def cross_family_agree(candle: float, line: float, hloc: float, pnf: float) -> bool:
    bar_up = _sign3(candle) > 0 or _sign3(hloc) > 0
    bar_dn = _sign3(candle) < 0 or _sign3(hloc) < 0
    path_up = _sign3(line) > 0 or _sign3(pnf) > 0
    path_dn = _sign3(line) < 0 or _sign3(pnf) < 0
    bar_dir = 1 if bar_up and not bar_dn else (-1 if bar_dn and not bar_up else 0)
    path_dir = 1 if path_up and not path_dn else (-1 if path_dn and not path_up else 0)
    return bar_dir != 0 and bar_dir == path_dir


def fuse_votes(candle: float, line: float, hloc: float, pnf: float) -> ChartVote:
    hidden, n_agree = hidden_vote(candle, line, hloc, pnf)
    cross = cross_family_agree(candle, line, hloc, pnf)
    raw = 0.22 * candle + 0.22 * line + 0.22 * hloc + 0.22 * pnf + 0.12 * hidden
    score = _clamp(raw if cross else raw * 0.2)
    return ChartVote(
        candle=candle,
        line=line,
        hloc=hloc,
        pnf=pnf,
        hidden=hidden,
        score=score,
        n_agree=n_agree,
        cross_family=cross,
        bias=_sign3(score, 0.12) if cross else 0,
    )


def vote_series(
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    c: np.ndarray,
    *,
    box_pct: float = 0.002,
    jp_bias: np.ndarray | None = None,
) -> list[ChartVote]:
    """Walk-forward votes for every bar (index 0 is the first bar)."""
    n = len(c)
    pnf = PointAndFigure(box_pct=box_pct)
    out: list[ChartVote] = []
    for i in range(n):
        jb = int(jp_bias[i]) if jp_bias is not None and i < len(jp_bias) else 0
        candle = candle_vote(o, h, l, c, i, jb)
        line = line_vote(c, i)
        hloc = hloc_vote(o, h, l, c, i)
        p = pnf.on_close(float(c[i]))
        out.append(fuse_votes(candle, line, hloc, p))
    return out


def chart_prob(vote: ChartVote | None) -> float:
    if vote is None or not vote.cross_family:
        return 0.5
    scale = 0.38 if vote.n_agree >= 3 else 0.28
    return float(max(0.0, min(1.0, 0.5 + vote.score * scale)))
