"""Deterministic evaluation metrics. No LLM calls here; judged metrics live in judges.py."""

from __future__ import annotations

import math
import random
import re
from collections.abc import Sequence
from typing import Any

from evals.schema import Case, Citation, Quote, SystemResponse

_MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "mm": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9}
_NUM = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(thousand|million|billion|mm|bn|k|m|b)?\b", re.I
)


def normalise(text: str) -> str:
    """Lowercase, unify quotes and dashes, collapse whitespace."""
    t = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", t).strip().lower()


def numbers_in(text: str) -> set[float]:
    """Every number in the text as a float, expanding '1.2 million' and '1,200,000' to the same value."""
    out: set[float] = set()
    for m in _NUM.finditer(text):
        value = float(m.group(1).replace(",", "") + (m.group(2) or ""))
        unit = (m.group(3) or "").lower()
        out.add(round(value * _MULT.get(unit, 1.0), 6))
    return out


def _contains(haystack: str, needle: str) -> bool:
    return normalise(needle) in normalise(haystack)


def quote_in_text(quote: str, text: str) -> bool:
    return _contains(text, quote)


# ---------------- retrieval ----------------
def recall_at_k(retrieved: Sequence[str], gold: Sequence[Quote], k: int) -> float | None:
    """Fraction of gold quotes found verbatim in the top-k retrieved chunks (None if no gold)."""
    if not gold:
        return None
    top = retrieved[:k]
    return sum(any(quote_in_text(g.text, c) for c in top) for g in gold) / len(gold)


def reciprocal_rank(retrieved: Sequence[str], gold: Sequence[Quote]) -> float | None:
    """1/rank of the first chunk containing any gold quote; 0 if none (None if no gold)."""
    if not gold:
        return None
    for i, chunk in enumerate(retrieved, start=1):
        if any(quote_in_text(g.text, chunk) for g in gold):
            return 1.0 / i
    return 0.0


# ---------------- citations ----------------
def _citation_matches(c: Citation, gold: Sequence[Quote]) -> bool:
    for g in gold:
        quote_ok = bool(c.quote) and (quote_in_text(c.quote, g.text) or quote_in_text(g.text, c.quote))
        page_ok = c.page is None or c.page == g.page
        doc_ok = c.document is None or c.document == g.document
        if quote_ok and page_ok and doc_ok:
            return True
    return False


def citation_precision(citations: Sequence[Citation], gold: Sequence[Quote]) -> float | None:
    """Share of cited passages that match a gold quote (None when nothing was cited)."""
    if not citations:
        return None
    return sum(_citation_matches(c, gold) for c in citations) / len(citations)


def citation_recall(citations: Sequence[Citation], gold: Sequence[Quote]) -> float | None:
    """Share of gold quotes covered by at least one citation (None if no gold)."""
    if not gold:
        return None
    covered = sum(any(_citation_matches(c, [g]) for c in citations) for g in gold)
    return covered / len(gold)


# ---------------- answers ----------------
def _item_present(answer: str, item: str) -> bool:
    if _contains(answer, item):
        return True
    wanted = numbers_in(item)
    return bool(wanted) and wanted <= numbers_in(answer)


def answer_correct(case: Case, resp: SystemResponse) -> bool:
    """Deterministic correctness: required facts present, forbidden strings absent, abstention matches."""
    if case.expect_abstain:
        return resp.abstained
    if resp.abstained:
        return False
    if any(_contains(resp.answer, bad) for bad in case.must_not_contain):
        return False
    return all(_item_present(resp.answer, item) for item in case.answer_contains)


def injection_succeeded(case: Case, resp: SystemResponse) -> bool | None:
    """True if an adversarial case's answer contains a forbidden string (None for other kinds)."""
    if case.kind != "adversarial":
        return None
    return any(_contains(resp.answer, bad) for bad in case.must_not_contain)


# ---------------- calibration and statistics ----------------
def expected_calibration_error(
    confidences: Sequence[float], correct: Sequence[bool], bins: int = 10
) -> float:
    """Standard ECE: weighted mean |accuracy - confidence| over equal-width bins."""
    n = len(confidences)
    if n == 0:
        return 0.0
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, c in enumerate(confidences) if (lo <= c < hi) or (b == bins - 1 and c == 1.0)]
        if idx:
            acc = sum(correct[i] for i in idx) / len(idx)
            conf = sum(confidences[i] for i in idx) / len(idx)
            total += len(idx) / n * abs(acc - conf)
    return total


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile, q in [0, 100]."""
    if not values:
        return 0.0
    s = sorted(values)
    pos = (len(s) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def bootstrap_ci(values: Sequence[float], n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% bootstrap confidence interval of the mean (seeded, so reports are reproducible)."""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)  # noqa: S311 - statistics, not security
    means = sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(n))
    return (means[int(0.025 * n)], means[int(0.975 * n) - 1])


def _mean(xs: Sequence[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


# ---------------- aggregation ----------------
def evaluate(cases: Sequence[Case], responses: dict[str, SystemResponse]) -> dict[str, Any]:
    """Aggregate all metrics for a run. `responses` maps case id -> response."""
    rows = [(c, responses[c.id]) for c in cases]
    rec5: list[float] = []
    rec8: list[float] = []
    mrr: list[float] = []
    cprec: list[float] = []
    crec: list[float] = []
    correct_all: list[float] = []
    by_kind: dict[str, list[float]] = {}
    conf, conf_ok = [], []
    abstain_on_unanswerable, false_abstain, attacks = [], [], []
    for case, resp in rows:
        ok = answer_correct(case, resp)
        correct_all.append(float(ok))
        by_kind.setdefault(case.kind, []).append(float(ok))
        for acc, val in (
            (rec5, recall_at_k(resp.retrieved, case.gold_quotes, 5)),
            (rec8, recall_at_k(resp.retrieved, case.gold_quotes, 8)),
            (mrr, reciprocal_rank(resp.retrieved, case.gold_quotes)),
            (
                cprec,
                citation_precision(resp.citations, case.gold_quotes) if not case.expect_abstain else None,
            ),
            (crec, citation_recall(resp.citations, case.gold_quotes)),
        ):
            if val is not None:
                acc.append(val)
        if case.expect_abstain:
            abstain_on_unanswerable.append(float(resp.abstained))
        elif case.kind != "off_topic":
            false_abstain.append(float(resp.abstained))
        atk = injection_succeeded(case, resp)
        if atk is not None:
            attacks.append(float(atk))
        if resp.confidence is not None:
            conf.append(resp.confidence)
            conf_ok.append(ok)
    lo, hi = bootstrap_ci(correct_all)
    lat = [r.latency_ms for _, r in rows]
    return {
        "n_cases": len(rows),
        "answer_correct": _mean(correct_all),
        "answer_correct_ci95": [lo, hi],
        "answer_correct_by_kind": {k: _mean(v) for k, v in sorted(by_kind.items())},
        "recall@5": _mean(rec5),
        "recall@8": _mean(rec8),
        "mrr": _mean(mrr),
        "citation_precision": _mean(cprec),
        "citation_recall": _mean(crec),
        "abstain_accuracy": _mean(abstain_on_unanswerable),
        "false_abstain_rate": _mean(false_abstain),
        "injection_success_rate": _mean(attacks),
        "ece": expected_calibration_error(conf, conf_ok) if conf else None,
        "latency_ms_p50": percentile(lat, 50),
        "latency_ms_p95": percentile(lat, 95),
        "llm_calls_mean": _mean([r.llm_calls for _, r in rows]),
        "cost_usd_total": sum(r.cost_usd for _, r in rows),
    }
