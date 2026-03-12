FROM python:3.11-slim

WORKDIR /app

# Install dependencies only
COPY pyproject.toml .
RUN pip install --no-cache-dir . && pip cache purge || true

# Copy application code and data
COPY app/ app/
COPY data/ data/

# Render sets PORT; default 8000 for local docker testing
ENV PORT=8000

EXPOSE ${PORT}

CMD ["python", "-c", "from app.main import cli; cli()"]
