from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
import os
import uuid

from services.pdf_loader import load_pdf
from services.chunker import chunk_text
from services.embeddings import get_embeddings
from services.vector_store import create_vector_store
from services.table_extractor import extract_tables
from config import RAW_DOCS_DIR

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    # SECURITY: the client controls file.filename. Keep only its base name for display, and never use it as a path.
    safe_name = os.path.basename((file.filename or "").replace("\\", "/")).strip()
    if not safe_name or not safe_name.lower().endswith(".pdf"):
        return JSONResponse(status_code=415, content={"error": "Only PDF files are supported"})

    os.makedirs(RAW_DOCS_DIR, exist_ok=True)
    path = os.path.join(RAW_DOCS_DIR, f"{uuid.uuid4().hex}.pdf")

    try:
        with open(path, "wb") as f:
            f.write(await file.read())
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to save file: {str(e)}"})

    try:
        text = load_pdf(path)
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": f"PDF read failed: {str(e)}"})

    if not text.strip():
        return JSONResponse(status_code=422, content={"error": "No readable text found in PDF"})

    chunks = chunk_text(text)

    # Extract tables and append as additional chunks (fails silently if camelot unavailable)
    tables = extract_tables(path)
    chunks.extend(tables)

    try:
        create_vector_store(chunks, get_embeddings(), safe_name)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Vector store update failed: {str(e)}"})

    return {
        "msg": "Uploaded and indexed successfully",
        "filename": safe_name,
        "chunks": len(chunks)
    }

