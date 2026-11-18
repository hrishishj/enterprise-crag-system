from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.embeddings import get_embeddings
from services.vector_store import load_vector_store
from services.retriever import retrieve_docs
from services.clause_extractor import extract_clauses

router = APIRouter()


class QueryRequest(BaseModel):
    query: str


@router.post("/extract-clause")
def extract(q: QueryRequest):
    db = load_vector_store(get_embeddings())

    docs = retrieve_docs(db, q.query, k=5)

    if not docs:
        return JSONResponse(status_code=404, content={"error": "No relevant documents found. Upload PDFs first."})

    context = "\n\n".join([d.page_content for d in docs])

    try:
        clauses = extract_clauses(context, q.query)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Clause extraction failed: {str(e)}"})

    return {"clauses": clauses}

