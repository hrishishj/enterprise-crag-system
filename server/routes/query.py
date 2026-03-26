from fastapi import APIRouter
from pydantic import BaseModel

from graph.rag_graph import build_graph
from evaluation.evaluator import log_eval

router = APIRouter()

# Build the LangGraph workflow once at startup
graph = build_graph()


class QueryRequest(BaseModel):
    query: str


@router.post("/query")
def query_docs(q: QueryRequest):
    # db=None because it gets populated inside the retrieve node
    result = graph.invoke({"query": q.query, "docs": [], "result": {}, "db": None})

    final = result.get("result") or {
        "answer": "No response generated",
        "sources": [],
        "confidence": 0.0
    }

    # Log for evaluation — must never crash the request
    try:
        log_eval(q.query, final["answer"], final["sources"])
    except Exception:
        pass

    return final
