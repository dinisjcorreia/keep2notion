# Sync Service

The Sync Service is the orchestrator for the Google Keep to Notion synchronization workflow. It coordinates between the Keep Extractor and Notion Writer services to perform the actual data synchronization.

## Overview

The Sync Service is responsible for:
- Loading user credentials from the database
- Determining which notes need to be synchronized (full or incremental)
- Calling the Keep Extractor service to fetch notes
- Calling the Notion Writer service to create or update pages
- Tracking sync progress and state
- Handling errors gracefully and logging all operations
- Sending notifications for critical errors

## Architecture

```
┌─────────────────┐
│  API Gateway    │
│  Admin Interface│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Sync Service   │ ◄── Orchestrator
└────┬───────┬────┘
     │       │
     ▼       ▼
┌─────────┐ ┌──────────────┐
│  Keep   │ │   Notion     │
│Extractor│ │   Writer     │
└─────────┘ └──────────────┘
```

## Endpoints

### Internal Endpoints

#### POST /internal/sync/execute
Execute a synchronization job.

**Request:**
```json
{
  "job_id": "uuid",
  "user_id": "string",
  "full_sync": false
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "completed|failed",
  "summary": {
    "total_notes": 10,
    "processed_notes": 10,
    "failed_notes": 0
  },
  "error": "error message if failed"
}
```

#### GET /internal/sync/status/{job_id}
Get the status of a sync job.

**Response:**
```json
{
  "job_id": "uuid",
  "status": "queued|running|completed|failed",
  "progress": {
    "total_notes": 10,
    "processed_notes": 5,
    "failed_notes": 0
  },
  "created_at": "2024-01-01T00:00:00",
  "completed_at": "2024-01-01T00:05:00",
  "error_message": "error if failed"
}
```

### Health Check

#### GET /health
Check service health and dependencies.

**Response:**
```json
{
  "status": "healthy|degraded",
  "service": "sync_service",
  "version": "0.1.0",
  "dependencies": {
    "database": "up|down",
    "keep_extractor": "up|down",
    "notion_writer": "up|down"
  }
}
```

## Components

### SyncOrchestrator
The main orchestration class that handles the sync workflow:
1. Loads user credentials
2. Determines notes to sync (full or incremental)
3. Fetches notes from Keep Extractor
4. Processes each note (create or update in Notion)
5. Updates sync state
6. Tracks progress and handles errors

### NotificationService
Handles sending notifications for critical errors. Can be configured to send notifications via:
- AWS SNS
- Slack webhooks
- Email via AWS SES
- PagerDuty
- Custom webhook URLs

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@localhost:5432/keep_notion_sync` |
| `KEEP_EXTRACTOR_URL` | Keep Extractor service URL | `http://localhost:8003` |
| `NOTION_WRITER_URL` | Notion Writer service URL | `http://localhost:8004` |
| `SYNC_SERVICE_PORT` | Port to run the service on | `8005` |
| `ENCRYPTION_KEY` | Encryption key for credentials | Generated if not provided |
| `ENABLE_NOTIFICATIONS` | Enable critical error notifications | `false` |
| `NOTIFICATION_WEBHOOK_URL` | Webhook URL for notifications | None |

## Running the Service

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/keep_notion_sync"
export KEEP_EXTRACTOR_URL="http://localhost:8003"
export NOTION_WRITER_URL="http://localhost:8004"

# Run the service
python -m uvicorn services.sync_service.main:app --host 0.0.0.0 --port 8005
```

### Docker

```bash
# Build the image
docker build -t sync-service -f services/sync_service/Dockerfile .

# Run the container
docker run -p 8005:8005 \
  -e DATABASE_URL="postgresql://postgres:postgres@postgres:5432/keep_notion_sync" \
  -e KEEP_EXTRACTOR_URL="http://keep_extractor:8003" \
  -e NOTION_WRITER_URL="http://notion_writer:8004" \
  sync-service
```

### Docker Compose

```bash
# Start all services
docker-compose up sync_service
```

## Error Handling

The Sync Service implements comprehensive error handling:

1. **Individual Note Failures**: If a single note fails to sync, the service logs the error and continues processing other notes
2. **Service Failures**: If Keep Extractor or Notion Writer fails, the error is logged and the job is marked as failed
3. **Database Failures**: Database errors are caught and logged, with the job marked as failed
4. **Critical Errors**: Critical errors trigger notifications (if enabled) to alert administrators

All errors are logged to:
- Application logs (stdout)
- Database sync_logs table
- Notification channels (if configured)

## Logging

The service logs all operations at different levels:
- **INFO**: Normal operations (sync started, notes processed, sync completed)
- **WARNING**: Non-critical issues (individual note failures)
- **ERROR**: Critical errors (service failures, database errors)

Logs are written to:
1. Standard output (captured by Docker/Kubernetes)
2. Database sync_logs table (for historical tracking)

## Testing

```bash
# Run unit tests
pytest services/sync_service/test_sync_service.py -v

# Run integration tests
python test_sync_service_integration.py
```

## Dependencies

- FastAPI: Web framework
- httpx: HTTP client for calling other services
- SQLAlchemy: Database ORM
- psycopg2-binary: PostgreSQL driver
- pydantic: Data validation

## Future Enhancements

- [ ] Implement retry logic for failed notes
- [ ] Add support for batch processing
- [ ] Implement rate limiting for API calls
- [ ] Add metrics and monitoring (Prometheus)
- [ ] Implement circuit breaker pattern for service calls
- [ ] Add support for webhooks to notify external systems
- [ ] Implement job scheduling and queuing
