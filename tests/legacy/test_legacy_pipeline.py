"""Characterisation of the legacy answer pipeline, graph and routes (baseline B0)."""

import pytest

from .conftest import FakeDB, FakeDoc, make_pdf


def _router(supported="YES", relevant="YES", score="0.7", conf="0.9", answer="The notice period is 30 days."):
    def respond(prompt: str) -> str:
        if prompt.startswith("Is this a finance or legal query"):
            return relevant
        if prompt.startswith("Rate how relevant this passage"):
            return score
        if prompt.startswith("Is the answer supported"):
            return supported
        if prompt.startswith("Rate how well the answer is supported"):
            return conf
        return answer

    return respond


DOCS = [FakeDoc(f"[Page {i}]\nclause text {i}") for i in range(1, 11)]


class _Boom:
    """OpenAI client whose every call raises."""

    class chat:
        class completions:
            @staticmethod
            def create(**kw):
                raise RuntimeError("down")


def _graph_stub(result):
    return type("G", (), {"invoke": lambda self, state: {"result": result}})()


# ---------------- generate_answer ----------------
def test_generate_answer_happy_path(install_llm):
    from services.rag_pipeline import generate_answer

    llm = install_llm(_router())
    out = generate_answer(DOCS[:3], "notice?", lambda q, k=3: DOCS[:3])
    assert out["answer"] == "The notice period is 30 days."
    assert out["confidence"] == pytest.approx(0.9)
    assert llm.calls == 3  # generate + hallucination check + confidence


def test_generate_answer_retries_with_k6_when_hallucinated(install_llm):
    """KNOWN FLAW: the retry asks for k=6 (fewer than the initial 10) and is not re-verified."""
    from services.rag_pipeline import generate_answer

    llm = install_llm(_router(supported="NO"))
    asked = []

    def retriever(q, k=3):
        asked.append(k)
        return DOCS[:3]

    out = generate_answer(DOCS[:3], "notice?", retriever)
    assert asked == [6]
    assert llm.calls == 4  # generate + check + regenerate + confidence (no second check)
    assert out["answer"]


def test_generate_answer_returns_error_dict_when_llm_fails(monkeypatch):
    import services.rag_pipeline as rp

    monkeypatch.setattr(rp, "client", _Boom)
    out = rp.generate_answer(DOCS[:1], "q", lambda q, k=3: [])
    assert out == {"answer": "Error generating answer", "sources": [], "confidence": 0}


def test_sources_only_found_in_chunks_that_start_with_a_page_marker(install_llm):
    """KNOWN FLAW: mid-page chunks carry no page, so their sources are silently lost."""
    from services.rag_pipeline import generate_answer

    install_llm(_router())
    docs = [FakeDoc("[Page 4]\nstarts a page"), FakeDoc("mid page text, no marker")]
    out = generate_answer(docs, "q", lambda q, k=3: docs)
    assert out["sources"] == ["[Page 4]"]


def test_stream_answer_yields_text_and_reports_errors(install_llm, monkeypatch):
    import services.rag_pipeline as rp

    install_llm(lambda p: "chunk")
    assert "".join(rp.stream_answer("p")) == "chunk"

    monkeypatch.setattr(rp, "client", _Boom)
    assert "Stream error" in "".join(rp.stream_answer("p"))


# ---------------- graph ----------------
@pytest.fixture
def graph_env(monkeypatch):
    import graph.rag_graph as rg

    db = FakeDB(DOCS)
    monkeypatch.setattr(rg, "get_embeddings", lambda: object())
    monkeypatch.setattr(rg, "load_vector_store", lambda emb: db)
    return rg, db


def _invoke(rg, query):
    return rg.build_graph().invoke({"query": query, "docs": [], "result": {}, "db": None})


def test_graph_blocks_off_domain_query_and_skips_retrieval(graph_env, install_llm):
    rg, db = graph_env
    llm = install_llm(_router(relevant="NO"))
    out = _invoke(rg, "best pizza?")
    assert out["result"]["confidence"] == 0.0
    assert "finance and legal" in out["result"]["answer"]
    assert llm.calls == 1
    assert db.ks == []


def test_graph_happy_path_costs_fourteen_sequential_llm_calls(graph_env, install_llm):
    """BASELINE COST: 1 relevance + 10 rerank + 1 generate + 1 hallucination + 1 confidence."""
    rg, db = graph_env
    llm = install_llm(_router())
    out = _invoke(rg, "notice period?")
    assert out["result"]["answer"] == "The notice period is 30 days."
    assert llm.calls == 14
    assert db.ks == [10]


