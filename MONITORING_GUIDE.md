# Monitoring Guide

## Quick Checks

### Admin UI

Open [http://localhost:8000](http://localhost:8000)

Use:

- dashboard for recent jobs and service health
- sync jobs list for history and filters
- job detail for logs and live progress

### Health Endpoints

```bash
curl http://localhost:8005/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8001/api/v1/health
```

### Docker Status

```bash
docker compose ps
docker compose logs -f
docker compose logs -f sync_service
docker compose logs -f keep_extractor
docker compose logs -f notion_writer
docker compose logs -f admin_interface
```

## Local Ports

- Admin Interface: `8000`
- API Gateway: `8001`
- Keep Extractor: `8003`
- Notion Writer: `8004`
- Sync Service: `8005`
- PostgreSQL: `5432`

## Job Detail Screen

Job detail page auto-refreshes while job is:

- `queued`
- `running`

It shows:

- items processed
- items synced
- errors
- logs

Current counters come from:

- `processed_notes`
- `failed_notes`

## Triggering and Inspecting Jobs

### Manual sync from UI

Open [http://localhost:8000/sync/trigger/](http://localhost:8000/sync/trigger/)

Choose:

- user
- sync type
- fallback database name

### Trigger via Sync Service

```bash
curl -X POST http://localhost:8005/internal/sync/execute \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "your-email@gmail.com",
    "full_sync": false,
    "main_database_name": "Keep"
  }'
```

### Check job status

```bash
curl http://localhost:8005/internal/sync/status/JOB_ID
```

## Common Problems

### Images missing in Notion

Usually Supabase config issue.

Check:

```bash
docker compose exec -T keep_extractor /bin/sh -lc 'printf "SUPABASE_URL=%s\nSUPABASE_STORAGE_BUCKET=%s\n" "$SUPABASE_URL" "$SUPABASE_STORAGE_BUCKET"'
```

If output still shows placeholder values like `your-project-ref`, uploads will fail and image URLs will be `null`.

Also verify:

- bucket exists
- bucket is public
- `SUPABASE_SERVICE_ROLE_KEY` is real service role key

### Notion access errors

Check:

- integration token is correct
- target root page or database is connected to integration
- page/database is in same workspace as integration

### Job stuck at `QUEUED`

Current app should move jobs out of `QUEUED` correctly. If you still see this:

- inspect `sync_service` logs
- inspect `sync_jobs` row
- confirm background task started

### Counters stay zero

Current admin UI reads the correct progress fields. If you still see zero:

- rebuild `admin_interface`
- refresh the job page
- confirm job row has non-zero `processed_notes` / `failed_notes`

## Useful Log Searches

```bash
docker compose logs sync_service | grep -i "failed to process"
docker compose logs keep_extractor | grep -i "supabase"
docker compose logs notion_writer | grep -i "failed to create"
docker compose logs notion_writer | grep -i "failed to update"
```

## Notes

For current deployment and runtime setup, use the docs under [`deployment/`](deployment/README.md).
