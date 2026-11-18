"""Integrity of the golden set: every gold quote must really be in the corpus on the stated page."""

import collections

import pytest
from evals.corpus import CORPUS, page_text
from evals.metrics import quote_in_text
from evals.run_evals import load_cases


@pytest.fixture(scope="module")
def cases():
    return load_cases()


def test_ids_unique(cases):
    assert len({c.id for c in cases}) == len(cases)


def test_every_gold_quote_is_verbatim_on_its_page(cases):
    for c in cases:
        for g in c.gold_quotes:
            assert g.document in CORPUS, f"{c.id}: unknown document {g.document}"
            assert 1 <= g.page <= len(CORPUS[g.document]), f"{c.id}: bad page {g.page}"
            assert quote_in_text(g.text, page_text(g.document, g.page)), (
                f"{c.id}: quote not on page: {g.text!r}"
            )


def test_cases_reference_known_documents(cases):
    for c in cases:
        assert set(c.documents) <= set(CORPUS), c.id


def test_answerable_cases_have_gold_and_checks(cases):
    for c in cases:
        if c.expect_abstain:
            assert not c.gold_quotes
            assert not c.answer_contains
        else:
            assert c.gold_quotes, c.id
            assert c.answer_contains, c.id


def test_kind_coverage_and_heldout_share(cases):
    kinds = collections.Counter(c.kind for c in cases)
    assert set(kinds) == {"answerable", "unanswerable", "multi_doc", "follow_up", "adversarial", "off_topic"}
    heldout = sum(c.split == "heldout" for c in cases) / len(cases)
    assert 0.25 <= heldout <= 0.45
    assert any(c.split == "heldout" and c.kind == "unanswerable" for c in cases)


def test_rendered_pdfs_contain_gold_quotes_on_the_right_pages(tmp_path, cases):
    pdfplumber = pytest.importorskip("pdfplumber")
    pytest.importorskip("reportlab")
    from scripts.make_sample_docs import render

    render(tmp_path)
    for c in cases:
        for g in c.gold_quotes:
            with pdfplumber.open(tmp_path / g.document) as pdf:
                assert len(pdf.pages) == len(CORPUS[g.document])
                assert quote_in_text(g.text, pdf.pages[g.page - 1].extract_text() or ""), (
                    f"{c.id}: {g.text!r}"
                )
