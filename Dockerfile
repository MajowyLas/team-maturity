FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code and data
COPY app/ app/
COPY data/ data/

# Render sets PORT; default 8000 for local docker testing
ENV PORT=8000

EXPOSE ${PORT}

CMD ["team-maturity"]
