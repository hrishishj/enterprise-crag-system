"""Evaluation harness.

    python -m evals.run_evals --offline --recorded evals/recorded/b0.json   # replay (CI, no keys)
    live systems (e.g. the legacy baseline) are added with the B0 run

Writes a JSON result and a Markdown report. See docs/EVAL_RESULTS.md for published numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from evals.metrics import answer_correct, evaluate
from evals.schema import Case, SystemResponse

ROOT = Path(__file__).resolve().parent
DEFAULT_CASES = ROOT / "datasets" / "handwritten" / "cases.json"


class System(Protocol):
    """Anything that can answer an evaluation case."""

    def ask(self, case: Case) -> SystemResponse: ...


class ReplaySystem:
    """Replays recorded responses so CI needs no API key. Missing cases fail loudly."""

    def __init__(self, recorded: dict[str, Any]):
        self._by_id = {k: SystemResponse.model_validate(v) for k, v in recorded.items()}

    @classmethod
    def from_file(cls, path: Path) -> ReplaySystem:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def ask(self, case: Case) -> SystemResponse:
        try:
            return self._by_id[case.id]
        except KeyError:
            raise KeyError(f"no recorded response for case {case.id!r}; re-record the run") from None


def load_cases(path: Path = DEFAULT_CASES) -> list[Case]:
    return [Case.model_validate(c) for c in json.loads(path.read_text(encoding="utf-8"))]


def run(
    system: System, cases: list[Case], on_case: Callable[[Case, SystemResponse], None] | None = None
) -> dict[str, Any]:
    """Run every case, return {'metrics': ..., 'responses': ..., 'failures': [...]}."""
    responses: dict[str, SystemResponse] = {}
    for case in cases:
        resp = system.ask(case)
        responses[case.id] = resp
        if on_case:
            on_case(case, resp)
    failures = [c.id for c in cases if not answer_correct(c, responses[c.id])]
    return {
        "metrics": evaluate(cases, responses),
        "responses": {k: v.model_dump() for k, v in responses.items()},
        "failures": failures,
    }


def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def render_report(name: str, cases: list[Case], result: dict[str, Any], split: str | None = None) -> str:
    """Markdown report that lists every failing case (no cherry-picking)."""
    m = result["metrics"]
    lines = [
        f"# Eval report: {name}" + (f" ({split} split)" if split else ""),
        "",
        f"Cases: {m['n_cases']}",
        "",
    ]
    lines += ["| Metric | Value |", "|---|---|"]
    for key in (
        "answer_correct",
        "recall@5",
        "recall@8",
        "mrr",
        "citation_precision",
        "citation_recall",
        "abstain_accuracy",
        "false_abstain_rate",
        "injection_success_rate",
        "ece",
        "latency_ms_p50",
        "latency_ms_p95",
        "llm_calls_mean",
        "cost_usd_total",
    ):
        lines.append(f"| {key} | {_fmt(m[key])} |")
    lo, hi = m["answer_correct_ci95"]
    lines += [
        "",
        f"answer_correct 95% bootstrap CI: [{lo:.3f}, {hi:.3f}] (n={m['n_cases']}; small n = wide)",
        "",
    ]
    lines += ["## By kind", "", "| Kind | answer_correct |", "|---|---|"]
    lines += [f"| {k} | {_fmt(v)} |" for k, v in m["answer_correct_by_kind"].items()]
    lines += ["", "## Failures", ""]
    by_id = {c.id: c for c in cases}
    if not result["failures"]:
        lines.append("None.")
    for cid in result["failures"]:
        resp = result["responses"][cid]
        lines.append(
            f"- **{cid}** ({by_id[cid].kind}): {by_id[cid].question!r} -> {resp['answer'][:160]!r}"
            + (" [abstained]" if resp["abstained"] else "")
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="replay recorded responses (no network)")
    ap.add_argument("--recorded", type=Path, help="recorded responses JSON for --offline")
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--split", choices=["tuning", "heldout"], help="evaluate one split only")
    ap.add_argument("--out", type=Path, help="write result JSON here")
    ap.add_argument("--report", type=Path, help="write Markdown report here")
    args = ap.parse_args(argv)

    cases = load_cases(args.cases)
    if args.split:
        cases = [c for c in cases if c.split == args.split]
    if not args.offline:
        print(
            "Live systems are added in the B0 baseline run; use --offline --recorded for now.",
            file=sys.stderr,
        )
        return 2
    if not args.recorded:
        print("--offline requires --recorded", file=sys.stderr)
        return 2

    result = run(ReplaySystem.from_file(args.recorded), cases)
    report = render_report(args.recorded.stem, cases, result, args.split)
    if args.out:
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.report:
        args.report.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