def test_graph_retry_path_costs_twenty_one_calls(graph_env, install_llm):
    """BASELINE COST of the corrective path: the k=6 pool is reranked with 6 more calls, plus a regenerate."""
    rg, db = graph_env
    llm = install_llm(_router(supported="NO"))
    _invoke(rg, "notice period?")
    # 14 happy-path calls + 6 rerank calls for the k=6 pool + 1 regenerate
    assert llm.calls == 21
    assert db.ks == [10, 6]


# ---------------- routes ----------------
def test_query_route_returns_result_and_logs(client, monkeypatch):
    import routes.query as rq

    logged = []
    monkeypatch.setattr(rq, "graph", _graph_stub({"answer": "A", "sources": [], "confidence": 0.5}))
    monkeypatch.setattr(rq, "log_eval", lambda q, a, s: logged.append((q, a)))
    res = client.post("/api/query", json={"query": "x"})
    assert res.json() == {"answer": "A", "sources": [], "confidence": 0.5}
    assert logged == [("x", "A")]


def test_query_route_survives_logging_failure(client, monkeypatch):
    import routes.query as rq

    monkeypatch.setattr(rq, "graph", _graph_stub({"answer": "A", "sources": [], "confidence": 1}))

    def boom(*a):
        raise OSError("disk full")

    monkeypatch.setattr(rq, "log_eval", boom)
    assert client.post("/api/query", json={"query": "x"}).status_code == 200


def test_clause_route(client, monkeypatch, install_llm):
    import routes.clause as rc

    monkeypatch.setattr(rc, "get_embeddings", lambda: object())
    monkeypatch.setattr(rc, "load_vector_store", lambda e: FakeDB([]))
    assert client.post("/api/extract-clause", json={"query": "indemnity"}).status_code == 404

    install_llm(lambda p: "0.5" if p.startswith("Rate how relevant") else "• bullet")
    monkeypatch.setattr(rc, "load_vector_store", lambda e: FakeDB(DOCS))
    res = client.post("/api/extract-clause", json={"query": "indemnity"})
    assert res.json() == {"clauses": "• bullet"}


def test_compare_route_requires_two_documents_in_global_top10(client, monkeypatch):
    """KNOWN FLAW: a dominant document crowds the other out of the global top-10 and yields a 400."""
    import routes.compare as rc

    monkeypatch.setattr(rc, "get_embeddings", lambda: object())
    monkeypatch.setattr(rc, "load_vector_store", lambda e: FakeDB([FakeDoc("x", "a.pdf") for _ in range(10)]))
    assert client.post("/api/compare", json={"query": "caps"}).status_code == 400

    monkeypatch.setattr(rc, "load_vector_store", lambda e: FakeDB([]))
    assert client.post("/api/compare", json={"query": "caps"}).status_code == 404


def test_compare_route_streams_when_two_documents_present(client, monkeypatch, install_llm):
    import routes.compare as rc

    install_llm(lambda p: "A caps at $1M; B is uncapped.")
    monkeypatch.setattr(rc, "get_embeddings", lambda: object())
    monkeypatch.setattr(rc, "load_vector_store", lambda e: FakeDB([FakeDoc("x", "a.pdf"), FakeDoc("y", "b.pdf")]))
    res = client.post("/api/compare", json={"query": "caps"})
    assert res.status_code == 200
    assert "caps at $1M" in res.text


# ---------------- upload ----------------
def test_upload_happy_path_rejects_non_pdf_and_unreadable(client, raw_dir, monkeypatch):
    import routes.upload as up

    stored = {}
    monkeypatch.setattr(up, "get_embeddings", lambda: object())
    monkeypatch.setattr(up, "extract_tables", lambda p: ["TABLE"])
    monkeypatch.setattr(up, "create_vector_store", lambda c, e, n: stored.update(chunks=c, name=n))

    ok = client.post("/api/upload", files={"file": ("contract.pdf", make_pdf(), "application/pdf")})
    assert ok.status_code == 200
    assert ok.json()["filename"] == "contract.pdf"
    assert stored["name"] == "contract.pdf"
    assert "TABLE" in stored["chunks"]
    assert len(list(raw_dir.glob("*.pdf"))) == 1

    assert client.post("/api/upload", files={"file": ("a.txt", b"x", "text/plain")}).status_code == 415
    bad = client.post("/api/upload", files={"file": ("a.pdf", b"not a pdf", "application/pdf")})
    assert bad.status_code == 422


def test_health_endpoints(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert "Running" in client.get("/").json()["message"]
