# Implementation Plan

Goal: bring `enterprise-crag-system` to the standard of `documind-ai` and `ai-devops-agents` (measured, tested, layered, observable, honestly documented).
Architecture: [TARGET_ARCHITECTURE.md](TARGET_ARCHITECTURE.md). Why: [ASSESSMENT.md](ASSESSMENT.md).

**Effort:** ~110–140 focused hours ≈ **6–7 weeks at ~20 h/week** (3–4 weeks full-time). Cost: **$0** on free tiers (Groq/Ollama, local embeddings, local Postgres).

## Strategy: measure first, then improve

The order matters for the story you tell in interviews. **Freeze the current code as the baseline, build the evaluation harness, measure it, *then* make
each improvement and report the delta.** "I measured the original at faithfulness 0.71 and 14 LLM calls/query; the redesign reached 0.93 with 2.4 calls" is far stronger than "I rewrote it".

Rules for every phase: work on a branch, open a PR to `master` (like `ai-devops-agents` PR #29/#31), merge only with CI green, one ADR per significant decision, update `docs/AUDIT.md` with anything you find.

---

## Phase 0 — Hygiene, safety net, and freeze the baseline (3–4 days)

| # | Task | Done when |
|---|---|---|
| 0.1 | Add `LICENSE` (MIT), `.gitattributes`, `.editorconfig`, `SECURITY.md`, `AGENTS.md` (project conventions for AI assistants), `CHANGELOG.md` | Files present |
| 0.2 | `pyproject.toml` (hatchling, Python ≥3.12, ruff/mypy/pytest/import-linter config), `uv.lock`, `Makefile` (`dev test lint types arch check eval image up down`) | `make check` runs |
| 0.3 | Move current code to `legacy/server/` unchanged (git `mv`, history preserved); keep it runnable | `uvicorn` still starts from `legacy/server` |
| 0.4 | **Hot-fix the legacy security bug** (path traversal via `file.filename`) on the legacy copy in a separate commit, noted in AUDIT.md | Test proves `../x.pdf` is rejected |
| 0.5 | Characterisation tests for legacy with a fake OpenAI client (ingest → query → clause → compare) | ≥15 passing tests |
| 0.6 | CI (`ci.yml`): ruff, mypy, pytest + coverage, import-linter; `security.yml`: gitleaks, pip-audit, bandit (ruff `S`); Dependabot; CODEOWNERS; PR template | Green badge in README |
| 0.7 | Start `docs/AUDIT.md`: log each finding from ASSESSMENT.md as an issue with status | File exists, 20+ entries |

**Exit:** repo looks maintained; baseline frozen; safety net exists.

## Phase 1 — Evaluation harness + baseline numbers (5–6 days) ⭐ most important phase

| # | Task | Done when |
|---|---|---|
| 1.1 | `evals/README.md`: dataset sources + licences; `scripts/fetch_datasets.py` pulls CUAD subset (≈15 contracts), 3–4 SEC 10-K excerpts, FinanceBench sample | Datasets reproducible by one command |
| 1.2 | Hand-write the golden set: ~60 questions in `evals/datasets/handwritten/cases.json` — answerable (with gold page + gold quote), **unanswerable**, multi-hop, multi-doc, follow-up, adversarial (injection inside a PDF). Split 70% tuning / 30% **held-out, never tuned on** | Schema-validated by a test |
| 1.3 | `evals/metrics.py`: recall@k, MRR, nDCG, citation precision/recall, faithfulness, numeric match, abstain accuracy, ECE, latency, tokens, cost | Unit-tested on toy cases |
| 1.4 | `evals/judges.py`: LLM-judge with rubric + deterministic checks first (exact/numeric match); judge prompt versioned; judge ≠ generator model where possible | Judge agreement spot-checked on 20 cases by hand and recorded |
| 1.5 | `evals/run_evals.py` with `--offline` (replay recorded outputs, used in CI) and live mode; writes `eval_runs` JSON + Markdown report | `make eval` works |
| 1.6 | **Run the legacy system (B0)** and publish `docs/EVAL_RESULTS.md` row B0 incl. every failure and LLM-calls/latency/cost | Numbers committed |

**Exit:** a real baseline. Every later phase must beat it or explain why not.

## Phase 2 — Platform foundation (5 days)

| # | Task | Done when |
|---|---|---|
| 2.1 | `src/crag/` skeleton with the layering in TARGET_ARCHITECTURE §14; import-linter contracts; `apps/container.py` composition root | `make arch` green |
| 2.2 | `core/config`: Pydantic Settings, validated at startup, `crag check-config` | No `os.getenv` outside config |
| 2.3 | `core/llm` gateway: OpenAI-compat adapter, retries/jitter, timeout, circuit breaker, structured output + repair-once, token/cost accounting, response cache, `FakeBackend` (scripted) | Fault-injection tests pass |
| 2.4 | Prompt registry + first prompts under `prompts/` (`*.v1.md`) | Run records prompt versions |
| 2.5 | Postgres + Alembic: tenants, api_keys, documents, ingest_jobs, chunks (pgvector HNSW + GIN tsv), runs, run_steps, feedback, eval_runs; `alembic check` in CI | Migrations apply on fresh DB; CI uses a Postgres service |
| 2.6 | Store port + Postgres adapter + in-memory adapter; repository layer enforces `tenant_id` | Cross-tenant leakage tests pass |
| 2.7 | structlog + request-id middleware + `/healthz` `/readyz` | Logs are JSON, no content leaked |
| 2.8 | ADRs 0001–0005 (see §ADRs) | Merged |

## Phase 3 — Ingestion v2 (5–6 days)

| # | Task | Done when |
|---|---|---|
| 3.1 | PyMuPDF parser adapter → blocks with page/bbox/heading level; scanned-page detection (`needs_ocr`) | Fixture PDFs incl. a scanned one |
| 3.2 | Heading/section-path builder for legal numbering and 10-K items | Unit tests on real excerpts |
| 3.3 | Table extraction → Markdown + caption + page; numeric cells verbatim | Table fixture round-trips |
| 3.4 | Structure-aware chunker (never splits clause/table; token-based) | Property tests: no chunk > max, coverage of all text |
| 3.5 | Contextual header enrichment (embed text ≠ display text) with cache | Toggle-able for the ablation |
| 3.6 | Embedder port: local bge-small + OpenAI adapter; model/dim stored per chunk | Re-embed command works |
| 3.7 | Async ingest worker: upload → 202 + job, leases, retries, idempotent on content hash, versioning/tombstones, post-ingest self-test | Re-upload is a no-op; crash mid-job recovers |
| 3.8 | Upload hardening: magic bytes, size/page caps, UUID storage keys, parser timeout, JS/embedded-file stripping | `tests/security/` green |

**Run evals → B1 row.**

## Phase 4 — Retrieval v2 (4 days)

| # | Task | Done when |
|---|---|---|
| 4.1 | Hybrid retrieval: pgvector dense + tsvector sparse, RRF fusion, tenant/doc/year/party filters | **B2 row** |
| 4.2 | Cross-encoder reranker adapter (+ noop fallback with `degraded` flag), MMR | **B3 row** |
| 4.3 | Contextual-header ablation | **B4 row** |
| 4.4 | Tune `k`, fusion weights, thresholds on the tuning split only; report held-out separately | Tuning vs held-out gap reported |

## Phase 5 — The real CRAG graph (7–8 days)

| # | Task | Done when |
|---|---|---|
| 5.1 | `CragState` (Pydantic), graph skeleton, Postgres checkpointer, node tracing → `run_steps` | Trace readable via `GET /v1/runs/{id}` |
| 5.2 | `guard_input` (rules + injection heuristics + scope) and `analyse_query` (history-aware rewrite, decomposition, filter extraction) | Follow-up questions resolve |
| 5.3 | `grade` node: reranker-score thresholds → CORRECT / AMBIGUOUS / INCORRECT; LLM judge only in ambiguous band; thresholds calibrated on tuning split | Verdict distribution reported |
| 5.4 | `refine` (sentence-level filtering with provenance) and `rewrite_query` loop (≤2 attempts); optional `web_fallback` adapter (off by default) | **B5 row** |
| 5.5 | `generate` with structured claims+citations and delimited untrusted context; abstain path | Schema-validated |
| 5.6 | `verify`: verbatim-quote check, numeric/date check, NLI entailment (LLM judge on disagreement), `repair` ×1 | **B6 row** |
| 5.7 | `finalize`: calibrated confidence (isotonic/Platt on tuning split) + abstention floor; reliability diagram + ECE | **B7 row**; `docs/RAG_ABLATION.md` written |
| 5.8 | Graph unit tests per node with `FakeBackend`; property test "loops always terminate"; fault-injection tests | ≥60 tests for the pipeline |

## Phase 6 — Domain features (4–5 days)

| # | Task | Done when |
|---|---|---|
| 6.1 | Clause extractor: `config/clause_taxonomy.yaml`, structured output, quote verification, risk flags; evaluated on CUAD subset (P/R/F1) | Numbers in EVAL_RESULTS |
| 6.2 | Compare: per-document retrieval → aspect × document matrix with `not_found` cells, SSE streaming | Fixes the legacy crowd-out bug; regression test |
| 6.3 | Financial numeric verifier + small calculator tool over extracted table cells | Numeric eval slice reported |
| 6.4 | Document summary / key-terms sheet (cached per version) | |

## Phase 7 — API v1, auth, tenancy (4–5 days)

| # | Task | Done when |
|---|---|---|
| 7.1 | `/v1` routes per TARGET_ARCHITECTURE §8, problem+json errors, OpenAPI examples | Contract tests (schemathesis) pass |
| 7.2 | API-key auth (hashed keys, scopes) + tenant context; rate limits + concurrency caps; CORS allow-list | Security tests |
| 7.3 | SSE streaming of step/grade/token/claim/final events | Stream tested with a fake graph |
| 7.4 | Feedback endpoint → "promote to eval case" CLI | Closed feedback loop documented |
| 7.5 | `crag` CLI: `ingest`, `ask`, `eval`, `migrate`, `check-config` | Used in docs/first-run.md |

## Phase 8 — Observability, reliability, security hardening (4 days)

| # | Task | Done when |
|---|---|---|
| 8.1 | OpenTelemetry spans per node; Prometheus metrics; Grafana dashboard + alert rules; `docs/observability.md`, `docs/SLO.md` | Dashboard screenshot committed |
| 8.2 | Fault-injection suite (LLM down/garbage/slow, DB down, reranker crash, embedder missing) | Every failure → explicit `degraded` or clean 503, never silent |
| 8.3 | `docs/THREAT_MODEL.md` + adversarial eval slice (injection inside PDFs) with measured attack success rate | Number published |
| 8.4 | Non-root multi-stage image, healthcheck, pinned deps, SBOM, `pip-audit` clean; backup/restore scripts + doc | `docker compose up` healthy |
| 8.5 | Load smoke test (k6/locust) at 5–10 concurrent users; record p50/p95 | In EVAL_RESULTS |

## Phase 9 — Frontend (5 days)

React + Vite + TS (reuse DocuMind patterns). Pages: **Library** (upload, ingest progress, status), **Chat** (streamed answer, claims with `[n]` chips, abstain state, confidence breakdown),
**Citation viewer** (PDF.js, jumps to page and highlights the quote), **Trace inspector** (node timeline, retrieval verdict, rewrites, tokens/cost), **Eval dashboard** (ablation table, latest run).
Vitest component tests; screenshots in `screenshots/`.

## Phase 10 — Docs, demo, release (3 days)

| # | Task |
|---|---|
| 10.1 | `docs/ARCHITECTURE.md` (final, with diagrams), `AUDIT.md` closed out, `DEPLOY.md`, `DEMO_SCRIPT.md` (90 s), `first-run.md`, `troubleshooting.md` |
| 10.2 | README rewrite (outline below) with the measured ablation table and honest limitations |
| 10.3 | Delete `legacy/` (or keep as `legacy-baseline` git tag), tag `v1.0.0`, GitHub Release with changelog |
| 10.4 | Record a 2-minute demo GIF/video; pin repo; write a 400-word write-up ("what I measured and what surprised me") |

---

## Calendar (≈20 h/week)

| Week | Phases | Milestone |
|---|---|---|
| 1 | 0, 1 (start) | Baseline frozen, CI green |
| 2 | 1, 2 | **Baseline numbers published**, platform skeleton |
| 3 | 3, 4 | Ingestion v2, retrieval ablations B1–B4 |
| 4 | 5 | CRAG graph B5–B7 |
| 5 | 6, 7 | Domain features, API v1 |
| 6 | 8, 9 | Hardening, UI |
| 7 | 9, 10 | Docs, demo, v1.0.0 |

If time is short, **cut order (last to first):** Phase 9 UI polish → web fallback → Docling adapter → RLS → load test. **Never cut:** Phase 1, Phase 5, tests, honest limitations.

## ADRs to write (short, like `ai-devops-agents/docs/adr/`)

1. 0001 — Measure-first: freeze legacy as baseline B0
2. 0002 — Postgres + pgvector instead of Chroma (hybrid search, transactions, tenancy)
3. 0003 — Local cross-encoder reranker instead of per-chunk LLM scoring
4. 0004 — Retrieval grading thresholds + LLM judge only for the ambiguous band
5. 0005 — Cite-or-abstain with deterministic quote/number verification
6. 0006 — Calibrated confidence instead of LLM self-rating
7. 0007 — Web fallback off by default (regulated-data posture)
8. 0008 — Async ingestion with DB leases (reuse DevOps ADR-0003 rationale)

## Migration map (old → new)

| Legacy file | Fate |
|---|---|
| `app.py` | → `apps/api/main.py` (versioned routers, middleware, lifespan, readiness) |
| `config.py` | → `core/config/settings.py` (Pydantic Settings, validated) |
| `routes/upload.py` | → `apps/api/routes/documents.py` + `pipelines/ingest/` (async, hardened) |
| `routes/query.py` | → `apps/api/routes/query.py` + `pipelines/crag/` |
| `routes/clause.py` | → `routes/clauses.py` + `pipelines/clauses/` (structured) |
| `routes/compare.py`, `services/multi_doc.py` | → `pipelines/compare/` (per-document retrieval, matrix) |
| `graph/rag_graph.py` | → `pipelines/crag/graph.py` + `nodes/` (loop now inside the graph) |
| `services/rag_pipeline.py` | → `nodes/generate.py`, `nodes/verify.py` (+ gateway streaming) |
| `services/retriever.py`, `reranker.py` | → `core/retrieval/` + `adapters/rerank/cross_encoder.py` |
| `services/vector_store.py`, `embeddings.py` | → `adapters/store/postgres.py`, `adapters/embeddings/*` |
| `services/pdf_loader.py`, `chunker.py`, `table_extractor.py` | → `adapters/parsing/pymupdf.py`, `core/ingest/{chunk,tables}.py` |
| `services/confidence.py` | → `core/grounding/calibration.py` (computed features, not LLM self-score) |
| `services/clause_extractor.py` | → `pipelines/clauses/extractor.py` |
| `guardrails/relevance.py` | → `nodes/guard.py` (rules + grade-based scope, no per-query LLM call) |
| `guardrails/hallucination.py` | → `core/grounding/` + `nodes/verify.py` (claim-level) |
| `evaluation/evaluator.py` | → `runs`/`run_steps` tables + top-level `evals/` harness |
| `utils/prompts.py` | → `prompts/*.vN.md` + registry |
| `Dockerfile`, `docker-compose.yml` | → `infra/container/Dockerfile` (non-root, multi-stage), `compose.yaml` (db, api, worker, optional ollama) |

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Free-tier LLM rate limits (Groq TPM) slow evals | High | Response cache, recorded replays, small judge model, run live eval nightly not per-PR |
| LLM-judge bias / self-preference | Medium | Deterministic checks first, judge ≠ generator, hand-verify 20 cases, report judge agreement |
| Small golden set → noisy metrics | High | State n and confidence intervals (bootstrap), keep held-out split, don't claim more than data supports |
| Scope creep (UI, deploy) | High | Cut order above; v1.0 gate is the acceptance bar in TARGET_ARCHITECTURE §15 |
| Local models heavy on Windows | Medium | Docker profile with CPU torch; `NoopReranker` fallback with explicit `degraded`; cache models in a volume |
| Datasets' licences | Low | Only CUAD (CC BY 4.0), SEC EDGAR public filings, your own text; document in `evals/README.md` |
| Improvements don't beat baseline on some metric | Medium | **Report it honestly** — this is a feature (DocuMind's EVAL reports list misses) |

