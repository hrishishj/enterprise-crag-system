# Enterprise CRAG System — Honest Assessment

Evaluated: every source file in `server/` (30 files, ~27 KB), Dockerfile, compose, requirements, git history (1 commit).
Benchmarked against your two reference projects: `documind-ai` (203 tracked files, 407 backend tests, measured eval reports,
audit log, CI) and `ai-devops-agents` (187 files, layered architecture enforced by import-linter, ADRs, threat model, SLOs, evals).

## 1. What the project is today (summary)

A FastAPI backend for Q&A over finance/legal PDFs.

| Stage | What the code actually does |
|---|---|
| Upload | Saves PDF to disk, extracts text with pdfplumber (adds `[Page N]` markers into one big string), extracts tables with camelot (`df.to_string()`), splits into 500/100 chunks, embeds with OpenAI, adds to one global Chroma collection with metadata `{"doc": filename}` |
| Query | LangGraph with 3 nodes: `check` (LLM YES/NO relevance) → `retrieve` (Chroma top-10, then **10 sequential LLM calls** to score each chunk, keep 3) → `generate` (GPT-4o-mini answer, then LLM YES/NO "supported?", on NO re-retrieve and regenerate once, then LLM self-score for confidence) |
| Clause | Top-5 chunks → "return bullet points" free text |
| Compare | Raw top-10 similarity search, grouped by doc name, streamed comparison |
| Evaluation | Appends `{query, answer, sources}` to a JSON file |

It works as a demo. It is a clean, readable ~300-line prototype. It is **not yet an AI-engineer portfolio project**, for the reasons below.

## 2. Verified defects and design flaws

Ordered by how much they hurt credibility. Everything here was verified against the code, not inferred from the README.

### A. The headline claim does not hold
1. **It is not Corrective RAG.** CRAG (Yan et al., 2024) needs a *retrieval evaluator* that classifies retrieval as
   Correct / Ambiguous / Incorrect and then **acts differently** on each (refine, rewrite + re-retrieve, fall back to another source).
   Here the retrieval is never graded; the only "correction" is a post-hoc YES/NO check on the *answer*, which is Self-RAG-style at best.
2. **LangGraph is decorative.** The graph is a straight line `check → retrieve → generate`. The correction loop lives inside
   `rag_pipeline.generate_answer`, outside the graph, so it is invisible to state, tracing, checkpointing and testing.
3. **The "retry with k=6" retrieves less, not more.** The first pass fetches 10 candidates; the retry calls
   `retrieve_docs(db, q, k=6)`, which fetches 6 candidates and reranks to the same hard-coded `top_k=3`. The corrective step has
   *fewer* candidates than the original and is not re-verified afterwards. The README describes the opposite.
4. **"Evaluation" is logging.** `evaluator.py` appends records to a JSON file (read-modify-write, unbounded, racy under concurrent
   requests). There is no dataset, no metric, no ground truth, no baseline. This is the biggest gap against both reference projects.

### B. Correctness and quality
5. **Citations are mostly broken.** `[Page N]` is inserted once per page into the full text *before* chunking, so only chunks that
   start a page contain it. Sources are derived by `page_content.split("]")[0]`. Most answers will have no or wrong page sources. Chunk
   metadata holds only `{"doc"}`; tables carry no page at all.
6. **Compare is unreliable.** It takes a global top-10 and requires ≥2 documents to appear in it. A dominant document crowds the
   others out and the endpoint returns 400 even when both documents are indexed. It should retrieve **per document**.
7. **Confidence is not confidence.** It is the same model rating its own answer 0–1 ("0.91"). Uncalibrated, unfalsifiable, and shown to users as a number.
8. **Guardrails fail open and cost a call each.** Relevance and hallucination checks return "allow" on any exception; the relevance gate
   rejects legitimate follow-ups ("and for the second year?").
9. **Duplicate ingestion.** Re-uploading a file appends all chunks again (no content hash / upsert), silently skewing retrieval.
10. **No document scoping.** One global collection; every query searches everything. No list/delete/filter-by-document, no tenants.
11. **Tables are flattened with `df.to_string()`** with no caption, page, header repair or row-level summaries; financial tables are the
    highest-value content in this domain and are handled worst.
12. **`sentence-transformers` is in `requirements.txt` but never imported** (a ~2 GB dependency doing nothing) while reranking is done
    by an LLM. A local cross-encoder is faster, free, deterministic and better.

