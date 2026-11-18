"""Typed models for evaluation cases and system responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["answerable", "unanswerable", "multi_doc", "follow_up", "adversarial", "off_topic"]
Split = Literal["tuning", "heldout"]


class Quote(BaseModel):
    document: str
    page: int = Field(ge=1)
    text: str


class Turn(BaseModel):
    question: str
    answer: str


class Case(BaseModel):
    id: str
    split: Split
    kind: Kind
    question: str
    documents: list[str] = Field(description="Documents the question is about (corpus names).")
    history: list[Turn] = []
    gold_quotes: list[Quote] = []
    answer_contains: list[str] = Field(
        default=[], description="All must appear in a correct answer (normalised)."
    )
    must_not_contain: list[str] = Field(
        default=[], description="None may appear (injection / wrong-document checks)."
    )
    expect_abstain: bool = False


class Citation(BaseModel):
    document: str | None = None
    page: int | None = None
    quote: str = ""


class SystemResponse(BaseModel):
    answer: str
    abstained: bool = False
    citations: list[Citation] = []
    retrieved: list[str] = Field(default=[], description="Text of retrieved chunks in rank order.")
    confidence: float | None = None
    llm_calls: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
