"""Fixtures for characterising the frozen baseline in legacy/server (no network, no real models)."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

LEGACY = Path(__file__).resolve().parents[2] / "legacy" / "server"

# The legacy modules build OpenAI clients at import time and need a key to exist.
os.environ.setdefault("OPENAI_API_KEY", "test-key")
if str(LEGACY) not in sys.path:
    sys.path.insert(0, str(LEGACY))


def make_pdf(text: str = "Termination requires 30 days written notice.") -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, text)
    c.save()
    return buf.getvalue()


class FakeDoc(SimpleNamespace):
    def __init__(self, content: str, doc: str = "a.pdf"):
        super().__init__(page_content=content, metadata={"doc": doc})


class FakeLLM:
    """Stand-in for openai.OpenAI. `responder(prompt) -> str` decides each reply; every prompt is recorded."""

    def __init__(self, responder):
        self.responder = responder
        self.prompts: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    @property
    def calls(self) -> int:
        return len(self.prompts)

    def _create(self, **kw):
        prompt = kw["messages"][0]["content"]
        self.prompts.append(prompt)
        text = self.responder(prompt)
        if kw.get("stream"):
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


class FakeDB:
    """Stand-in for the Chroma store: returns canned docs and records the k it was asked for."""

    def __init__(self, docs):
        self.docs = docs
        self.ks: list[int] = []

    def similarity_search(self, query, k=4):
        self.ks.append(k)
        return self.docs[:k]


LLM_MODULES = [
    "guardrails.relevance",
    "guardrails.hallucination",
    "services.reranker",
    "services.confidence",
    "services.rag_pipeline",
    "services.clause_extractor",
]


@pytest.fixture
def install_llm(monkeypatch):
    """Replace the OpenAI client in every legacy module with one FakeLLM; returns that fake."""
    import importlib

    def _install(responder):
        fake = FakeLLM(responder)
        for name in LLM_MODULES:
            monkeypatch.setattr(importlib.import_module(name), "client", fake)
        return fake

    return _install


@pytest.fixture
def pdf_bytes() -> bytes:
    return make_pdf()


@pytest.fixture
def raw_dir(tmp_path, monkeypatch):
    import routes.upload as upload

    d = tmp_path / "raw_docs"
    monkeypatch.setattr(upload, "RAW_DOCS_DIR", str(d))
    return d


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app import app

    return TestClient(app)
