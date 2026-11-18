# Evaluation

## What is here
| File | Purpose |
|---|---|
| `corpus.py` | Synthetic, fictional contracts: the single source of truth for sample PDFs and gold quotes |
| `datasets/handwritten/cases.json` | 28 cases: answerable, multi-doc, follow-up, unanswerable, off-topic, adversarial (injection inside a PDF). 18 tuning, 10 held-out |
| `schema.py` | Typed `Case` / `SystemResponse` models |
| `metrics.py` | Deterministic metrics: recall@k, MRR, citation precision/recall, numeric-aware answer correctness, abstention, injection success, ECE, latency percentiles, bootstrap CI |
| `run_evals.py` | Harness. `--offline --recorded <file>` replays recorded responses (CI, no keys) and writes JSON and Markdown reports that list **every** failure |

## Rules
- Tune only on the `tuning` split. Report `heldout` separately; never tune on it.
- n is small: always read the bootstrap interval, do not over-claim.
- Every gold quote must exist verbatim on its page. `tests/unit/test_eval_dataset.py` enforces this against both the corpus and the rendered PDFs.
- Regenerate sample PDFs: `python scripts/make_sample_docs.py` (output in `sample_data/`).

## Still to come in Phase 1
- Live adapter for the legacy system and the recorded B0 run (needs an OpenAI key) -> `docs/EVAL_RESULTS.md`.
- Public datasets (CUAD CC BY 4.0, SEC EDGAR filings, FinanceBench sample) via `scripts/fetch_datasets.py`.
- LLM judge for free-text faithfulness, with hand-checked agreement.
- Grow the golden set from 28 towards ~60 cases.

## Provenance and licences
Synthetic corpus and hand-written cases: this repository (MIT). External datasets will be listed here with their licences when added.
