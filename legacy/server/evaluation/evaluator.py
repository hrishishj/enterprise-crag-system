import json
import os
from datetime import datetime
from config import EVAL_LOG_FILE

def log_eval(query: str, answer: str, sources: list) -> None:
    """Append a query/answer evaluation record to the log file."""
    record = {
        "time": str(datetime.now()),
        "query": query,
        "answer": answer,
        "sources": sources
    }

    os.makedirs(os.path.dirname(EVAL_LOG_FILE), exist_ok=True)

    # Load existing data safely
    data = []
    if os.path.exists(EVAL_LOG_FILE):
        try:
            with open(EVAL_LOG_FILE, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            data = []

    data.append(record)

    with open(EVAL_LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)
