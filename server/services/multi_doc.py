def group_by_document(docs: list) -> dict:
    """Group retrieved document chunks by their source document name."""
    grouped = {}
    for doc in docs:
        name = doc.metadata.get("doc", "unknown")
        if name not in grouped:
            grouped[name] = []
        grouped[name].append(doc.page_content)
    return grouped
