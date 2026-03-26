from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from services.embeddings import get_embeddings
from services.vector_store import load_vector_store
from services.multi_doc import group_by_document
from utils.prompts import build_comparison_prompt
from services.rag_pipeline import stream_answer

router = APIRouter()


class QueryRequest(BaseModel):
    query: str


@router.post("/compare")
def compare(q: QueryRequest):
    db = load_vector_store(get_embeddings())

    docs = db.similarity_search(q.query, k=10)

    if not docs:
        return JSONResponse(status_code=404, content={"error": "No documents found in the vector store. Upload PDFs first."})

    grouped = group_by_document(docs)

    if len(grouped) < 2:
        return JSONResponse(status_code=400, content={"error": "At least 2 different documents are required for comparison."})

    prompt = build_comparison_prompt(grouped, q.query)

    return StreamingResponse(stream_answer(prompt), media_type="text/plain")

