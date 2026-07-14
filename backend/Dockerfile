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

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8000

CMD ["/start.sh"]