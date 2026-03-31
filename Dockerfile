FROM python:3.11-slim

WORKDIR /app

# Copy source and data
COPY pyproject.toml .
COPY app/ app/
COPY data/ data/

# Install dependencies only (don't install the package itself to site-packages,
# so Path(__file__) resolves to /app/app/ where templates & static files live)
RUN pip install --no-cache-dir -e .

# Render sets PORT; default 8000 for local docker testing
ENV PORT=8000

EXPOSE ${PORT}

CMD python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
