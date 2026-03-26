import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# DATA_DIR can be overridden via environment variable.
# Docker sets DATA_DIR=/data; locally it defaults to <project-root>/data
_server_dir = os.path.dirname(os.path.abspath(__file__))
_default_data_dir = os.path.join(os.path.dirname(_server_dir), "data")
DATA_DIR = os.getenv("DATA_DIR", _default_data_dir)

CHROMA_DB_DIR = os.path.join(DATA_DIR, "chroma_db")
RAW_DOCS_DIR  = os.path.join(DATA_DIR, "raw_docs")
EVAL_LOG_FILE = os.path.join(DATA_DIR, "eval_logs", "eval_logs.json")
