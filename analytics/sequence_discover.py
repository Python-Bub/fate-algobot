"""Discover sequence patterns from data alone — no named/hardcoded pattern methods.

FATE integration: copied from the author's guess_patterns.py (selftrader project)
and used as math machinery for return/price-structure discovery. Rank impact is
gated through analytics.structure_patterns (small weight, validated excess only).

Only general machinery:
  1. Read structure (steps, ratios, factorizations)
  2. Fit polynomials from differences
  3. Fit geometric ratios
  4. Discover linear recurrences from data
  5. Detect cycles
  6. Decompose terms as base^exp and discover each side separately
  7. Evolve expression trees when closed forms aren't found

Pure Python stdlib.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


def _close(a: float, b: float, rel: float = 0.01) -> bool:
    return math.isclose(a, b, rel_tol=rel, abs_tol=1e-4)


def fmt(x: float) -> str:
    if math.isfinite(x) and abs(x - round(x)) < 1e-6:
        v = int(round(x))
        return str(v) if abs(v) < 10**14 else f"{v:.6e}"
    return f"{x:g}"


# ---------------------------------------------------------------------------
# General math helpers
# ---------------------------------------------------------------------------

def _solve_linear(system: list[list[float]]) -> list[float] | None:
    if not system:
        return None
    n = len(system)
    m = len(system[0])
    aug = [row[:] for row in system]
    cols = m - 1
    for col in range(cols):
        if col >= n:
            break
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]) if col < len(aug[r]) else 0)
        if col >= len(aug[pivot]) or abs(aug[pivot][col]) < 1e-12:
            continue
        aug[col], aug[pivot] = aug[pivot], aug[col]
        div = aug[col][col]
        aug[col] = [v / div for v in aug[col]]
        for row in range(n):
            if row != col and col < len(aug[row]) and abs(aug[row][col]) > 1e-12:
                f = aug[row][col]
                aug[row] = [aug[row][j] - f * aug[col][j] for j in range(m)]
    sol = []
    for i in range(cols):
        if i < n and i < len(aug[i]) and abs(aug[i][i] if i < len(aug[i]) - 1 else 0) > 1e-9:
            sol.append(aug[i][m - 1])
        else:
            sol.append(0.0)
    return sol


def _is_constant(seq: list[float]) -> bool:
    if not seq:
        return False
    scale = max(abs(seq[0]), 1.0)
    return all(_close(seq[i], seq[0], rel=1e-4 / scale) for i in range(len(seq)))


def _poly_degree(nums: list[float]) -> int | None:
    d = list(nums)
    for degree in range(len(nums)):
        if len(d) <= 1 or _is_constant(d):
            return degree
        d = [d[i + 1] - d[i] for i in range(len(d) - 1)]
    return None


def _fit_poly_coeffs(nums: list[float], degree: int) -> list[float] | None:
    if len(nums) <= degree:
        return None
    rows = [[i ** j for j in range(degree + 1)] + [y] for i, y in enumerate(nums)]
    return _solve_linear(rows)


def _poly_eval(c: list[float], n: int) -> float:
    return sum(co * (n ** j) for j, co in enumerate(c))


def _poly_str(c: list[float]) -> str:
    parts = []
    for j, co in enumerate(c):
        if abs(co) < 1e-9:
            continue
        if j == 0:
            parts.append(fmt(co))
        elif j == 1:
            parts.append(f"{fmt(co)}·n" if abs(co - 1) > 1e-9 else "n")
        else:
            parts.append(f"{fmt(co)}·n^{j}" if abs(co - 1) > 1e-9 else f"n^{j}")
    return " + ".join(parts).replace("+ -", "- ") or "0"


def _integer_factor_power(val: float) -> tuple[int, int] | None:
    """If val = b^e for integers b>=2, e>=2, return (b, e). No special cases."""
    if not math.isfinite(val):
        return None
    xi = int(round(val))
    if xi < 4 or not _close(val, xi):
        return None
    for b in range(2, min(500, xi) + 1):
        e = 2
        while b ** e <= xi:
            if b ** e == xi:
                return b, e
            e += 1
    return None


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------

@dataclass
class Rule:
    name: str
    predict: object
    family: str
    reason: str
    score: float = 0.0
    complexity: float = 1.0

    def value(self, n: int) -> float:
        return float(self.predict(n))  # type: ignore


@dataclass
class SearchResult:
    best: Rule
    runner_up: Rule | None
    tried: int
    thoughts: list[str]
    next_val: float


def _score(rule: Rule, nums: list[float]) -> float:
    err = 0.0
    exact = True
    for i, y in enumerate(nums):
        p = rule.value(i)
        if not math.isfinite(p):
            return float("inf")
        d = abs(p - y)
        if not _close(p, y):
            exact = False
        err += d + (d * 12 if not _close(p, y) else 0)
    if exact:
        return rule.complexity * 0.1
    return err + rule.complexity * 0.15


def _is_exact(rule: Rule, nums: list[float]) -> bool:
    return _score(rule, nums) < 0.5


def _recurrence_fits(nums: list[float], order: int) -> bool:
    n = len(nums)
    if n <= order:
        return False
    rows = [[nums[i - j] for j in range(1, order + 1)] + [nums[i]] for i in range(order, n)]
    coeffs = _solve_linear(rows)
    if coeffs is None:
        return False
    return all(
        _close(sum(coeffs[j] * nums[i - j - 1] for j in range(order)), nums[i])
        for i in range(order, n)
    )


def _discover_target_ratio(nums: list[float]) -> float | None:
    """General ratio continuation — no named pattern labels."""
    if len(nums) < 2:
        return None
    ratios = [nums[i + 1] / nums[i] for i in range(len(nums) - 1) if abs(nums[i]) > 1e-12]
    if not ratios:
        return None
    if _is_constant(ratios):
        return ratios[0]
    log_r = [math.log(abs(r)) for r in ratios]
    if len(log_r) >= 2:
        drift = abs(log_r[-1] - log_r[-2])
        scale = max(abs(log_r[-1]), abs(log_r[-2]), 1.0)
        if drift < max(0.5, 0.12 * scale):
            return ratios[-2]
    if len(log_r) >= 3:
        cap = min(1, len(log_r) - 2)
        c = _fit_poly_coeffs(log_r, cap)
        if c is not None:
            return math.exp(_poly_eval(c, len(log_r)))
    return ratios[-1]


def _discover_gap_next(bases: list[float]) -> tuple[float, str] | None:
    """Extrapolate next base via general gap hypotheses. Returns (base, reason)."""
    if len(bases) < 2:
        return None
    gaps = [bases[i + 1] - bases[i] for i in range(len(bases) - 1)]
    candidates: list[tuple[float, float, str]] = []

    def add(gap: float, complexity: float, reason: str) -> None:
        if gap > 0 and math.isfinite(gap):
            candidates.append((bases[-1] + gap, complexity, reason))

    add(gaps[-1], 1.0, f"repeat last gap {fmt(gaps[-1])}")
    if len(gaps) >= 2:
        add(2 * gaps[-1] - gaps[-2], 1.5, f"linear gap step {fmt(2 * gaps[-1] - gaps[-2])}")
        add(gaps[-1] + gaps[-2], 1.5, f"sum of last two gaps {fmt(gaps[-1] + gaps[-2])}")
        if _close(gaps[-1], gaps[-2]):
            add(gaps[-1] + gaps[-2], 0.8, f"equal tail gaps → add them → {fmt(gaps[-1] + gaps[-2])}")

    for deg in range(min(2, len(gaps) - 1)):
        gdeg = _poly_degree(gaps)
        if gdeg is None or gdeg > deg:
            continue
        gc = _fit_poly_coeffs(gaps, gdeg)
        if gc is not None:
            ng = _poly_eval(gc, len(gaps))
            add(ng, gdeg + 1.5, f"gap polynomial degree {gdeg} → {fmt(ng)}")

    for order in range(1, min(4, len(gaps))):
        rows = [[gaps[i - j - 1] for j in range(order)] + [gaps[i]] for i in range(order, len(gaps))]
        if len(rows) < order:
            continue
        coeffs = _solve_linear(rows)
        if coeffs is None:
            continue
        if not all(
            _close(sum(coeffs[j] * gaps[i - j - 1] for j in range(order)), gaps[i])
            for i in range(order, len(gaps))
        ):
            continue
        ng = sum(coeffs[j] * gaps[-(j + 1)] for j in range(order))
        terms = " + ".join(f"{fmt(coeffs[j])}·g(n-{j+1})" for j in range(order))
        add(ng, order + 2, f"gap recurrence {terms} → {fmt(ng)}")

    if len(gaps) >= 2:
        for order in range(1, 3):
            for coeffs in ((1, 1), (1, 0), (0, 2), (2, -1), (2, -2)):
                cs = list(coeffs[:order])
                if not all(
                    _close(sum(cs[j] * gaps[i - j - 1] for j in range(order)), gaps[i])
                    for i in range(order, len(gaps))
                ):
                    continue
                ng = sum(cs[j] * gaps[-(j + 1)] for j in range(order))
                add(ng, order + sum(abs(c) for c in cs) * 0.1, f"small-int gap coeffs {cs} → {fmt(ng)}")

    if not candidates:
        return None

    best_base, best_score, best_reason = None, float("inf"), ""
    for base, complexity, reason in candidates:
        b = int(round(base))
        if b <= int(round(bases[-1])):
            continue
        ext = bases + [float(b)]
        score = complexity
        if _recurrence_fits(ext, 2):
            score += 10.0
        if score < best_score:
            best_base, best_score, best_reason = float(b), score, reason
    if best_base is None:
        return None
    return best_base, best_reason


def _extrapolate_next_base(
    bases: list[float],
    nums: list[float],
    exp_predict,
) -> tuple[float, str]:
    """Pick the next integer base by structural fit — no named patterns."""
    last = int(round(bases[-1]))

    gap_hit = _discover_gap_next(bases)
    if gap_hit is not None:
        base, reason = gap_hit
        if base > last:
            return float(int(round(base))), reason

    # Fallback: score integer candidates
    log_terms = [math.log(abs(v)) for v in nums if v > 0]
    target_log = None
    if len(log_terms) >= 2:
        cap = min(2, len(log_terms) - 1)
        deg = _poly_degree(log_terms)
        if deg is not None and deg <= cap:
            c = _fit_poly_coeffs(log_terms, deg)
            if c is not None:
                target_log = _poly_eval(c, len(log_terms))

    best_b, best_score = None, float("inf")
    for b in range(last + 1, last + 80):
        e = float(exp_predict(b))
        if not math.isfinite(e) or e < 1:
            continue
        term = float(int(b) ** int(round(e)))
        score = 0.0

        if target_log is not None:
            score += abs(math.log(term) - target_log)

        ext = bases + [float(b)]
        if _recurrence_fits(ext, 2):
            score += 8.0
        if _recurrence_fits(ext, 1) and len(ext) >= 4:
            score += 3.0

        score += 0.001 * (b - last)
        if score < best_score:
            best_b, best_score = b, score
    b = best_b if best_b is not None else last + 1
    return float(b), "integer search on log-term fit"


# ---------------------------------------------------------------------------
# General discoverers (no named patterns)
# ---------------------------------------------------------------------------

def _discover_polynomial(nums: list[float], max_degree: int | None = None) -> tuple[Rule, list[str]] | None:
    deg = _poly_degree(nums)
    if deg is None:
        return None
    cap = max_degree if max_degree is not None else min(deg, max(1, len(nums) - 2))
    if deg > cap:
        return None
    c = _fit_poly_coeffs(nums, deg)
    if c is None:
        return None
    for i, y in enumerate(nums):
        if not _close(_poly_eval(c, i), y):
            return None
    if deg == 0:
        label = f"constant {fmt(c[0])}"
    elif deg == 1:
        label = f"linear: {_poly_str(c)}"
    else:
        label = f"degree-{deg} polynomial: {_poly_str(c)}"
    thoughts = [
        f"  • Differences level {deg} is flat → polynomial of degree {deg}",
        f"  • Coefficients: {_poly_str(c)}",
    ]
    return Rule(label, lambda n, cc=c: _poly_eval(cc, n), "polynomial", "difference calculus", complexity=deg + 1), thoughts


def _discover_geometric(nums: list[float]) -> tuple[Rule, list[str]] | None:
    if len(nums) < 2 or abs(nums[0]) < 1e-12:
        return None
    r = nums[1] / nums[0]
    if not all(abs(nums[i - 1]) > 1e-12 and _close(nums[i] / nums[i - 1], r) for i in range(2, len(nums))):
        return None
    a0 = nums[0]
    thoughts = [f"  • Ratios between terms are all ≈ {fmt(r)}", f"  • f(n) = {fmt(a0)} · {fmt(r)}^n"]
    return Rule(f"ratio ×{fmt(r)}", lambda n, a=a0, rr=r: a * rr ** n, "geometric", "ratio analysis", complexity=1.0), thoughts


def _discover_recurrence(nums: list[float], max_order: int = 4, min_margin: int = 1) -> tuple[Rule, list[str]] | None:
    """General linear recurrence — no Fibonacci/prime labels."""
    n = len(nums)
    best: tuple[Rule, list[str]] | None = None
    best_score = float("inf")

    for order in range(1, min(max_order + 1, n)):
        if n <= order or n < 2 * order + min_margin:
            continue
        rows = [[nums[i - j] for j in range(1, order + 1)] + [nums[i]] for i in range(order, n)]
        coeffs = _solve_linear(rows)
        if coeffs is None:
            continue
        ok = all(_close(sum(coeffs[j] * nums[i - j - 1] for j in range(order)), nums[i]) for i in range(order, n))
        if not ok:
            continue
        terms = " + ".join(f"{fmt(coeffs[j])}·a(n-{j+1})" for j in range(order))

        def make_pred(c=coeffs, o=order, seed=list(nums)):
            def predict(idx: int) -> float:
                if idx < len(seed):
                    return seed[idx]
                seq = list(seed)
                for _ in range(len(seed), idx + 1):
                    seq.append(sum(c[j] * seq[-(j + 1)] for j in range(o)))
                return seq[idx]
            return predict

        rule = Rule(f"a(n) = {terms}", make_pred(), "recurrence", "recurrence fit", complexity=order + 2)
        sc = _score(rule, nums)
        if sc < best_score:
            best_score = sc
            best = (rule, [f"  • Linear recurrence of order {order}: a(n) = {terms}"])
    return best


def _discover_cycle(nums: list[float]) -> tuple[Rule, list[str]] | None:
    n = len(nums)
    for p in range(1, min(n // 2 + 1, 16)):
        if n >= 2 * p and nums[-p:] == nums[-2 * p : -p]:
            pat = nums[-p:]
            return Rule(
                f"repeats {pat}", lambda i, pattern=pat, period=p: pattern[i % period],
                "cycle", "cycle detection", complexity=1.0,
            ), [f"  • Tail repeats every {p} terms"]
    return None


def _discover_exp_from_base(bases: list[float], exps: list[float]) -> tuple[Rule, list[str]] | None:
    """Discover exponent as a function of base — no named patterns."""
    pairs = list(zip(bases, exps))

    # e == b ?
    if all(_close(e, b) for b, e in pairs):
        return Rule("exp = base", lambda b: float(b), "relation", "exp equals base", 0.5), [
            "  • Exponent equals base for every term"]

    # e == constant?
    if all(_close(e, exps[0]) for _, e in pairs):
        c = exps[0]
        return Rule(f"exp = {fmt(c)}", lambda b, cc=c: cc, "relation", "constant exponent", 0.5), [
            f"  • Exponent is always {fmt(c)}"]

    # e = c if base < T else base  (discover threshold T from data)
    for T in sorted(set(bases)):
        small = [e for b, e in pairs if b < T]
        large = [(b, e) for b, e in pairs if b >= T]
        if not small or not large:
            continue
        if not all(_close(e, small[0]) for e in small):
            continue
        c = small[0]
        if all(_close(e, b) for b, e in large):
            thoughts = [f"  • For base < {fmt(T)}: exp = {fmt(c)}; else exp = base"]
            return Rule(
                f"exp = {fmt(c)} if base<{fmt(T)} else base",
                lambda b, tt=T, cc=c: cc if b < tt else b,
                "relation", "piecewise exp from base", 1.0,
            ), thoughts

    # polynomial in base, degree <= 2
    for degree in range(min(3, len(pairs))):
        rows = [[b ** j for j in range(degree + 1)] + [e] for b, e in pairs]
        coeffs = _solve_linear(rows)
        if coeffs is None:
            continue
        if all(_close(_poly_eval(coeffs, int(b)), e) for b, e in pairs):
            return Rule(
                f"exp = {_poly_str(coeffs)}  (in base)",
                lambda b, cc=coeffs: _poly_eval(cc, int(b)),
                "relation", "polynomial in base", degree + 1,
            ), [f"  • Exponent follows {_poly_str(coeffs)} in the base value"]
    return None


def _discover_power_structure(nums: list[float], depth: int = 0) -> tuple[Rule, list[str]] | None:
    """General: if each term = base^exp, discover rules for base(n) and exp(n) separately."""
    if depth > 2:
        return None
    decomps = [_integer_factor_power(v) for v in nums]
    if any(d is None for d in decomps):
        return None

    bases = [float(d[0]) for d in decomps]  # type: ignore
    exps = [float(d[1]) for d in decomps]  # type: ignore

    thoughts = ["  • Each term factors as a single base^exponent:"]
    for i, (v, d) in enumerate(zip(nums, decomps)):
        thoughts.append(f"      a({i}) = {fmt(v)} = {d[0]}^{d[1]}")  # type: ignore

    thoughts.append(f"  • Base sequence: {[fmt(b) for b in bases]}")
    thoughts.append(f"  • Exponent sequence: {[fmt(e) for e in exps]}")

    # Discover exponent from base values (relational — more stable than index for towers)
    exp_rel = _discover_exp_from_base(bases, exps)
    if exp_rel:
        thoughts.append(f"  • Exponent rule: {exp_rel[0].name}")
        exp_rule = exp_rel[0]
        thoughts.extend(exp_rel[1])
    else:
        exp_rule = _discover_all(exps, depth=depth + 1)
        if exp_rule is None or not _is_exact(exp_rule, exps):
            return None
        thoughts.append(f"  • Exponent by index: {exp_rule.name}")

    base_rule = _discover_all(bases, depth=depth + 1)
    if base_rule and _is_exact(base_rule, bases) and base_rule.family != "evolved":
        thoughts.append(f"  • Base by index: {base_rule.name}")
        base_complexity = base_rule.complexity
    else:
        thoughts.append("  • Base by index: gap / search on integer candidates")
        base_complexity = 1.5
    thoughts.append("  • Combined: a(n) = base(n)^exp(n)")

    def _base_at(n: int, bs=bases, ns=nums, er=exp_rule, rel=exp_rel) -> float:
        if n < len(bs):
            return bs[n]
        exp_fn = er.predict if rel else er.value  # type: ignore
        b, _ = _extrapolate_next_base(bs, ns, exp_fn)
        return b

    def predict(n: int, bs=bases, er=exp_rule, rel=exp_rel, ns=nums) -> float:
        b = _base_at(n)
        if not math.isfinite(b):
            return float("nan")
        if rel:
            e = float(er.predict(b))  # type: ignore
        else:
            e = er.value(n)
        if not math.isfinite(e) or b < 2:
            return float("nan")
        out = float(int(round(b)) ** int(round(e)))
        return out

    # Show how the next base is chosen when we're at the frontier
    if len(bases) == len(nums):
        exp_fn = exp_rule.predict if exp_rel else exp_rule.value  # type: ignore
        nb, why = _extrapolate_next_base(bases, nums, exp_fn)
        ne = float(exp_fn(nb))  # type: ignore
        thoughts.append(f"  • Next base: {fmt(nb)} ({why})")
        thoughts.append(f"  • Next term: {fmt(nb)}^{fmt(ne)} = {fmt(int(round(nb)) ** int(round(ne)))}")

    complexity = exp_rule.complexity + base_complexity
    return Rule(
        f"base(n)^exp(n)",
        predict, "power_structure", "factor + relational discovery",
        complexity=complexity,
    ), thoughts


# ---------------------------------------------------------------------------
# Expression evolution (general discovery)
# ---------------------------------------------------------------------------

@dataclass
class _Node:
    tag: str
    left: "_Node | None" = None
    right: "_Node | None" = None
    value: float = 0.0

    def eval(self, n: int, prev: list[float]) -> float:
        try:
            t = self.tag
            if t == "n":
                return float(n)
            if t == "c":
                return self.value
            if t == "p1":
                return prev[-1] if prev else float("nan")
            if t == "p2":
                return prev[-2] if len(prev) >= 2 else float("nan")
            if t == "add":
                return self.left.eval(n, prev) + self.right.eval(n, prev)  # type: ignore
            if t == "sub":
                return self.left.eval(n, prev) - self.right.eval(n, prev)  # type: ignore
            if t == "mul":
                return self.left.eval(n, prev) * self.right.eval(n, prev)  # type: ignore
            if t == "div":
                d = self.right.eval(n, prev)  # type: ignore
                return self.left.eval(n, prev) / d if abs(d) > 1e-12 else float("nan")  # type: ignore
            if t == "pow":
                b = self.left.eval(n, prev)  # type: ignore
                e = self.right.eval(n, prev)  # type: ignore
                if abs(e) > 10 or abs(b) > 1e5:
                    return float("nan")
                out = b ** e
                return out if isinstance(out, (int, float)) and math.isfinite(out) else float("nan")
            if t == "sq":
                x = self.left.eval(n, prev)  # type: ignore
                return x * x
        except (OverflowError, ValueError, ZeroDivisionError):
            return float("nan")
        return float("nan")

    def copy(self) -> "_Node":
        return _Node(self.tag, self.left.copy() if self.left else None,
                     self.right.copy() if self.right else None, self.value)

    def to_str(self) -> str:
        if self.tag == "n":
            return "n"
        if self.tag == "c":
            return fmt(self.value)
        if self.tag == "p1":
            return "a(n-1)"
        if self.tag == "p2":
            return "a(n-2)"
        if self.tag == "sq":
            return f"({self.left.to_str()})²" if self.left else "?"
        ops = {"add": "+", "sub": "-", "mul": "×", "div": "÷", "pow": "^"}
        if self.tag in ops:
            return f"({self.left.to_str()} {ops[self.tag]} {self.right.to_str()})"
        return self.tag

    def size(self) -> int:
        return 1 + (self.left.size() if self.left else 0) + (self.right.size() if self.right else 0)


def _rand_tree(rng: random.Random, depth: int, nums: list[float]) -> _Node:
    if depth <= 0 or rng.random() < 0.3:
        choice = rng.random()
        if choice < 0.35:
            return _Node("n")
        if choice < 0.55 and nums:
            return _Node("p1")
        if choice < 0.65 and len(nums) >= 2:
            return _Node("p2")
        return _Node("c", value=rng.choice(nums) if nums else rng.uniform(-3, 3))
    tag = rng.choice(["add", "sub", "mul", "div", "pow", "sq"])
    if tag == "sq":
        return _Node("sq", left=_rand_tree(rng, depth - 1, nums))
    return _Node(tag, _rand_tree(rng, depth - 1, nums), _rand_tree(rng, depth - 1, nums))


def _mutate(node: _Node, rng: random.Random, nums: list[float]) -> _Node:
    if rng.random() < 0.2:
        return _rand_tree(rng, 3, nums)
    out = node.copy()
    stack = [out]
    while stack:
        cur = stack.pop()
        if rng.random() < 0.25:
            if cur.tag == "c":
                cur.value += rng.gauss(0, max(1, abs(cur.value)) * 0.15)
            elif cur.left is None and cur.right is None:
                repl = _rand_tree(rng, 2, nums)
                cur.tag, cur.left, cur.right, cur.value = repl.tag, repl.left, repl.right, repl.value
        if cur.left:
            stack.append(cur.left)
        if cur.right:
            stack.append(cur.right)
    return out


def _evolve(nums: list[float], seed: int = 0) -> tuple[Rule, list[str]] | None:
    if len(nums) < 2:
        return None
    rng = random.Random(seed)
    pop_size, gens = 80, 60

    def fitness(tree: _Node) -> float:
        err = 0.0
        for i, y in enumerate(nums):
            prev = nums[:i]
            p = tree.eval(i, prev)
            if not math.isfinite(p):
                return float("inf")
            d = abs(p - y)
            err += d * d + (d * 8 if not _close(p, y) else 0)
        return err + tree.size() * 0.03

    pop = [_rand_tree(rng, 4, nums) for _ in range(pop_size)]
    best = min(pop, key=fitness)
    best_err = fitness(best)

    for _ in range(gens):
        scored = sorted(pop, key=fitness)
        elites = scored[: pop_size // 4]
        nxt = [e.copy() for e in elites]
        while len(nxt) < pop_size:
            nxt.append(_mutate(rng.choice(elites), rng, nums))
        pop = nxt
        for t in pop:
            e = fitness(t)
            if e < best_err:
                best, best_err = t.copy(), e

    exact = all(_close(best.eval(i, nums[:i]), nums[i]) for i in range(len(nums)))

    def predict(n: int, t=best.copy(), hist=list(nums)) -> float:
        seq = list(hist)
        while len(seq) <= n:
            i = len(seq)
            seq.append(t.eval(i, seq))
        return seq[n]

    thoughts = [
        "  • No simple closed form — evolved an expression from scratch",
        f"  • {'Exact' if exact else 'Best'} fit: f(n) = {best.to_str()}",
        f"  • Search: {pop_size} trees × {gens} generations",
    ]
    return Rule(
        best.to_str() if exact else f"≈ {best.to_str()}",
        predict,
        "evolved",
        "genetic expression search",
        complexity=best.size() * 0.5,
    ), thoughts


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _discover_all(nums: list[float], depth: int = 0) -> Rule | None:
    """Run all general discoverers; return best rule."""
    candidates: list[Rule] = []
    poly_cap = min(2, max(1, len(nums) - 2)) if depth > 0 else None
    for fn in (_discover_cycle, _discover_geometric, _discover_recurrence):
        hit = fn(nums)  # type: ignore
        if hit:
            rule, _ = hit
            rule.score = _score(rule, nums)
            candidates.append(rule)
    hit = _discover_polynomial(nums, max_degree=poly_cap)
    if hit:
        rule, _ = hit
        rule.score = _score(rule, nums)
        candidates.append(rule)
    hit = _discover_power_structure(nums, depth)
    if hit:
        rule, _ = hit
        rule.score = _score(rule, nums)
        candidates.append(rule)

    if not candidates or min(c.score for c in candidates) > 0.01:
        ev = _evolve(nums, seed=sum(int(abs(x)) for x in nums) % 99991)
        if ev:
            rule, _ = ev
            rule.score = _score(rule, nums)
            candidates.append(rule)

    if not candidates:
        return None
    candidates.sort(key=lambda r: (r.score, r.complexity))
    return candidates[0]


def search_pattern(
    nums: list[float],
    family_weights: dict[str, float] | None = None,
    budget: int = 0,
) -> SearchResult | None:
    if not nums:
        return None

    weights = family_weights or {}
    thoughts = ["Thinking... reading your sequence"]

    if len(nums) >= 2:
        steps = [nums[i + 1] - nums[i] for i in range(len(nums) - 1)]
        thoughts.append(f"  • Terms: {[fmt(x) for x in nums]}")
        thoughts.append(f"  • Steps: {[fmt(x) for x in steps]}")
        if len(nums) >= 3:
            ratios = [nums[i + 1] / nums[i] for i in range(len(nums) - 1) if abs(nums[i]) > 1e-12]
            if ratios:
                thoughts.append(f"  • Ratios: {[fmt(x) for x in ratios]}")
        if all(abs(x - round(x)) < 1e-6 for x in nums):
            facs = [_integer_factor_power(x) for x in nums]
            if all(f is not None for f in facs):
                thoughts.append(f"  • Factor forms: {[f'{a}^{b}' for a, b in facs]}")  # type: ignore

    candidates: list[Rule] = []
    sub_thoughts: list[str] = []

    for fn in (_discover_cycle, _discover_geometric, _discover_polynomial,
                _discover_power_structure, _discover_recurrence):
        hit = fn(nums) if fn != _discover_power_structure else fn(nums, 0)  # type: ignore
        if hit:
            rule, t = hit
            sub_thoughts.extend(t)
            rule.score = _score(rule, nums) - weights.get(rule.family, 0) * 0.2
            candidates.append(rule)

    if not candidates or not any(_is_exact(c, nums) for c in candidates):
        sub_thoughts.append("  • No exact rule yet — growing an expression...")
        ev = _evolve(nums, seed=sum(int(abs(x)) for x in nums) % 99991)
        if ev:
            rule, t = ev
            sub_thoughts.extend(t)
            rule.score = _score(rule, nums)
            candidates.append(rule)

    if not candidates:
        return None

    candidates.sort(key=lambda r: (r.score, r.complexity))
    best, runner = candidates[0], candidates[1] if len(candidates) > 1 else None
    nxt = best.value(len(nums))

    thoughts.extend(sub_thoughts)
    thoughts.append(f"  ✓ Discovered: {best.name}  ({best.reason})")
    if runner and runner.score < float("inf"):
        thoughts.append(f"  · Alternative: {runner.name}")
    thoughts.append(f"I think: {best.name} → next = {fmt(nxt)}")

    return SearchResult(best=best, runner_up=runner, tried=len(candidates), thoughts=thoughts, next_val=nxt)


def update_weights(weights: dict[str, float], hypothesis: Rule, success: bool) -> None:
    fam = hypothesis.family
    if success:
        weights[fam] = weights.get(fam, 1.0) + 0.5
    else:
        weights[fam] = max(0.1, weights.get(fam, 0.85))
