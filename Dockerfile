FROM python:3.10-slim

# System dependencies: ghostscript for camelot, libgl1/libglib2.0 for opencv
RUN apt-get update && apt-get install -y \
    ghostscript \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY legacy/server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY legacy/server/ ./

# Create data directories inside the container
RUN mkdir -p /data/raw_docs /data/chroma_db /data/eval_logs

# Tell config.py where to find data (avoids fragile dirname(__file__) resolution)
ENV DATA_DIR=/data

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
