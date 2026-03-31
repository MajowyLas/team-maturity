FROM python:3.11-slim

WORKDIR /app

# Copy source and data
COPY pyproject.toml .
COPY app/ app/
COPY data/ data/

# Install the package (needs app/ present for setuptools find_packages)
RUN pip install --no-cache-dir .

# Render sets PORT; default 8000 for local docker testing
ENV PORT=8000

EXPOSE ${PORT}

CMD ["team-maturity"]
