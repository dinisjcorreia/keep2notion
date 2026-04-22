# Deployment Guide

This directory contains deployment-oriented material for running Keep2Notion outside local Docker Compose.

Current runtime assumptions:

- PostgreSQL for app state
- Supabase Storage for note images
- Notion integration token
- Google Keep master token
- Docker images for each service

## Directory Layout

```text
deployment/
├── kubernetes/          # Kubernetes manifests and notes
├── security/            # HTTPS, logging, and storage-safety guidance
├── testing/             # End-to-end deployment validation
├── PRODUCTION_DEPLOYMENT.md
├── STAGING_DEPLOYMENT_GUIDE.md
└── README.md
```

## Services

Keep2Notion deploys these app services:

- `admin_interface` on `8000`
- `api_gateway` on `8001`
- `keep_extractor` on `8003`
- `notion_writer` on `8004`
- `sync_service` on `8005`
- PostgreSQL on `5432`

## Required Runtime Configuration

Minimum required environment variables:

```env
DATABASE_URL=postgresql://...

SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_STORAGE_BUCKET=keep-images

ENCRYPTION_KEY=your-base64-encryption-key
SECRET_KEY=your-django-secret-key
```

App credentials stored through admin UI:

- Gmail / user id
- Google Keep master token
- Notion API token
- Notion root page or main database URL/ID

## Deployment Paths

Recommended options:

1. Docker Compose for single-host deployment
2. Kubernetes for staged or production environments

## Important Behavior

### Image Storage

Current app stores note images in Supabase Storage and writes public image URLs into Notion image blocks.

### Database Routing

Notes route by Google Keep label:

- first non-empty label wins
- database name = label name
- if no label exists, app uses fallback database name from manual trigger
- missing databases can be auto-created under connected Notion root page

## Recommended Reading Order

1. [STAGING_DEPLOYMENT_GUIDE.md](STAGING_DEPLOYMENT_GUIDE.md)
2. [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)
3. [kubernetes/README.md](kubernetes/README.md)
4. [security/HTTPS_CONFIGURATION.md](security/HTTPS_CONFIGURATION.md)
5. [testing/END_TO_END_TESTS.md](testing/END_TO_END_TESTS.md)
