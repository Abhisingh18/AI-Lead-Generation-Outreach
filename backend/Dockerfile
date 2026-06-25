# Playwright base image already includes Chromium + all OS libs (matches v1.49.1).
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

# xvfb = virtual display, so the headed WhatsApp browser can run on a screenless
# cloud server (Render). Without it Chromium errors: "Missing X server or $DISPLAY".
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure the chromium browser is present.
RUN python -m playwright install chromium

# App code.
COPY . .

ENV PYTHONUNBUFFERED=1

# Scraping runs headless (no display needed). WhatsApp (which needs xvfb) is
# disabled on the cloud due to the free-tier RAM limit — run it on your laptop.
# To re-enable WhatsApp on a paid instance, wrap this with: xvfb-run -a ...
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
