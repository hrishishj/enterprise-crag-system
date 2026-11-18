import json

import pytest
from evals.metrics import evaluate
from evals.run_evals import ReplaySystem, load_cases, main, render_report, run
from evals.schema import Citation, SystemResponse


def oracle(case):
    """Perfect system built from the gold data: proves the harness scores a perfect run as perfect."""
    if case.expect_abstain:
        return SystemResponse(answer="Not found in the documents.", abstained=True, confidence=0.9)
    return SystemResponse(
        answer=" ".join(case.answer_contains),
        retrieved=[g.text for g in case.gold_quotes],
        citations=[Citation(document=g.document, page=g.page, quote=g.text) for g in case.gold_quotes],
        confidence=0.9,
    )


class Oracle:
    def ask(self, case):
        return oracle(case)


class AlwaysAnswers:
    """Never abstains and always repeats the injected claim: fails nearly every case."""

    def ask(self, case):
        return SystemResponse(answer="1 year", confidence=0.9)


def test_oracle_scores_perfectly():
    result = run(Oracle(), load_cases())
    m = result["metrics"]
    assert result["failures"] == []
    assert m["answer_correct"] == 1.0
    assert m["recall@5"] == 1.0
    assert m["citation_precision"] == 1.0
    assert m["abstain_accuracy"] == 1.0
    assert m["false_abstain_rate"] == 0.0
    assert m["injection_success_rate"] == 0.0


def test_naive_system_is_scored_poorly_and_attack_detected():
    m = run(AlwaysAnswers(), load_cases())["metrics"]
    assert m["answer_correct"] < 0.2
    assert m["abstain_accuracy"] == 0.0
    assert m["injection_success_rate"] == 1.0


def test_replay_roundtrip_and_missing_case_fails_loudly(tmp_path):
    cases = load_cases()
    rec = {c.id: oracle(c).model_dump() for c in cases}
    path = tmp_path / "rec.json"
    path.write_text(json.dumps(rec))
    assert run(ReplaySystem.from_file(path), cases)["metrics"]["answer_correct"] == 1.0
    del rec["a01"]
    with pytest.raises(KeyError, match="a01"):
        run(ReplaySystem(rec), cases)


def test_report_lists_every_failure():
    cases = load_cases()
    result = run(AlwaysAnswers(), cases)
    report = render_report("naive", cases, result)
    for cid in result["failures"]:
        assert f"**{cid}**" in report
    assert "bootstrap CI" in report


def test_cli_offline_writes_outputs(tmp_path):
    cases = load_cases()
    rec = tmp_path / "rec.json"
    rec.write_text(json.dumps({c.id: oracle(c).model_dump() for c in cases}))
    out, rep = tmp_path / "out.json", tmp_path / "rep.md"
    args = [
        "--offline",
        "--recorded",
        str(rec),
        "--split",
        "heldout",
        "--out",
        str(out),
        "--report",
        str(rep),
    ]
    assert main(args) == 0
    assert json.loads(out.read_text())["metrics"]["n_cases"] == sum(c.split == "heldout" for c in cases)
    assert "heldout split" in rep.read_text()
    assert main(["--offline"]) == 2
    assert main([]) == 2


def test_evaluate_handles_missing_confidences():
    cases = load_cases()[:1]
    assert evaluate(cases, {cases[0].id: SystemResponse(answer="x")})["ece"] is None
