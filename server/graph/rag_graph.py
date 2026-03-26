from langgraph.graph import StateGraph, END
from typing import TypedDict, Any

from services.embeddings import get_embeddings
from services.vector_store import load_vector_store
from services.retriever import retrieve_docs
from services.rag_pipeline import generate_answer
from guardrails.relevance import is_relevant


class State(TypedDict):
    query: str
    docs: list
    result: dict
    db: Any          # vector store handle — loaded once in retrieve, reused in generate


def check(state: State) -> State:
    """Guardrail: reject queries not related to finance/legal."""
    if not is_relevant(state["query"]):
        return {
            **state,
            "docs": [],
            "result": {
                "answer": "This system only answers finance and legal queries. Please rephrase your question.",
                "sources": [],
                "confidence": 0.0
            }
        }
    return state


def should_skip(state: State) -> str:
    """Conditional edge: skip retrieve+generate if query was already blocked in check."""
    # result is initialised as {} (falsy); check() only populates it when blocking
    if state.get("result"):
        return "done"
    return "retrieve"


def retrieve(state: State) -> State:
    """Load vector store once and attach to state so generate can reuse it."""
    db = load_vector_store(get_embeddings())
    docs = retrieve_docs(db, state["query"])
    return {**state, "db": db, "docs": docs}


def generate(state: State) -> State:
    """Generate answer, reusing the db handle already loaded in retrieve."""
    db = state["db"]
    result = generate_answer(
        state["docs"],
        state["query"],
        lambda q, k=3: retrieve_docs(db, q, k)
    )
    return {**state, "result": result}


def build_graph():
    g = StateGraph(State)

    g.add_node("check", check)
    g.add_node("retrieve", retrieve)
    g.add_node("generate", generate)

    g.set_entry_point("check")

    # If check blocked the query short-circuit to END; otherwise proceed
    g.add_conditional_edges(
        "check",
        should_skip,
        {
            "done": END,
            "retrieve": "retrieve"
        }
    )

    g.add_edge("retrieve", "generate")
    g.set_finish_point("generate")

    return g.compile()
