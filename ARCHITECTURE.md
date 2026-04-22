# Architecture Overview

## Summary

Keep2Notion is a Python microservices app that:

- reads notes from Google Keep
- uploads note images to Supabase Storage
- writes notes into Notion
- tracks sync jobs and sync state in PostgreSQL
- exposes admin controls through a Django UI

Current runtime image flow is:

`Google Keep -> Keep Extractor -> Supabase Storage -> Notion Writer -> Notion`

## Services

### Admin Interface

- Framework: Django
- Port: `8000`
- Purpose: credentials, manual sync, job list, job detail, retry, abort

### API Gateway

- Framework: FastAPI
- Port: `8001`
- Purpose: external API for health, sync start, sync status, history

### Keep Extractor

- Framework: FastAPI
- Port: `8003`
- Purpose: authenticate with Google Keep, extract notes, download images, upload images to Supabase Storage

### Notion Writer

- Framework: FastAPI
- Port: `8004`
- Purpose: resolve target database, create missing databases, create/update Notion pages

### Sync Service

- Framework: FastAPI
- Port: `8005`
- Purpose: orchestrate sync workflow, track progress, update sync state, handle retries and failures

### PostgreSQL

- Port: `5432`
- Purpose: store sync jobs, sync state, encrypted credentials, sync logs

## Data Model

### `credentials`

Stores:

- Gmail/user id
- encrypted Google Keep master token
- encrypted Notion API token
- Notion root page or main database reference

### `sync_jobs`

Stores:

- job status
- full vs incremental mode
- total note count
- processed note count
- failed note count
- error message

### `sync_state`

Maps:

- `user_id + keep_note_id -> notion_page_id`

This lets incremental sync update existing pages instead of always creating new ones.

### `sync_logs`

Stores per-job logs for the admin detail screen.

## Current Sync Flow

1. User starts sync from admin UI or API.
2. Sync Service loads encrypted credentials from PostgreSQL.
3. Sync Service asks Keep Extractor for notes.
4. Keep Extractor downloads note images from Google Keep.
5. Keep Extractor uploads images to Supabase Storage and returns public URLs.
6. Sync Service decides target Notion database for each note.
7. Notion Writer reuses or creates databases based on routing rules.
8. Notion Writer creates or updates Notion pages.
9. Sync Service updates `sync_state`, `sync_jobs`, and `sync_logs`.

## Database Routing Rules

Current routing behavior:

- first non-empty Google Keep label wins
- target database name = that label
- if note has no labels, app uses fallback database name from manual trigger page
- if target database does not exist and credential root is a Notion page, app creates it automatically

Examples:

- labels `work`, `ideas` -> database `work`
- no labels -> fallback database, for example `Keep`

## Important Runtime Notes

- Supabase Storage is used for note image storage
- Notion image blocks use public external URLs from Supabase Storage
- best credential setup is a Notion page URL/ID, not only a single database ID
- Sync Service port is `8005`, not `8002`

## Local Development

Main entrypoint for local use:

```bash
docker compose up -d
```

Open:

- Admin UI: [http://localhost:8000](http://localhost:8000)
- API Gateway: [http://localhost:8001](http://localhost:8001)

## Deployment Notes

See [`deployment/`](deployment/README.md) for current deployment documentation.
