# Database Layer Documentation

## Overview

The database layer provides SQLAlchemy models and operations for managing sync state, credentials, and job tracking in the Google Keep to Notion sync application.

## Components

### Models (`db_models.py`)

Four main database models:

1. **SyncJob** - Tracks sync job execution
   - `job_id` (UUID): Primary key
   - `user_id` (str): User identifier
   - `status` (str): Job status (queued, running, completed, failed)
   - `full_sync` (bool): Whether this is a full or incremental sync
   - `total_notes`, `processed_notes`, `failed_notes` (int): Progress tracking
   - `error_message` (str): Error details if failed
   - `created_at`, `completed_at` (datetime): Timestamps

2. **SyncState** - Tracks which notes have been synced
   - `id` (int): Primary key
   - `user_id` (str): User identifier
   - `keep_note_id` (str): Google Keep note ID
   - `notion_page_id` (str): Corresponding Notion page ID
   - `last_synced_at` (datetime): Last sync timestamp
   - `keep_modified_at` (datetime): Last modification time in Keep
   - Unique constraint on (user_id, keep_note_id)

3. **Credential** - Stores encrypted user credentials
   - `user_id` (str): Primary key
   - `google_oauth_token` (str): Encrypted Google OAuth token
   - `notion_api_token` (str): Encrypted Notion API token
   - `notion_database_id` (str): Notion database ID
   - `updated_at` (datetime): Last update timestamp

4. **SyncLog** - Detailed logging for sync jobs
   - `id` (int): Primary key
   - `job_id` (UUID): Foreign key to SyncJob
   - `keep_note_id` (str): Optional note ID
   - `level` (str): Log level (INFO, WARNING, ERROR)
   - `message` (str): Log message
   - `created_at` (datetime): Log timestamp

### Operations (`db_operations.py`)

The `DatabaseOperations` class provides methods for:

#### Sync State Operations
- `get_sync_state_by_user(user_id)` - Get all sync records for a user
- `get_sync_record(user_id, keep_note_id)` - Get specific sync record
- `upsert_sync_state(...)` - Insert or update sync state

#### Credential Management
- `store_credentials(...)` - Store encrypted credentials
- `get_credentials(user_id, encryption_service)` - Retrieve and decrypt credentials
- `delete_credentials(user_id)` - Delete user credentials

#### Sync Job Tracking
- `create_sync_job(job_id, user_id, full_sync)` - Create new sync job
- `update_sync_job(job_id, ...)` - Update job progress
- `get_sync_job(job_id)` - Get job by ID
- `get_sync_jobs_by_user(user_id, limit, offset)` - Get user's jobs with pagination
- `increment_sync_job_progress(job_id, processed, failed)` - Increment counters

#### Sync Log Operations
- `add_sync_log(job_id, level, message, keep_note_id)` - Add log entry
- `get_sync_logs(job_id, limit)` - Get logs for a job

### Encryption (`encryption.py`)

The `EncryptionService` class provides AES-256 encryption for credentials:

- `encrypt(plaintext)` - Encrypt a string
- `decrypt(ciphertext)` - Decrypt a string
- `generate_key()` - Generate new encryption key

Uses Fernet (symmetric encryption) from the cryptography library.

## Usage Example

```python
from shared.db_operations import DatabaseOperations
from shared.encryption import EncryptionService
from uuid import uuid4
from datetime import datetime

# Initialize
db = DatabaseOperations()
db.create_tables()
encryption = EncryptionService()

# Create a sync job
job_id = uuid4()
job = db.create_sync_job(job_id, "user123", full_sync=True)

# Store credentials
db.store_credentials(
    user_id="user123",
    google_oauth_token="google_token",
    notion_api_token="notion_token",
    notion_database_id="db_id",
    encryption_service=encryption
)

# Retrieve credentials
creds = db.get_credentials("user123", encryption)
print(creds['google_oauth_token'])  # Decrypted token

# Track sync state
db.upsert_sync_state(
    user_id="user123",
    keep_note_id="note_1",
    notion_page_id="page_1",
    keep_modified_at=datetime.utcnow()
)

# Update job progress
db.increment_sync_job_progress(job_id, processed=1, failed=0)

# Add log
db.add_sync_log(job_id, "INFO", "Processing note_1", keep_note_id="note_1")

# Complete job
db.update_sync_job(
    job_id,
    status="completed",
    completed_at=datetime.utcnow()
)
```

## Configuration

Set the database URL via environment variable:
```bash
export DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"
```

For encryption, set the encryption key:
```bash
export ENCRYPTION_KEY="your-base64-encoded-key"
```

## Testing

Run tests with:
```bash
pytest shared/test_db_operations.py -v
```

Tests use in-memory SQLite for fast execution.
