# Keep Extractor Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy shared package
COPY shared/ /app/shared/

# Copy service files
COPY services/keep_extractor/ /app/services/keep_extractor/

# Install dependencies with retry (skip pip upgrade to avoid network issues)
RUN pip install --no-cache-dir --retries 5 --timeout 60 -r /app/shared/requirements.txt && \
    pip install --no-cache-dir --retries 5 --timeout 60 -r /app/services/keep_extractor/requirements.txt

# Set Python path
ENV PYTHONPATH=/app

WORKDIR /app/services/keep_extractor

# Expose port
EXPOSE 8003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8003/health', timeout=5).read()"

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]
