# Admin Interface Service

Django admin UI for Keep2Notion.

## What It Does

Admin UI provides:

- dashboard
- sync job history
- sync job detail with logs
- manual sync trigger
- credential management
- retry and abort controls
- clear sync state action

## Stack

- Django 4.2
- Gunicorn
- PostgreSQL
- httpx

## Local Port

`8000`

## Main Screens

### Credential Configuration

Stores:

- Gmail/user id
- Google Keep master token
- Notion API token
- Notion root page or main database URL/ID

Notes:

- token fields are encrypted before storage
- edit screen can keep masked tokens without forcing re-entry
- list supports edit, delete, and clear sync state

### Manual Sync Trigger

Lets you choose:

- user
- full or incremental sync
- fallback database name

Fallback database name is used for notes without Google Keep labels.

### Sync Job Detail

Shows:

- job status
- items processed
- items synced
- errors
- detailed logs

Page auto-refreshes while job is queued or running.

## Environment Variables

- `DATABASE_URL`
- `SECRET_KEY`
- `SYNC_SERVICE_URL`
- `LOG_LEVEL`

Current local Sync Service URL:

```bash
export SYNC_SERVICE_URL=http://localhost:8005
```

## Local Run

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Or with Gunicorn:

```bash
gunicorn admin_project.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

## Tests

```bash
python manage.py test
```

Focused example:

```bash
python manage.py test test_sync_job_views.SyncJobViewsTest
```
