FROM python:3.11-slim

WORKDIR /app

# Copy everything
COPY pyproject.toml .
COPY app/ app/
COPY data/ data/

# Install only the dependencies (not the package itself)
RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "sqlalchemy>=2.0.0" \
    "jinja2>=3.1.0" \
    "python-multipart>=0.0.9"

# Render sets PORT; default 8000 for local docker testing
ENV PORT=8000
EXPOSE ${PORT}

# Run uvicorn directly from /app — app/ is a local package, no pip install needed
CMD python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
