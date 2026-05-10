FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        git \
        ffmpeg \
        tesseract-ocr \
        tesseract-ocr-eng \
        libglib2.0-0 \
        libgl1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "-m", "main"]
