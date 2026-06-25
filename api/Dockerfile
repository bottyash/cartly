FROM python:3.10-slim

# Build-time args
ARG ENVIRONMENT=production

WORKDIR /app

# System deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source packages
COPY api/           ./api/
COPY agents/        ./agents/
COPY data/          ./data/
COPY observability/ ./observability/
COPY scripts/       ./scripts/

# Create log directory
RUN mkdir -p /app/observability/logs

ENV PYTHONPATH=/app
ENV ENVIRONMENT=${ENVIRONMENT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -sf http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
