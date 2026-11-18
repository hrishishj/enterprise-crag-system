# Enterprise CRAG — Target Architecture

Status: **proposed** (nothing below is built yet; see [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)). Replaces the flat `server/` layout.

## 1. Purpose and non-goals

**Purpose.** Answer questions over finance and legal documents with **verifiable, cited, abstaining** answers, and prove it with measured
evaluation. The system should say "I can't find that in your documents" more readily than it guesses.

**Non-goals (v1).** Fine-tuning or training models; legal/financial advice; OCR of scanned PDFs (flagged, not solved; Phase 2 stretch);
autonomous actions; multi-region. Web search fallback exists but is **off by default** (regulated-data posture).

## 2. Design principles

| # | Principle | Consequence |
|---|---|---|
| 1 | **Corrective by construction.** Retrieval quality is graded and acted on *inside* the graph (CRAG), not bolted on after generation. | Every correction is a node, visible in traces and testable. |
| 2 | **Deterministic where possible, LLM where necessary.** Cross-encoder for ranking, exact-match for quote/number verification, rules for injection/PII, LLM only for judgement calls. | Cheaper, faster, reproducible. Target ≤3 LLM calls on the happy path (today: 14). |
| 3 | **Cite or abstain.** Every claim carries chunk id + page + verbatim quote; claims without a verified quote are dropped or the answer abstains. | Hallucination becomes measurable (citation precision). |
| 4 | **Confidence is computed, not asked.** From retrieval scores, grounding ratio, citation validity; calibrated on the eval set. | A number a user can actually trust, with a reliability diagram to prove it. |
| 5 | **Documents are untrusted input.** Prompt-injection defence, delimiters, no tools with side effects, tenant isolation. | Safe for counterparty-supplied contracts. |
| 6 | **Everything is measured.** Eval harness gates CI; each improvement is justified by an ablation row. | Quality is data. |
| 7 | **Ports and adapters.** LLM, embeddings, reranker, vector store, parser are interfaces with fake implementations. | Whole pipeline tests run offline in seconds. |
| 8 | **Fail loudly, degrade explicitly.** No `except: pass`. Degraded modes are surfaced in the response (`degraded: ["reranker_timeout"]`). | No silent quality loss (today's guardrails fail open silently). |
| 9 | **Typed, versioned config and prompts.** Pydantic settings validated at startup; prompts are versioned files. | No hard-coded model names; prompt changes are diffable and eval-gated. |
| 10 | **Free by default.** Runs on Ollama/Groq + local embeddings + local Postgres; OpenAI/Azure optional. | Anyone can reproduce your results. |

## 3. System context

```
   Browser UI (React)        API clients / curl          CLI (crag ingest|ask|eval)
          │                        │                              │
          └──────────────┬─────────┴──────────────────────────────┘
                         ▼
        ┌──────────────────────────────────┐
        │ API  (FastAPI, /v1)              │  authN (API key/JWT) → tenant ctx, rate limit,
        │ thin: validate, authorise, 202   │  request-id, size limits, SSE streaming
        └───────┬──────────────────┬───────┘
     ingest job │                  │ query
                ▼                  ▼
   ┌──────────────────┐   ┌─────────────────────────────────────────────┐
   │ Ingestion worker │   │ CRAG graph (LangGraph, checkpointed)        │
   │ parse→chunk→     │   │ see §4                                      │
   │ enrich→embed→    │   └───────┬───────────────┬─────────────────────┘
   │ upsert           │           │               │
   └────────┬─────────┘           ▼               ▼
            │            ┌────────────────┐  ┌──────────────────────────┐
            └──────────► │ PostgreSQL 16  │  │ LLM gateway              │
                         │ + pgvector     │  │ retries, timeouts, cache,│
                         │ + tsvector FTS │  │ redaction, budgets,      │
                         │ tenants, docs, │  │ schema-validated output, │
                         │ chunks, runs,  │  │ token/cost accounting    │
                         │ feedback, eval │  └────────────┬─────────────┘
                         └────────────────┘               ▼
                                              Groq / Ollama / OpenAI / Azure OpenAI
```

## 4. The CRAG graph (the core of the project)

```
                 ┌───────────────┐
 query ─────────►│ guard_input   │── blocked (injection/off-domain/PII policy) ──► finalize(abstain)
                 └──────┬────────┘
                        ▼
                 ┌───────────────┐   intent: qa | clause | compare | summarise
                 │ analyse_query │   rewrite w/ chat history, decompose multi-hop,
                 └──────┬────────┘   extract filters (doc, year, party)
                        ▼
                 ┌───────────────┐   dense (pgvector) + sparse (tsvector) in parallel,
        ┌───────►│ retrieve      │   fused with RRF, tenant+doc filtered, k=40
        │        └──────┬────────┘
        │               ▼
        │        ┌───────────────┐   local cross-encoder (bge-reranker), top 8, MMR for diversity
        │        │ rerank        │
        │        └──────┬────────┘
        │               ▼
        │        ┌───────────────┐   CRAG evaluator: per-chunk score → CORRECT / AMBIGUOUS / INCORRECT
        │        │ grade         │   thresholds on reranker score; LLM judge ONLY for the ambiguous band
        │        └──────┬────────┘
        │   ┌───────────┼───────────────────────┐
        │   │CORRECT    │AMBIGUOUS              │INCORRECT
        │   ▼           ▼                       ▼
        │ ┌────────┐ ┌──────────────────┐ ┌─────────────────────┐
        │ │ refine │ │ refine + rewrite │ │ rewrite_query       │  attempts < MAX (2)?
        │ └───┬────┘ └───┬──────────────┘ └──┬──────────────────┘
        │     │          └─────► retrieve ◄───┘ yes → loop        no → web_fallback (opt-in) or abstain
        │     ▼
        │ ┌───────────────┐   knowledge refinement: sentence-level filter, strip irrelevant spans,
        │ │ (refine)      │   keep provenance (chunk_id, page, char offsets)
        │ └──────┬────────┘
        │        ▼
        │ ┌───────────────┐   structured output: Answer{claims[{text, chunk_id, quote}], abstain?}
        │ │ generate      │   instruction hierarchy + delimited, untrusted context
        │ └──────┬────────┘
        │        ▼
        │ ┌───────────────┐   1) quote exists verbatim in cited chunk (deterministic)
        │ │ verify        │   2) every number/date/currency in claim appears in cited chunk (deterministic)
        │ └──────┬────────┘   3) claim entailment (cheap NLI cross-encoder; LLM judge on disagreement)
        │   pass │  fail & repairs < 1
        │        │  └─► repair (regenerate with failures listed) ─► verify
        │        ▼
        │ ┌───────────────┐   confidence = calibrated(f(retrieval_grade, rerank scores, grounding ratio,
        └─┤ finalize      │   citation validity, #repairs));  abstain if below floor; emit trace
          └───────────────┘
```

Rules:
- Loop budget is explicit in state (`retrieval_attempts ≤ 2`, `repairs ≤ 1`); the graph cannot spin.
- **Happy path = 1 generate call** (+ optional ambiguous-band judge calls + NLI model locally). Typical LLM calls: 2–3.
- Every node writes a span into `state.trace` (name, duration, tokens, decision, reason). Persisted as `runs` / `run_steps`.
- Intents `clause` and `compare` reuse `retrieve→rerank→grade` but swap `generate` for domain nodes (§6).
- State is checkpointed (Postgres checkpointer) so runs are resumable and inspectable.

State (Pydantic, not `TypedDict` + `Any`):
```python
class CragState(BaseModel):
    run_id: UUID
    tenant_id: UUID
    question: str
    history: list[Turn] = []
    intent: Intent | None
    rewritten: list[str] = []
    filters: Filters = Filters()
    candidates: list[ScoredChunk] = []
    graded: list[GradedChunk] = []
    verdict: Literal["correct", "ambiguous", "incorrect"] | None
    context: list[Passage] = []  # refined, with provenance
    draft: Answer | None
    verification: VerificationReport | None
    retrieval_attempts: int = 0
    repairs: int = 0
    degraded: list[str] = []
    trace: list[Step] = []
    result: FinalAnswer | None
```

## 5. Ingestion pipeline (async job)

`POST /v1/documents` → validate (magic bytes, size, page cap, hash) → store blob → create `documents` row + `ingest_jobs` row → **202**.
Worker: `parse → structure → chunk → enrich → embed → upsert → verify`.

| Step | Detail |
|---|---|
| Parse | Layout-aware PDF parsing (PyMuPDF / `pymupdf4llm` default; Docling as optional adapter) producing blocks with page, bbox, heading level, reading order. Detects scanned pages (no text layer) and marks `ocr_needed` instead of silently producing nothing. |
| Structure | Heading tree (legal: Article/Section/Clause numbering; finance: Item 1A, MD&A, Notes). Section path stored per chunk (`"Article 12 > 12.3 Termination"`). |
| Tables | Extracted as Markdown + caption + page; an LLM-free row-header normaliser; optional one-line summary for retrieval. Numeric cells preserved verbatim. Stored as `chunk_type="table"`. |
| Chunk | Structure-aware (never split mid-clause/table), 300–600 tokens, small overlap only within a section. Token counting via tiktoken. |
| Enrich | **Contextual chunk header** prepended for embedding only ("This chunk is from <doc>, <section>, about …") — Anthropic-style contextual retrieval; original text kept for citation. |
| Embed | `Embedder` port. Default local `bge-small-en-v1.5` (384-d, free); adapters for OpenAI/Azure. Embedding model + dim recorded per chunk (re-embed safe). |
| Upsert | Idempotent on `(tenant_id, content_hash)`; re-upload of identical file is a no-op, changed file creates a new `version` and tombstones the old chunks. |
| Verify | Post-condition: chunk count > 0, every page accounted for, sample retrieval self-test (first-sentence → retrieves itself). Failures mark the job `failed` with a reason. |

Job states: `queued → running → succeeded | failed | needs_ocr`, with lease + attempts (borrow the lease pattern from `ai-devops-agents`).

## 6. Domain features (what makes it *finance/legal*, not generic RAG)

- **Clause extraction (structured).** Taxonomy of ~20–40 clause types (CUAD-aligned: termination, indemnification, limitation of liability,
  governing law, change of control, assignment, non-compete, MFN, renewal, IP ownership, …). Output schema:
  `Clause{type, text_verbatim, page, section, party, obligation_direction, risk_flags[], confidence}`; quote verified against source.
- **Multi-document comparison.** Retrieve **per document** (fixes today's crowd-out bug), emit a matrix `rows=aspects × cols=documents`
  with cited cells and an explicit `"not found"`; streamed progressively.
- **Financial grounding.** Numeric verifier (amount/percent/date/unit normalisation: "$1.2 million" ≡ "1,200,000 USD"); table-aware answers;
  period awareness ("FY2023 vs FY2022"); arithmetic questions delegated to a small Python calculator tool over extracted cells (no LLM maths).
- **Document summary / key-terms sheet** intent (cached per document version).
- **Disclaimers and scope guard** as configuration, not a per-query LLM call: deterministic domain rules + the retrieval grade decide off-topic; a cheap
  classifier only for the ambiguous band. Follow-ups are resolved against history *before* the scope decision.

## 7. Data model (PostgreSQL 16 + pgvector, Alembic-managed)

```
tenants(id, name, created_at)
api_keys(id, tenant_id, hash, label, scopes, created_at, revoked_at)
documents(id, tenant_id, filename, sha256, version, status, pages, ocr_needed, blob_uri, created_at, deleted_at)
ingest_jobs(id, document_id, status, attempts, lease_until, error, created_at, finished_at)
chunks(id, tenant_id, document_id, version, ord, page_start, page_end, section_path, chunk_type,
       text, embed_text, token_count, content_hash, embedding vector(384), embed_model,
       tsv tsvector GENERATED, bbox jsonb)            -- HNSW index on embedding, GIN on tsv, btree (tenant_id, document_id)
runs(id, tenant_id, question, intent, verdict, answer, abstained, confidence, latency_ms,
     prompt_tokens, completion_tokens, cost_usd, degraded jsonb, created_at)
run_steps(id, run_id, ord, node, started_at, duration_ms, tokens, decision, detail jsonb)
feedback(id, run_id, rating, comment, created_at)        -- feeds the eval set
eval_runs(id, git_sha, dataset, config jsonb, metrics jsonb, created_at)
```
Every query is filtered by `tenant_id` at the repository layer (not in routes), with tests that prove cross-tenant leakage is impossible.

**Why pgvector instead of Chroma:** one transactional store for vectors, metadata, jobs, traces and tenancy; hybrid search (dense + FTS) with RRF
in one SQL round trip; Alembic migrations; matches both reference projects. A `VectorStore` port keeps an in-memory/Chroma adapter for zero-setup tests
and demos. (See ADR-0002.)

## 8. API (versioned, `/v1`)

| Method & path | Purpose |
|---|---|
| `POST /v1/documents` | Upload PDF → `202 {document_id, job_id}` |
| `GET /v1/documents`, `GET/DELETE /v1/documents/{id}` | List, status, delete (cascades chunks) |
| `GET /v1/jobs/{id}` | Ingestion progress |
| `POST /v1/query` | `{question, document_ids?, conversation_id?, stream?}` → answer |
| `POST /v1/query/stream` | SSE events: `step`, `retrieval`, `grade`, `token`, `claim`, `final` |
| `POST /v1/clauses/extract` | `{document_ids, clause_types[]}` → structured clauses |
| `POST /v1/compare` | `{document_ids[≥2], aspects[]}` → comparison matrix (SSE optional) |
| `GET /v1/runs/{id}` | Full trace (nodes, decisions, tokens, cost) |
| `POST /v1/feedback` | Thumbs + comment attached to a run |
| `GET /healthz`, `GET /readyz`, `GET /metrics` | Liveness (process), readiness (DB, migrations, model loaded), Prometheus |

Response contract (stable, typed, documented in OpenAPI):
```json
{
  "run_id": "…", "answer": "…", "abstained": false,
  "citations": [{"id":"c1","document":"msa.pdf","page":7,"section":"12.3 Termination","quote":"Either party may terminate…"}],
  "claims": [{"text":"…","citation_ids":["c1"],"verified":true}],
  "confidence": {"score": 0.84, "components": {"retrieval":0.9,"grounding":1.0,"citations":1.0}},
  "retrieval": {"verdict":"correct","attempts":1},
  "degraded": [], "usage": {"llm_calls":2,"tokens":1930,"cost_usd":0.0004,"latency_ms":2100}
}
```
Errors: RFC 7807 problem+json with stable error codes. Idempotency-Key supported on upload.

## 9. LLM gateway (one place for all model access)

- Provider-agnostic via OpenAI-compatible client (`base_url`): OpenAI, Azure OpenAI, Groq, Ollama, OpenRouter. One config, tiered models (`small` for judging, `large` for generation).
- Schema-validated outputs (Pydantic via JSON mode / structured outputs), automatic repair-once on invalid JSON.
- Retries with jitter, per-call timeout, circuit breaker, rate-limit aware waits (Groq free-tier TPM), per-run token/cost budget.
- Response cache (hash of model+prompt version+inputs) for eval reruns and idempotent retries.
- Redaction hook (emails, SSNs, account numbers → placeholders) applied before egress when `REDACT_PII=true`; mapping restored in the answer.
- Prompts live in `prompts/<area>/<name>.vN.md`, loaded by a registry; prompt version recorded on every run and eval.

## 10. Evaluation (the differentiator)

**Datasets** (all public, license-clean, documented in `evals/README.md`):
- Legal: **CUAD** (Atticus, CC BY 4.0) contracts + clause annotations → clause extraction P/R, QA.
- Finance: **FinanceBench** open sample + SEC EDGAR 10-K/10-Q filings → numeric and table QA.
- Hand-written set (~60 questions) over 6–8 documents: answerable, **unanswerable**, multi-hop, multi-doc, adversarial (prompt injection inside a PDF), follow-up.

**Metrics**

| Layer | Metrics |
|---|---|
| Retrieval | recall@k, MRR, nDCG@10, context precision |
| Generation | answer correctness (exact/numeric match + LLM judge with rubric), **faithfulness**, **citation precision / recall** |
| Abstention | abstain accuracy on unanswerable, false-abstain rate on answerable |
| Calibration | ECE + reliability diagram of the confidence score |
| Safety | injection success rate on adversarial docs; cross-tenant leakage = 0 |
| System | p50/p95 latency, LLM calls/query, tokens, $/query |

**Ablation table (published in `docs/EVAL_RESULTS.md`)** — the headline artifact:

| Config | Description |
|---|---|
| B0 | **Legacy system** (current code, frozen as `legacy/`), the "before" |
| B1 | + page-aware structure chunking + metadata |
| B2 | + hybrid (dense+BM25, RRF) |
| B3 | + cross-encoder rerank |
| B4 | + contextual headers |
| B5 | + CRAG grading/rewrite loop |
| B6 | + claim verification + abstention |
| B7 | + calibrated confidence |

Each row reports all metrics; regressions fail CI via thresholds in `evals/thresholds.yaml`. `--offline` mode replays recorded LLM outputs so CI needs no key
(same pattern as `ai-devops-agents/evals/run_evals.py`). Live runs publish a dated report including **every failure**, like `docs/EVAL_QA_RESULTS.md` in DocuMind.

## 11. Observability and reliability

- Structured JSON logs (structlog) with `request_id`, `tenant_id`, `run_id`; no document text in logs.
- OpenTelemetry spans per graph node; optional OTLP export (Jaeger/Tempo) and optional Langfuse adapter.
- Prometheus: `crag_queries_total{verdict,abstained}`, `crag_node_duration_seconds`, `crag_llm_tokens_total`, `crag_llm_cost_usd_total`,
  `crag_ingest_jobs{status}`, `crag_rerank_degraded_total`. Grafana dashboard + alert rules in `infra/observability/` (copy the pattern from DevOps project).
- SLOs in `docs/SLO.md` (e.g., p95 query latency < 8 s on free-tier Groq, abstention-correctness ≥ 90%, faithfulness ≥ 0.9).
- Fault-injection tests: LLM timeout/garbage, DB down, reranker crash, embedder missing → assert explicit `degraded` flags and no 500s on the happy surfaces.

## 12. Security model (see `docs/THREAT_MODEL.md`)

| Threat | Control |
|---|---|
| Prompt injection inside documents | Context delimited and labelled untrusted; instruction hierarchy; injection heuristics at ingest (flag chunks like "ignore previous instructions"); generation has **no tools**; verify step rejects claims not quoted from context; adversarial eval set |
| Cross-tenant leakage | `tenant_id` enforced in repository layer + Postgres row-level security (stretch) + leakage tests |
| Path traversal / malicious upload | Server-generated storage keys (UUID), never client filenames; magic-byte check; size/page caps; parser run with timeouts; PDF JS/embedded files stripped |
| Secret & PII handling | Env/secret manager only; PII redaction option; logs exclude content; data-flow table documenting what leaves the machine |
| Abuse / DoS | Per-key rate limits, concurrency caps, request timeouts, loop budgets in graph |
| Supply chain | Pinned lockfile (`uv.lock`), Dependabot, `pip-audit`, `gitleaks`, ruff `S` rules, non-root distroless-ish image, SBOM in CI |
| SSRF (web fallback) | Off by default; allow-listed search provider only; never fetches arbitrary URLs |

## 13. Technology choices

| Concern | Choice | Reason / alternative |
|---|---|---|
| Language/tooling | Python 3.12, uv, ruff, mypy `strict`, pytest, import-linter | Same as DevOps project |
| API | FastAPI + Pydantic v2, SSE | Existing choice |
| Orchestration | LangGraph + Postgres checkpointer | Keep; make it earn its place |
| Store | Postgres 16 + pgvector (HNSW) + tsvector | ADR-0002; Chroma adapter kept for tests |
| Embeddings | `bge-small-en-v1.5` local (default), OpenAI optional | Free, reproducible |
| Reranker | `bge-reranker-base` cross-encoder (local) | Replaces 10 LLM calls; uses the already-listed `sentence-transformers` |
| Parsing | PyMuPDF/`pymupdf4llm`; Docling optional | Layout + page/bbox |
| LLM | OpenAI-compatible gateway; default Groq/Ollama, Azure/OpenAI optional | Free by default |
| Migrations | Alembic | Parity with both projects |
| Frontend | React + Vite + TypeScript, PDF.js viewer with citation highlighting | Same stack as DocuMind |
| Packaging | Multi-stage Docker, non-root, healthcheck, compose with db + api + worker (+ ollama profile) | |
| Deploy (optional) | Container Apps/Fly/Render recipe in `docs/DEPLOY.md` | Don't claim a live deploy you haven't done |

## 14. Repository layout (target)

```
enterprise-crag-system/
├── README.md  LICENSE  SECURITY.md  AGENTS.md  CHANGELOG.md
├── pyproject.toml  uv.lock  Makefile  compose.yaml  .env.example  .pre-commit-config.yaml
├── .github/  workflows/{ci,security,eval,release}.yml  dependabot.yml  CODEOWNERS  PULL_REQUEST_TEMPLATE.md
├── src/crag/
│   ├── domain/            # pure models, no I/O: documents, chunks, claims, citations, verdicts, errors
│   ├── core/              # config, logging, ids, tracing, metrics, token counting, ports (Protocols)
│   │   ├── llm/           #   gateway, redaction, cache, budgets, fake backend, prompt registry
│   │   ├── ingest/        #   parse→structure→chunk→enrich pipeline (pure functions over ports)
│   │   ├── retrieval/     #   hybrid fusion (RRF), MMR, filters
│   │   └── grounding/     #   quote verifier, numeric verifier, NLI entailment, calibration
│   ├── adapters/          # implementations of ports; depend on core+domain
│   │   ├── store/         #   postgres (sqlalchemy+pgvector), memory (tests)
│   │   ├── embeddings/    #   bge_local, openai
│   │   ├── rerank/        #   cross_encoder, noop
│   │   ├── parsing/       #   pymupdf, docling
│   │   ├── llm/           #   openai_compat
│   │   └── blob/          #   local_fs, s3
│   ├── pipelines/
│   │   ├── crag/          #   state.py graph.py nodes/{guard,analyse,retrieve,rerank,grade,refine,rewrite,generate,verify,finalize}.py
│   │   ├── clauses/       #   taxonomy.yaml, extractor.py
│   │   ├── compare/       #   per-document retrieval + matrix builder
│   │   └── ingest/        #   worker job runner (leases, retries)
│   └── apps/
│       ├── api/           #   main.py auth.py deps.py middleware.py routes/{documents,query,clauses,compare,runs,feedback,health}.py
│       ├── worker/        #   ingestion worker entrypoint
│       ├── cli/           #   crag ingest | ask | eval | migrate | check-config
│       └── container.py   #   composition root (the only place adapters are wired)
├── prompts/               # versioned: guard/ analyse/ grade/ generate/ verify/ clauses/ compare/ *.v1.md
├── config/                # clause taxonomy, scope rules, redaction patterns, thresholds
├── migrations/            # alembic
├── evals/
│   ├── datasets/{cuad_subset,financebench_subset,handwritten,adversarial}/
│   ├── recorded/          # offline replay fixtures
│   ├── run_evals.py  metrics.py  judges.py  calibrate.py  thresholds.yaml
│   └── README.md          # dataset provenance + licences
├── tests/{unit,contract,integration,fault,security}/  + conftest.py  fixtures/
├── frontend/              # React+Vite+TS: Chat, DocumentLibrary, CitationViewer (PDF.js), TraceInspector, EvalDashboard
├── infra/{container/Dockerfile, observability/{prometheus.yml,alerts.yml,grafana/}, sandbox/}
├── scripts/{backup.sh, restore.sh, seed_demo.py, fetch_datasets.py}
├── sample_data/           # redistributable demo docs (public filings, synthetic contracts)
├── docs/
│   ├── ASSESSMENT.md  TARGET_ARCHITECTURE.md  IMPLEMENTATION_PLAN.md
│   ├── ARCHITECTURE.md  AUDIT.md  THREAT_MODEL.md  SLO.md  DEPLOY.md  DEMO_SCRIPT.md
│   ├── EVAL_RESULTS.md  RAG_ABLATION.md  observability.md  runbooks-ops/  troubleshooting.md  first-run.md
│   └── adr/0001…
├── legacy/server/         # frozen original code; baseline B0 for evals; deleted at v1.0
└── screenshots/
```
Layering `apps → pipelines → adapters → core → domain` enforced by import-linter in CI (`core` and `domain` may not import `adapters`; only `apps/container.py` wires them).

## 15. Definition of "AI-engineer worthy" (acceptance bar)

- [ ] Ablation table with real numbers, including failures, reproducible by `make eval`
- [ ] CRAG loop visible in LangGraph trace with retrieval verdicts, rewrites, repairs
- [ ] ≤3 LLM calls typical; p95 latency and $/query reported
- [ ] Citation precision ≥ 0.9, abstain-on-unanswerable ≥ 0.9 on the golden set (or honest explanation if not)
- [ ] ≥ 300 tests, ≥ 85% coverage, mypy strict, ruff clean, import-linter green, CI green
- [ ] Tenant isolation, upload hardening and injection tests pass
- [ ] `docker compose up` → working UI with citation highlighting in one command
- [ ] README with measured results, screenshots, architecture diagram, 90-second demo script, honest "Known limitations"
