# Database Layer Documentation

## Overview

The shared database layer provides SQLAlchemy models and helper operations for:

- sync jobs
- sync state
- encrypted credentials
- sync logs

Primary implementation files:

- `shared/db_models.py`
- `shared/db_operations.py`
- `shared/encryption.py`

## Core Tables

### `sync_jobs`

Tracks each sync run.

Important fields:

- `job_id`
- `user_id`
- `status`
- `full_sync`
- `total_notes`
- `processed_notes`
- `failed_notes`
- `error_message`
- `created_at`
- `completed_at`

### `sync_state`

Tracks current mapping between Keep note and Notion page.

Important fields:

- `user_id`
- `keep_note_id`
- `notion_page_id`
- `keep_modified_at`
- `last_synced_at`

### `credentials`

Stores encrypted secrets plus Notion routing root.

Important fields:

- `user_id`
- `google_oauth_token`
  This now stores the Google Keep master token used by the app.
- `notion_api_token`
- `notion_database_id`
  Legacy column name. Current meaning is:
  Notion root page or main database URL/ID.
- `updated_at`

### `sync_logs`

Stores detailed per-job log messages shown in admin UI.

Important fields:

- `job_id`
- `keep_note_id`
- `level`
- `message`
- `created_at`

## Key Operations

`DatabaseOperations` provides methods for:

- create/update/get sync jobs
- increment sync progress
- store/delete/get encrypted credentials
- upsert sync state
- add/get sync logs
- delete sync state for a user

## Current Credential Semantics

Current app behavior is:

- `google_oauth_token` = encrypted Google Keep master token
- `notion_database_id` = root page or main database reference

Using a Notion page as root is recommended because tag-based routing can auto-create child databases under that page.

## Usage Example

```python
from uuid import uuid4
from datetime import datetime

from shared.db_operations import DatabaseOperations
from shared.encryption import EncryptionService

db = DatabaseOperations()
encryption = EncryptionService()

job_id = uuid4()
db.create_sync_job(job_id, "user@example.com", full_sync=True)

db.store_credentials(
    user_id="user@example.com",
    google_oauth_token="google-keep-master-token",
    notion_api_token="secret_...",
    notion_database_id="https://www.notion.so/Root-Page-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    encryption_service=encryption,
)

credentials = db.get_credentials("user@example.com", encryption)

db.upsert_sync_state(
    user_id="user@example.com",
    keep_note_id="keep-note-id",
    notion_page_id="notion-page-id",
    keep_modified_at=datetime.utcnow(),
)

db.increment_sync_job_progress(job_id, processed=1, failed=0)
db.add_sync_log(job_id, "INFO", "Processed note", keep_note_id="keep-note-id")
```

## Environment Variables

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/keep_notion_sync"
export ENCRYPTION_KEY="your-base64-key"
```

## Testing

```bash
pytest shared/test_db_operations.py -v
```
