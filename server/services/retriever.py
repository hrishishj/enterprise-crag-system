from services.reranker import rerank

def retrieve_docs(db, query: str, k: int = 10) -> list:
    """
    Retrieve documents from vector DB and apply re-ranking.
    Returns top 3 re-ranked results by default.
    """
    try:
        docs = db.similarity_search(query, k=k)
    except Exception:
        return []

    return rerank(query, docs, top_k=3)
