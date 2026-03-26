from langchain_community.vectorstores import Chroma
from config import CHROMA_DB_DIR

def create_vector_store(chunks, embeddings, doc_name):
    """Create or update the vector store with new chunks."""
    db = Chroma(
        persist_directory=CHROMA_DB_DIR,
        embedding_function=embeddings
    )

    metadatas = [{"doc": doc_name} for _ in chunks]
    db.add_texts(texts=chunks, metadatas=metadatas)
    # NOTE: .persist() was removed in chromadb >= 0.4.x — persistence is automatic
    return db

def load_vector_store(embeddings):
    """Load existing vector store from disk."""
    return Chroma(
        persist_directory=CHROMA_DB_DIR,
        embedding_function=embeddings
    )
