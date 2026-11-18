# Audit log

Every defect found in the original prototype (now frozen in `legacy/server`) and what happened to it.
Status: **fixed** (in legacy, security only) · **pinned** (a test documents the behaviour; the fix lands in the new `src/crag`) · **open**.
Detail and reasoning: [ASSESSMENT.md](ASSESSMENT.md). Planned fix location: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

| # | Finding | Severity | Status | Evidence / planned fix |
|---|---|---|---|---|
| 1 | Not Corrective RAG: retrieval never graded | High | open | Phase 5 (`grade`, `refine`, `rewrite` nodes) |
| 2 | LangGraph is a straight line; correction loop lives outside the graph | High | pinned | `test_graph_*` ; Phase 5 |
| 3 | Retry asks `k=6` (fewer than the first pass's 10) and is not re-verified | High | pinned | `test_generate_answer_retries_with_k6_when_hallucinated`; Phase 5 |
| 4 | "Evaluation" is a JSON log with no metrics or dataset | High | open | Phase 1 |
| 5 | Page citations lost for chunks that do not start a page | High | pinned | `test_sources_only_found_in_chunks_that_start_with_a_page_marker`; Phase 3 |
| 6 | Compare needs 2 docs in the global top-10 (crowd-out 400) | Medium | pinned | `test_compare_route_requires_two_documents_in_global_top10`; Phase 6 |
| 7 | Confidence is the model rating itself | Medium | open | Phase 5 (calibrated) |
| 8 | Guardrails fail open silently | Medium | pinned | `test_relevance_guardrail_fails_open_on_error`; Phase 2/5 |
| 9 | Re-upload duplicates chunks (no content hash) | Medium | open | Phase 3 |
| 10 | Single global collection, no document scoping or tenants | Medium | open | Phase 2/7 |
| 11 | Tables flattened with `df.to_string()`, no page/caption | Medium | open | Phase 3 |
| 12 | `sentence-transformers` installed but unused; reranking by per-chunk LLM calls | Medium | pinned | `test_rerank_makes_one_llm_call_per_candidate`; Phase 4 |
| 13 | 14 sequential LLM calls per query (21 on the retry path) | High | pinned | `test_graph_happy_path_costs_fourteen_sequential_llm_calls`, `test_graph_retry_path_costs_twenty_one_calls` (asserts 21); Phase 4/5 |
| 14 | Six OpenAI clients at import time, store reopened per request, model hard-coded | Low | open | Phase 2 (gateway, config) |
| 15 | **Path traversal on upload** via client filename | **Critical** | **fixed** | `tests/legacy/test_upload_security.py`; storage key is now a UUID, display name is the sanitised basename |
| 16 | No auth, no rate limit, no size cap, CORS `*` with credentials | High | open | Phase 7 |
| 17 | Prompt-injection surface (no delimiting of untrusted text) | High | open | Phase 5/8 |
| 18 | Root container, no healthcheck, unpinned deps, deprecated `langchain_community.Chroma` | Medium | open | Phase 2/8 |
| 19 | No PII handling or data-flow statement for a finance/legal tool | Medium | open | Phase 2/8 |
| 20 | No tests, CI, lint, types; README claims MIT without a LICENSE file | Medium | **fixed** | Phase 0: LICENSE, CI, ruff, mypy, import-linter, 40 characterisation tests |
| 21 | No structured logs, metrics, tracing, real readiness check | Medium | open | Phase 2/8 |
| 22 | No migrations or metadata store; no async ingestion | Medium | open | Phase 2/3 |
| 23 | Flat services layout; nothing injectable or unit-testable offline | Medium | open | Phase 2 (ports and adapters) |

## Corrections to earlier claims
- The retry path costs **21** LLM calls, not ~25: the `k=6` pool is only 6 candidates, so it adds 6 rerank calls, not 10 (found while writing the characterisation tests).
