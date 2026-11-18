"""Characterisation of legacy building blocks. These pin CURRENT behaviour (including known flaws; see docs/ASSESSMENT.md)."""

import json

import pytest

from .conftest import FakeDB, FakeDoc, make_pdf


def test_chunker_respects_size_and_overlap():
    from services.chunker import chunk_text

    chunks = chunk_text(("word " * 600).strip())
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)


def test_pdf_loader_inserts_page_marker_once_per_page(tmp_path):
    from services.pdf_loader import load_pdf

    p = tmp_path / "a.pdf"
    p.write_bytes(make_pdf("Hello contract"))
    text = load_pdf(str(p))
    assert "[Page 1]" in text and "Hello contract" in text


def test_table_extractor_returns_empty_on_failure(tmp_path):
    from services.table_extractor import extract_tables

    assert extract_tables(str(tmp_path / "missing.pdf")) == []


def test_group_by_document():
    from services.multi_doc import group_by_document

    g = group_by_document([FakeDoc("x", "a.pdf"), FakeDoc("y", "b.pdf"), FakeDoc("z", "a.pdf")])
    assert g == {"a.pdf": ["x", "z"], "b.pdf": ["y"]}


def test_rerank_sorts_by_llm_score_and_keeps_top_k(install_llm):
    from services.reranker import rerank

    scores = {"low": "0.1", "high": "0.9", "mid": "0.5"}
    install_llm(lambda prompt: next(v for k, v in scores.items() if f"Passage: {k}" in prompt))
    docs = [FakeDoc("low"), FakeDoc("high"), FakeDoc("mid")]
    assert [d.page_content for d in rerank("q", docs, top_k=2)] == ["high", "mid"]


def test_rerank_falls_back_to_neutral_score_on_garbage(install_llm):
    from services.reranker import rerank

    install_llm(lambda prompt: "not a number")
    docs = [FakeDoc("a"), FakeDoc("b"), FakeDoc("c"), FakeDoc("d")]
    assert [d.page_content for d in rerank("q", docs, top_k=3)] == ["a", "b", "c"]


def test_rerank_makes_one_llm_call_per_candidate(install_llm):
    from services.reranker import rerank

    llm = install_llm(lambda prompt: "0.5")
    rerank("q", [FakeDoc(str(i)) for i in range(10)])
    assert llm.calls == 10


def test_retrieve_docs_always_reranks_down_to_three_whatever_k_is(install_llm):
    """KNOWN FLAW: k only widens the candidate pool; the answer context is capped at 3."""
    from services.retriever import retrieve_docs

    install_llm(lambda prompt: "0.5")
    db = FakeDB([FakeDoc(str(i)) for i in range(10)])
    assert len(retrieve_docs(db, "q", k=10)) == 3
    assert len(retrieve_docs(db, "q", k=6)) == 3
    assert db.ks == [10, 6]


def test_retrieve_docs_returns_empty_on_store_error():
    from services.retriever import retrieve_docs

    class Boom:
        def similarity_search(self, *a, **k):
            raise RuntimeError("down")

    assert retrieve_docs(Boom(), "q") == []


@pytest.mark.parametrize("reply,expected", [("YES", True), ("no", False), ("Yes, it is", True)])
def test_relevance_guardrail(install_llm, reply, expected):
    from guardrails.relevance import is_relevant

    install_llm(lambda prompt: reply)
    assert is_relevant("q") is expected


def test_relevance_guardrail_fails_open_on_error(monkeypatch):
    """KNOWN FLAW: any exception lets the query through silently."""
    import guardrails.relevance as rel

    class Boom:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    raise RuntimeError("api down")

    monkeypatch.setattr(rel, "client", Boom)
    assert rel.is_relevant("anything") is True


@pytest.mark.parametrize("reply,hallucinated", [("YES", False), ("NO", True), ("maybe", True)])
def test_hallucination_check(install_llm, reply, hallucinated):
    from guardrails.hallucination import is_hallucinated

    install_llm(lambda prompt: reply)
    assert is_hallucinated("a", "c") is hallucinated


@pytest.mark.parametrize("reply,expected", [("0.85", 0.85), ("7", 1.0), ("junk", 0.5), ("Score: .4", 0.4)])
def test_confidence_parsing_and_clamping(install_llm, reply, expected):
    from services.confidence import get_confidence

    install_llm(lambda prompt: reply)
    assert get_confidence("a", "c") == pytest.approx(expected)


def test_clause_extractor_returns_model_text(install_llm):
    from services.clause_extractor import extract_clauses

    llm = install_llm(lambda prompt: "• Party A shall indemnify")
    assert extract_clauses("ctx", "indemnification") == "• Party A shall indemnify"
    assert "indemnification" in llm.prompts[0]


def test_log_eval_appends_and_recovers_from_corrupt_file(tmp_path, monkeypatch):
    import evaluation.evaluator as ev

    f = tmp_path / "logs" / "eval.json"
    monkeypatch.setattr(ev, "EVAL_LOG_FILE", str(f))
    ev.log_eval("q1", "a1", ["[Page 1]"])
    ev.log_eval("q2", "a2", [])
    assert [r["query"] for r in json.loads(f.read_text())] == ["q1", "q2"]
    f.write_text("{corrupt")
    ev.log_eval("q3", "a3", [])
    assert len(json.loads(f.read_text())) == 1


def test_prompts_embed_context_and_query():
    from utils.prompts import build_comparison_prompt, build_prompt

    p = build_prompt("CTX", "QUESTION")
    assert "CTX" in p and "QUESTION" in p and "I don't have enough information" in p
    c = build_comparison_prompt({"a.pdf": ["x"], "b.pdf": ["y"]}, "caps")
    assert "=== a.pdf ===" in c and "=== b.pdf ===" in c
