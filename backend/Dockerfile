FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies first (separate layer for Docker cache efficiency).
# When only requirements.txt changes, Docker rebuilds from here without touching the OS layer.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Source code is provided at runtime via a volume mount (docker-compose.yml).
# This COPY is here so the image also works standalone (e.g. in CI or production).
COPY . .

EXPOSE 8000

# --reload enables hot-reload when the source volume is mounted.
# In production this will be replaced with a fixed worker count via Gunicorn.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
