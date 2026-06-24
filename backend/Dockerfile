# Playwright base image already includes Chromium + all OS libs (matches v1.49.1).
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

# Install Python deps first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure the chromium browser is present.
RUN python -m playwright install chromium

# App code.
COPY . .

ENV PYTHONUNBUFFERED=1

# Render provides $PORT. Bind to it (default 8000 for local docker runs).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
