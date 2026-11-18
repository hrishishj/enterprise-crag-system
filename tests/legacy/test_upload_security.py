import routes.upload as upload

from .conftest import make_pdf


def _stub_index(monkeypatch):
    stored = {}
    monkeypatch.setattr(upload, "get_embeddings", lambda: object())
    monkeypatch.setattr(upload, "extract_tables", lambda p: [])
    monkeypatch.setattr(
        upload, "create_vector_store", lambda chunks, emb, name: stored.update(chunks=chunks, name=name)
    )
    return stored


def test_path_traversal_filename_never_escapes_raw_dir(client, raw_dir, tmp_path, monkeypatch):
    _stub_index(monkeypatch)
    res = client.post("/api/upload", files={"file": ("../escaped.pdf", make_pdf(), "application/pdf")})
    assert not (tmp_path / "escaped.pdf").exists(), "file written outside RAW_DOCS_DIR"
    assert res.status_code in (200, 400)
    for p in raw_dir.rglob("*"):
        assert raw_dir in p.parents or p == raw_dir


def test_absolute_and_backslash_filenames_are_confined(client, raw_dir, tmp_path, monkeypatch):
    _stub_index(monkeypatch)
    for name in ("/etc/evil.pdf", r"..\..\evil.pdf", "a/../../evil.pdf"):
        client.post("/api/upload", files={"file": (name, make_pdf(), "application/pdf")})
    assert not list(tmp_path.glob("evil.pdf"))
    assert not list(tmp_path.parent.glob("evil.pdf"))
