FROM python:3.11-slim

WORKDIR /app

# Copy everything
COPY app/ app/
COPY data/ data/

# Install pinned dependencies — jinja2 3.1.3 avoids template cache bug
# Cache-bust: v3
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Render sets PORT; default 8000 for local docker testing
ENV PORT=8000
EXPOSE ${PORT}

# Run uvicorn directly from /app — app/ is a local package, no pip install needed
CMD python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
