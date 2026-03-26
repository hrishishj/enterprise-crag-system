def extract_tables(file_path: str) -> list[str]:
    """
    Extract tables from PDF using camelot.
    Returns list of string-formatted tables.
    camelot requires ghostscript: `apt install ghostscript` or `brew install ghostscript`
    """
    try:
        import camelot
        tables = camelot.read_pdf(file_path, pages="all")
        return [t.df.to_string() for t in tables]
    except Exception:
        return []
