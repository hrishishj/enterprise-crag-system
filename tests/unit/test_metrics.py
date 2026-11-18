import pytest
from evals.metrics import (
    answer_correct,
    bootstrap_ci,
    citation_precision,
    citation_recall,
    evaluate,
    expected_calibration_error,
    injection_succeeded,
    normalise,
    numbers_in,
    percentile,
    recall_at_k,
    reciprocal_rank,
)
from evals.schema import Case, Citation, Quote, SystemResponse


def _case(**kw):
    base = {"id": "c", "split": "tuning", "kind": "answerable", "question": "q", "documents": ["a.pdf"]}
    return Case(**{**base, **kw})


def test_normalise_unifies_case_space_and_quotes():
    assert normalise("Supplier’s  \n Liability") == "supplier's liability"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$1.2 million", {1_200_000.0}),
        ("1,200,000 USD", {1_200_000.0}),
        ("6.25% per annum", {6.25}),
        ("20 installments of 5k", {20.0, 5000.0}),
        ("no numbers", set()),
    ],
)
def test_numbers_in(text, expected):
    assert numbers_in(text) == expected


def test_recall_and_mrr():
    gold = [Quote(document="a.pdf", page=1, text="ninety (90) days")]
    chunks = ["unrelated", "notice of Ninety (90)   days applies", "other"]
    assert recall_at_k(chunks, gold, 1) == 0.0
    assert recall_at_k(chunks, gold, 2) == 1.0
    assert reciprocal_rank(chunks, gold) == 0.5
    assert recall_at_k(chunks, [], 5) is None
    assert reciprocal_rank(chunks, []) is None


def test_citation_precision_and_recall():
    gold = [
        Quote(document="a.pdf", page=2, text="ninety (90) days written notice"),
        Quote(document="a.pdf", page=3, text="laws of the State of New York"),
    ]
    good = Citation(document="a.pdf", page=2, quote="ninety (90) days")
    wrong_page = Citation(document="a.pdf", page=1, quote="ninety (90) days")
    fabricated = Citation(document="a.pdf", page=2, quote="thirty days")
    assert citation_precision([good, wrong_page, fabricated], gold) == pytest.approx(1 / 3)
    assert citation_recall([good], gold) == 0.5
    assert citation_precision([], gold) is None


def test_answer_correct_rules():
    c = _case(answer_contains=["42,500"], must_not_contain=["28,000"])
    assert answer_correct(c, SystemResponse(answer="That is 42500 per month"))
    assert answer_correct(c, SystemResponse(answer="$42,500 monthly"))
    assert not answer_correct(c, SystemResponse(answer="$42,500, unlike the $28,000 elsewhere"))
    assert not answer_correct(c, SystemResponse(answer="not found", abstained=True))
    assert not answer_correct(c, SystemResponse(answer="no idea"))


def test_unanswerable_requires_abstention():
    c = _case(kind="unanswerable", expect_abstain=True)
    assert answer_correct(c, SystemResponse(answer="not in the documents", abstained=True))
    assert not answer_correct(c, SystemResponse(answer="The CEO is Jane."))


def test_injection_detection():
    adv = _case(kind="adversarial", must_not_contain=["1 year"])
    assert injection_succeeded(adv, SystemResponse(answer="It survives for 1 year.")) is True
    assert injection_succeeded(adv, SystemResponse(answer="Five years.")) is False
    assert injection_succeeded(_case(), SystemResponse(answer="x")) is None


def test_ece_perfect_and_overconfident():
    assert expected_calibration_error([1.0, 1.0, 0.0, 0.0], [True, True, False, False]) == pytest.approx(0.0)
    assert expected_calibration_error([0.9] * 10, [True] * 5 + [False] * 5) == pytest.approx(0.4)
    assert expected_calibration_error([], []) == 0.0


def test_percentile_and_bootstrap_are_deterministic():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([], 95) == 0.0
    assert bootstrap_ci([1.0, 0.0, 1.0, 1.0]) == bootstrap_ci([1.0, 0.0, 1.0, 1.0])
    lo, hi = bootstrap_ci([1.0] * 10)
    assert lo == hi == 1.0


def test_evaluate_aggregates_all_metrics():
    ok = _case(
        id="ok",
        answer_contains=["90"],
        gold_quotes=[Quote(document="a.pdf", page=1, text="ninety (90) days")],
    )
    unans = _case(id="un", kind="unanswerable", expect_abstain=True)
    resps = {
        "ok": SystemResponse(
            answer="90 days",
            retrieved=["ninety (90) days"],
            confidence=0.9,
            llm_calls=3,
            latency_ms=100,
            citations=[Citation(document="a.pdf", page=1, quote="ninety (90) days")],
        ),
        "un": SystemResponse(answer="Jane", confidence=0.8, llm_calls=14, latency_ms=900),
    }
    m = evaluate([ok, unans], resps)
    assert m["answer_correct"] == 0.5
    assert m["recall@5"] == 1.0
    assert m["mrr"] == 1.0
    assert m["citation_precision"] == 1.0
    assert m["citation_recall"] == 1.0
    assert m["abstain_accuracy"] == 0.0
    assert m["false_abstain_rate"] == 0.0
    assert m["llm_calls_mean"] == 8.5
    # bin 0.9 holds the correct case (|1-0.9|=0.1), bin 0.8 the wrong one (|0-0.8|=0.8)
    assert m["ece"] == pytest.approx(0.5 * 0.1 + 0.5 * 0.8)
