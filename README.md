# Keep2Notion

Sync Google Keep notes into Notion with:
- full note text
- images
- Google Keep labels
- per-tag Notion database routing

Images are stored in Supabase Storage. Notes can be routed into different Notion databases based on the first Google Keep label.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)

## Features

- Automatic sync from Google Keep to Notion
- Incremental and full sync modes
- Image upload to Supabase Storage, then embed in Notion
- Images inserted at top of note content in Notion
- First Google Keep label routes note to matching Notion database
- Automatic Notion database creation under a connected root page
- Fallback database name for notes without labels
- Admin UI for credentials, manual sync, job history, logs, retry, abort
- Encrypted stored credentials
- Docker Compose local setup

## Routing Rules

Keep2Notion now supports tag-based database routing:

- If note has labels, first non-empty label wins
- Label name becomes target Notion database name
- If database does not exist yet, app creates it automatically
- If note has no labels, app uses fallback database name entered on manual trigger page

Example:

- Note labels: `work`, `ideas` -> goes to database `work`
- No labels -> goes to fallback database, for example `Keep`

Important:

- Best setup is to store a Notion page URL/ID in credentials as root page
- That page must be connected to your Notion integration
- New databases are created under that page

## Screenshots

### Manual Sync Trigger

![Manual Sync Trigger](docs/images/manual-sync-trigger.png)

### Sync Job Details

![Sync Job Details](docs/images/sync-job-details.png)

### Notion Example

![Notion sample](docs/images/Notion-sample.png)

## Architecture

```text
Google Keep
  -> Keep Extractor
  -> Supabase Storage
  -> Sync Service
  -> Notion Writer
  -> Notion

PostgreSQL stores:
- sync jobs
- sync state
- encrypted credentials

Admin Interface reads PostgreSQL and drives sync actions.
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for deeper architecture notes.

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Supabase project
- Notion workspace
- Google account with Keep notes

### 1. Clone repo

```bash
git clone https://github.com/cochilocovt/keep2notion.git
cd keep2notion
```

### 2. Create env file

```bash
cp .env.example .env
```

### 3. Fill `.env`

Minimum important values:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/keep_notion_sync

SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_REAL_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET=keep-images

SECRET_KEY=your-django-secret-key
ENCRYPTION_KEY=your-base64-encryption-key
```

Notes:

- `SUPABASE_URL` must be your real project URL, not placeholder `your-project-ref`
- bucket must already exist
- bucket should be public, because Notion needs public image URLs

### 4. Generate keys

Encryption key:

```bash
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Django secret key:

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Start stack

```bash
docker compose up -d
```

### 6. Open admin UI

[http://localhost:8000](http://localhost:8000)

Main local ports:

- Admin UI: `8000`
- API Gateway: `8001`
- Keep Extractor: `8003`
- Notion Writer: `8004`
- Sync Service: `8005`
- Postgres: `5432`

## Credential Setup

Open [http://localhost:8000/config/credentials/](http://localhost:8000/config/credentials/)

You need:

- Gmail address
- Google Keep master token
- Notion API token
- Notion root page or main database URL/ID

### Google Keep master token

Repo includes helper script:

```bash
python3.11 -m pip install gpsoauth
python3.11 get_master_token_python.py
```

Recommended flow:

1. Open [https://accounts.google.com/EmbeddedSetup](https://accounts.google.com/EmbeddedSetup)
2. Sign in
3. Find `oauth_token` cookie in browser devtools
4. Paste it into helper script
5. Use returned master token in credential form

Fallback also supported:

```bash
python3.11 get_master_token_python.py --email you@gmail.com --password '...'
```

### Supabase

Create a Supabase project, then:

1. Open Storage
2. Create bucket, for example `keep-images`
3. Make bucket public
4. Open Project Settings -> API
5. Copy:
   - project URL -> `SUPABASE_URL`
   - `service_role` key -> `SUPABASE_SERVICE_ROLE_KEY`

Do not use:

- publishable key
- anon key

### Notion

Create internal integration:

1. Open [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Create integration
3. Give it at least:
   - Read content
   - Insert content
   - Update content
4. Copy token

Then connect integration to your target Notion page:

1. Open page in Notion
2. Use `...`
3. Choose `Add connections`
4. Select your integration

For best results, put page URL/ID into Keep2Notion credentials, not only a database ID.

Why:

- app can create tag databases under that page
- app can still use fallback/main database under same root

Accepted Notion formats:

- plain 32-char ID
- dashed UUID
- full Notion page URL
- full Notion database URL
- slug URLs like `https://www.notion.so/Notas-34a39cb1c2ac80fb81efd00697b44032`

## First Sync

Open [http://localhost:8000/sync/trigger/](http://localhost:8000/sync/trigger/)

Choose:

- user
- sync type
- fallback database name

Then start sync.

Behavior:

- notes with label `work` go to database `work`
- notes with label `ideas` go to database `ideas`
- notes without labels go to fallback database name from trigger form

If a target database does not exist and your credential root is a Notion page, app creates it automatically.

## Sync Job Screen

Job detail page:

- auto-refreshes while job is queued/running
- shows processed, synced, and failed counters
- shows logs
- supports retry for failed jobs
- supports abort for running jobs

Credential screen also supports:

- edit
- delete
- clear sync state

Clear sync state is useful when you want future sync to recreate Notion pages instead of updating old mapped pages.

## Common Problems

### Images missing in Notion

Usually Supabase config problem.

Check:

- `.env` has real `SUPABASE_URL`
- `.env` has real `SUPABASE_SERVICE_ROLE_KEY`
- bucket exists
- bucket is public
- containers restarted after env change

Quick check:

```bash
docker compose exec -T keep_extractor /bin/sh -lc 'printf "SUPABASE_URL=%s\nSUPABASE_STORAGE_BUCKET=%s\n" "$SUPABASE_URL" "$SUPABASE_STORAGE_BUCKET"'
```

If output still shows placeholder values, app is not using real config yet.

### Notion says integration cannot find page or database

Usually integration access problem.

Check:

- integration token is correct
- root page/database is in same workspace
- page or database is connected to integration using `Add connections`

### Job detail counters stuck at zero

Refresh with latest build. Current admin UI reads actual `processed_notes` and `failed_notes` fields correctly.

## Development

Start stack:

```bash
docker compose up -d --build
```

Run tests:

```bash
source venv/bin/activate
pytest
```

Run focused tests:

```bash
source venv/bin/activate
pytest services/notion_writer/test_writer.py -q
pytest services/sync_service/test_sync_service.py -q
```

## Deployment Docs

Additional docs:

- [Monitoring Guide](MONITORING_GUIDE.md)
- [Sync State Management](SYNC_STATE_MANAGEMENT.md)
- [Deployment Guide](deployment/README.md)

Repo still contains Kubernetes and AWS-oriented deployment examples under [`deployment/`](deployment/README.md). Runtime app storage flow for note images is now Supabase, not S3.

## License

MIT. See [LICENSE](LICENSE).

## Credits

- [gkeepapi](https://github.com/kiwiz/gkeepapi)
- [notion-sdk-py](https://github.com/ramnes/notion-sdk-py)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Django](https://www.djangoproject.com/)
