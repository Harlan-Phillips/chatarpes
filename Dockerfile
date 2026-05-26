FROM python:3.12-slim

WORKDIR /app

# System dependencies for matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY analysis/ ./analysis/
COPY data/ ./data/
COPY knowledge/ ./knowledge/

EXPOSE 8000

# `backend/app/__init__.py` adds the repo root (/app) to sys.path so
# `from analysis...` keeps working. We just need `app` to be importable
# as a top-level module, so launch uvicorn from /app/backend.
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
