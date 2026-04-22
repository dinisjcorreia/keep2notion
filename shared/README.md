# Shared Package

This package contains common data models and utilities used across all microservices.

## Contents

- **models.py**: Shared data models (KeepNote, ImageAttachment, SyncJobRequest, etc.)
- **config.py**: Configuration utilities for environment variables and storage settings

## Usage

All services import from this shared package:

```python
from shared.models import KeepNote, SyncJobRequest
from shared.config import get_database_url, get_supabase_storage_config
```

## Data Models

### KeepNote
Represents a note from Google Keep with title, content, timestamps, labels, and images.

### ImageAttachment
Represents an image attachment with external storage URL and metadata.

### SyncJobRequest
Request object for initiating a sync job.

### SyncJobStatus
Status information for a running or completed sync job.

### SyncStateRecord
Record of sync state for tracking which notes have been synced.

## Configuration

The `config.py` module provides utilities for accessing environment variables:

- `get_env()`: Get environment variable with optional default and validation
- `get_database_url()`: Get PostgreSQL connection string
- `get_supabase_storage_config()`: Get Supabase Storage configuration
