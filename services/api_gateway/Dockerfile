# API Gateway Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy shared package
COPY shared/ /app/shared/

# Copy service files
COPY services/api_gateway/ /app/services/api_gateway/

# Upgrade pip and install dependencies with retry
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --retries 5 --timeout 60 -r /app/shared/requirements.txt && \
    pip install --no-cache-dir --retries 5 --timeout 60 -r /app/services/api_gateway/requirements.txt

# Set Python path
ENV PYTHONPATH=/app

WORKDIR /app/services/api_gateway

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8001/health', timeout=5).read()"

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