## Definition of done per phase
Code merged via PR, tests added, CI green, docs/ADR updated, eval table row added where relevant, `AUDIT.md` updated.

## README outline (final)
1. One-paragraph pitch + badges (CI, coverage, license) + hero screenshot
2. What it does (table) — 3. **Evidence** (ablation table, latency/cost, tests) — 4. Architecture diagram + graph diagram
5. Quick start (Docker, one command) — 6. Local dev — 7. Configuration table — 8. API reference (generated from OpenAPI)
9. Evaluation & reproducibility — 10. Security notes — 11. **Known limitations (honest)** — 12. Roadmap — 13. License

## Interview / resume talking points (only claim what you measure)
- "Replaced per-chunk LLM reranking (10 calls) with a local cross-encoder: −X% latency, −Y% cost, recall@8 Z→W."
- "Implemented true Corrective RAG: retrieval verdicts drive refine / rewrite / abstain inside a checkpointed LangGraph; bounded loops, fully traced."
- "Cite-or-abstain with deterministic quote and number verification; citation precision A, abstain accuracy B on a held-out set."
- "Calibrated confidence (ECE from X to Y) instead of LLM self-rating."
- "Found and fixed N defects in my own v0 (path traversal, retry that retrieved fewer docs, broken citations) — documented in AUDIT.md."
- Across the three projects: RAG (this + DocuMind), agent safety/policy (DevOps), evaluation discipline (all three).

## Immediate next steps (first 48 hours)
1. Create branch `chore/phase-0-foundations`; do tasks 0.1–0.3.
2. Do 0.4 (path-traversal hot-fix) and write its test first.
3. Draft the 60-question golden set skeleton (Phase 1.2) while the CI work runs — it is the longest-lead item.
