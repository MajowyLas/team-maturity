FROM python:3.11-slim

WORKDIR /app

# Copy everything
COPY app/ app/
COPY data/ data/
COPY seed_dummy.py .
COPY start.sh .

# Install pinned dependencies — jinja2 3.1.3 avoids template cache bug
# Cache-bust: v4
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-seed dummy data into a default DB at /app/maturity.db
RUN python seed_dummy.py

# Make start script executable
RUN chmod +x start.sh

# Render sets PORT; default 8000 for local docker testing
ENV PORT=8000
EXPOSE ${PORT}

# Smart startup: copies pre-seeded DB to persistent disk if needed
CMD ["./start.sh"]
