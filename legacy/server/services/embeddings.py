from langchain_openai import OpenAIEmbeddings
from config import OPENAI_API_KEY

_embeddings = None

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    return _embeddings
