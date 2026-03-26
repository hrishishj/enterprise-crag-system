# Enterprise CRAG System

> A production-ready **Corrective Retrieval-Augmented Generation** backend for intelligent finance and legal document analysis.

Built with **FastAPI · LangGraph · ChromaDB · OpenAI GPT-4o-mini**

---

## What It Does

Upload your finance or legal PDF documents and ask questions in plain English. The system retrieves relevant content, validates its own answers against your documents, and returns grounded responses with source references and confidence scores.

| Feature | Description |
|--------|-------------|
| 📄 **Document Ingestion** | Upload PDFs — text and tables are extracted, chunked, and indexed automatically |
| 🔍 **Smart Retrieval** | Semantic search over your documents with LLM-powered re-ranking |
| 🤖 **Answer Generation** | GPT-4o-mini generates answers strictly grounded in your documents |
| ✅ **Hallucination Check** | Automatically detects and corrects unsupported answers |
| 📊 **Confidence Scoring** | Every answer comes with a 0–1 confidence score |
| ⚖️ **Clause Extraction** | Extract specific clause types (e.g. indemnification, termination) as bullet points |
| 📑 **Document Comparison** | Compare terms across multiple uploaded documents side by side |
| 🛡️ **Relevance Guardrail** | Non-finance/legal queries are rejected before hitting the pipeline |

---

## Architecture

```
Client Request
      ↓
FastAPI Routes
      ↓
LangGraph Orchestration
   ├── Relevance Guardrail
   ├── Vector Retrieval (ChromaDB)
   ├── LLM Re-ranking
   ├── Answer Generation (GPT-4o-mini)
   ├── Hallucination Check → Re-retrieve if needed
   └── Confidence Scoring
      ↓
JSON Response { answer, sources, confidence }
```

---

## Project Structure

```
enterprise-crag/
├── server/
│   ├── app.py                  # FastAPI entry point
│   ├── config.py               # Environment & path config
│   ├── routes/                 # API endpoints
│   │   ├── upload.py           # POST /api/upload
│   │   ├── query.py            # POST /api/query
│   │   ├── compare.py          # POST /api/compare
│   │   └── clause.py           # POST /api/extract-clause
│   ├── graph/
│   │   └── rag_graph.py        # LangGraph workflow
│   ├── services/               # Core business logic
│   ├── guardrails/             # Relevance + hallucination checks
│   ├── evaluation/             # Query/answer logging
│   └── utils/                  # Prompt builders
├── data/                       # Auto-created, gitignored
├── Dockerfile
└── docker-compose.yml
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- An [OpenAI API key](https://platform.openai.com)
- Ghostscript (for table extraction from PDFs)
  - **Windows:** [Download here](https://www.ghostscript.com/download.html)
  - **Mac:** `brew install ghostscript`
  - **Linux:** `sudo apt install ghostscript libgl1`

### Local Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-username/enterprise-crag-system.git
cd enterprise-crag-system/server

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and add your OpenAI API key
```

**.env**
```
OPENAI_API_KEY=sk-your-key-here
```

```bash
# 5. Start the server
uvicorn app:app --reload --port 8000
```

Visit **http://localhost:8000/docs** for the interactive API.

### Docker Setup

```bash
cp server/.env.example server/.env
# Add your OpenAI API key to server/.env

docker compose up --build
```

---

## API Reference

### `POST /api/upload`
Upload and index a PDF document.

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "file=@contract.pdf"
```
```json
{ "msg": "Uploaded and indexed successfully", "filename": "contract.pdf", "chunks": 42 }
```

---

### `POST /api/query`
Ask a question against your indexed documents.

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the termination clauses?"}'
```
```json
{
  "answer": "Either party may terminate with 30 days written notice...",
  "sources": ["[Page 4]", "[Page 7]"],
  "confidence": 0.91
}
```

---

### `POST /api/extract-clause`
Extract specific clause types as bullet points.

```bash
curl -X POST http://localhost:8000/api/extract-clause \
  -H "Content-Type: application/json" \
  -d '{"query": "indemnification clauses"}'
```
```json
{ "clauses": "• Party A shall indemnify...\n• Liability is capped at..." }
```

---

### `POST /api/compare`
Compare terms across multiple uploaded documents (streamed response).

```bash
curl -X POST http://localhost:8000/api/compare \
  -H "Content-Type: application/json" \
  -d '{"query": "liability caps"}'
```

---

### `GET /health`
```json
{ "status": "ok" }
```

---

## How It Works

1. **Upload** — PDF text and tables are extracted, split into 500-token chunks with 100-token overlap, embedded via OpenAI, and stored in ChromaDB.

2. **Query** — The LangGraph pipeline runs:
   - Relevance check (finance/legal only)
   - Semantic retrieval (top 10 chunks)
   - LLM re-ranking (scored by relevance)
   - Answer generation (GPT-4o-mini, grounded in context)
   - Hallucination detection (re-retrieves with k=6 if flagged)
   - Confidence scoring (0–1)

3. **Evaluate** — Every query/answer pair is logged to `data/eval_logs/eval_logs.json` for review.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI |
| Orchestration | LangGraph |
| Vector Store | ChromaDB |
| Embeddings | OpenAI `text-embedding-ada-002` |
| LLM | OpenAI `gpt-4o-mini` |
| PDF Parsing | pdfplumber |
| Table Extraction | camelot-py |
| Chunking | LangChain RecursiveCharacterTextSplitter |

---

## License

MIT
