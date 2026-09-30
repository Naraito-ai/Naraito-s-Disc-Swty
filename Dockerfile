FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and build essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure permissions for Hugging Face container user (UID 1000)
RUN useradd -m -u 1000 user || true && \
    chown -R 1000:1000 /app || true

USER 1000

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV PORT=7860

EXPOSE 7860 8080

CMD ["python", "bot.py"]


