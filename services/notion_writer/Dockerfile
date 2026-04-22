# Notion Writer Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy shared package
COPY shared/ /app/shared/

# Copy service files
COPY services/notion_writer/ /app/services/notion_writer/

# Install dependencies with retry (skip pip upgrade to avoid network issues)
RUN pip install --no-cache-dir --retries 5 --timeout 60 -r /app/shared/requirements.txt && \
    pip install --no-cache-dir --retries 5 --timeout 60 -r /app/services/notion_writer/requirements.txt

# Set Python path
ENV PYTHONPATH=/app

WORKDIR /app/services/notion_writer

# Expose port
EXPOSE 8004

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8004/health', timeout=5).read()"

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