### C. Performance and cost
13. **14 sequential LLM calls on the happy path** (1 relevance + 10 rerank + 1 generate + 1 hallucination + 1 confidence), **21 on the
    retry path** (measured by tests/legacy). All synchronous, no concurrency, no caching, no timeouts, no retry/backoff. Expect multi-second to tens-of-seconds latency
    and ~10–20× the necessary cost.
14. Six separate `OpenAI()` clients created at import time; the vector store is re-opened on every request; model name hard-coded in six places.

### D. Security
15. **Path traversal on upload:** `os.path.join(RAW_DOCS_DIR, file.filename)` uses the client-supplied filename unchecked.
16. No authentication, no rate limiting, no upload size/page limit (PDF bombs), CORS `*` with `allow_credentials=True`.
17. **Prompt injection surface:** document text and user query are f-string-concatenated into prompts with no delimiting or
    instruction hierarchy; documents are untrusted in this domain (contracts come from counterparties).
18. Runs as root in Docker, no healthcheck, unpinned dependencies (`>=`), `langchain_community.Chroma` is deprecated.
19. Raw document content and queries are sent to a third-party LLM with no PII redaction or data-handling statement. For a *finance/legal*
    positioning that is a credibility issue a reviewer will raise.

### E. Engineering hygiene
20. **0 tests, 0 CI, 0 lint/type checks**, 1 git commit, placeholder clone URL, README says MIT but there is no LICENSE file.
21. No structured logging, metrics, tracing, request IDs, or health checks beyond a static `{"status":"ok"}`.
22. No migrations, no persistent metadata store (documents/jobs/runs only exist as files in a folder), no API versioning, no async ingestion.
23. Flat "services" package with no layering: routes import infrastructure directly; nothing is injectable, so nothing is unit-testable without OpenAI.

## 3. Gap analysis vs. your reference projects

| Dimension | documind-ai | ai-devops-agents | enterprise-crag (today) |
|---|---|---|---|
| Measured evaluation, reported with failures | 58 cases, 3 reports, ablation of retrieval tuning | golden datasets + precision/recall/grounding gates | none |
| Tests | 407 backend (95% cov) + 70 frontend, fault injection | 88+ unit/contract/integration | 0 |
| CI | lint, tests, alembic check, frontend build | CI, security scan, AI review, deploy, dependabot | none |
| Architecture discipline | documented principles, LangGraph with validation/retry | domain→core→integrations→agents→apps enforced by import-linter | flat folders |
| Reliability | checkpoints, timeouts, retries, fault injection | leases, idempotency, supersede, audit log | none (swallows exceptions) |
| Observability | per-run traces, `/metrics`, token/cost accounting | Prometheus, Grafana, alerts, SLOs | none |
| Security | upload validation, zip-bomb/XXE, untrusted-text prompts, security model | threat model, ADRs, SECURITY.md, signed webhooks | path traversal, no auth |
| Persistence | PostgreSQL + Alembic | PostgreSQL + Alembic, leases | folder + Chroma |
| Honest docs | AUDIT.md, "Known limitations" | ADRs, "Known limitations (honest status)" | README feature table |
| UI / demo | React UI, screenshots, demo script | CLI, dashboards, first-run guide | Swagger only |

## 4. What is already good (keep it)

- The *problem choice* is right: finance/legal has real hallucination cost, which makes grounding, abstention and citations meaningful.
- Domain features worth keeping and deepening: clause extraction, multi-document comparison, table extraction, confidence in the response.
- Sensible small touches: DATA_DIR override for Docker, streaming compare, graceful fallbacks, readable code.
- LangGraph is the right orchestration choice **once the corrective loop is actually inside it**.

## 5. Verdict

The raw material is a good *idea*, executed at tutorial level. To reach DocuMind / DevOps-agents level it needs four things, in this order of impact:

1. **A real evaluation harness with published numbers** (including baseline-vs-improved ablation). This alone separates "I called an API" from "I engineered a system".
2. **A genuinely corrective graph** (retrieval grading + query rewrite + refinement + claim-level grounding + abstention), all inside LangGraph with traces.
3. **Engineering rigor**: layered architecture, typed config, tests, CI, Postgres/Alembic, observability, security.
4. **Honest docs**: ADRs, threat model, audit/limitations, measured results.

See [TARGET_ARCHITECTURE.md](TARGET_ARCHITECTURE.md) and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
