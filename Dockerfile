FROM python:3.13-slim
WORKDIR /app

# Install build dependencies and libstdc++ for numpy
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libstdc++6 && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Pinned: openbb 5.x no longer installs openbb-equity, so obb.equity is
# missing and every quote fails. 4.7.2 is the known-good line (it also fits
# the 30s quote budget at ~4.7s per symbol).
RUN pip install --no-cache-dir openbb==4.7.2 openbb-yfinance==1.6.3

# Copy application code
COPY . .

# Local tailnet LLM routes. Scheduled runs use Kalliope Ornith; DS4 is an
# explicit manual override inside the image only.
# The bearer token is injected at runtime via `docker run -e KALLIOPE_SERVING_API_KEY`.
ENV KALLIOPE_SERVING_API_KEY=
ENV FINANCE_NEWS_ORNITH_BASE_URL=http://100.124.155.99:4000/v1
ENV FINANCE_NEWS_ORNITH_MODEL=mama-resident
ENV FINANCE_NEWS_DS4_BASE_URL=http://100.120.26.16:8888/v1
ENV FINANCE_NEWS_DS4_API_KEY=dsv4-local
ENV FINANCE_NEWS_DS4_MODEL=deepseek-v4-flash-0731
ENV FINANCE_NEWS_SUPPRESS_VENV_WARNING=1
ENV OPENBB_QUOTE_BIN=/app/scripts/openbb-quote

# Default command (override via docker run args)
CMD ["python3", "scripts/briefing.py"]
