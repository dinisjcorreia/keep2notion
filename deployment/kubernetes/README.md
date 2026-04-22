# Kubernetes Deployment

This folder contains Kubernetes manifests you can adapt for Keep2Notion.

## Services and Ports

- `admin_interface`: `8000`
- `api_gateway`: `8001`
- `keep_extractor`: `8003`
- `notion_writer`: `8004`
- `sync_service`: `8005`

## Recommended Exposure Model

Public:

- `admin_interface`
- `api_gateway`

Internal only:

- `keep_extractor`
- `notion_writer`
- `sync_service`

## Required Config

ConfigMap-style values:

```env
DATABASE_URL=postgresql://...
KEEP_EXTRACTOR_URL=http://keep-extractor-service:8003
NOTION_WRITER_URL=http://notion-writer-service:8004
SYNC_SERVICE_URL=http://sync-service:8005
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_STORAGE_BUCKET=keep-images
```

Secret-style values:

```env
SUPABASE_SERVICE_ROLE_KEY=...
ENCRYPTION_KEY=...
SECRET_KEY=...
```

## Deployment Order

1. namespace
2. config and secrets
3. postgres dependency or external db connection
4. keep_extractor
5. notion_writer
6. sync_service
7. api_gateway
8. admin_interface
9. ingress

## Probes

Recommended health probes:

- `admin_interface`: `/`
- `api_gateway`: `/api/v1/health`
- `keep_extractor`: `/health`
- `notion_writer`: `/health`
- `sync_service`: `/health`

## Storage Notes

App does not need in-cluster object storage for note images.

It relies on Supabase Storage:

- uploads happen from `keep_extractor`
- public image URLs are consumed by `notion_writer`

## Operational Notes

- use rolling deployments
- keep only one source of truth for env vars
- do not mix placeholder Supabase values into live workloads
- secure internal services with network policies if available
