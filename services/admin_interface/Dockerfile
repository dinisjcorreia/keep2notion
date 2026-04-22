# Admin Interface Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy shared package
COPY shared/ /app/shared/

# Copy service files
COPY services/admin_interface/ /app/services/admin_interface/

# Upgrade pip and install dependencies with retry
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --retries 5 --timeout 60 -r /app/shared/requirements.txt && \
    pip install --no-cache-dir --retries 5 --timeout 60 -r /app/services/admin_interface/requirements.txt

# Set Python path
ENV PYTHONPATH=/app

WORKDIR /app/services/admin_interface

# Collect static files (will be configured later)
# RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8000/', timeout=5).read()"

# Run the application with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "admin_project.wsgi:application"]
