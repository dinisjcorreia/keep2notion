# Production Deployment

This guide describes a production-ready deployment shape for Keep2Notion.

## Production Goals

- stable PostgreSQL
- durable Supabase Storage configuration
- HTTPS for public entrypoints
- isolated service networking
- encrypted secrets injection
- observability for jobs and service health

## Recommended Architecture

```text
Internet
  -> HTTPS ingress / reverse proxy
  -> admin_interface
  -> api_gateway

Internal network
  -> sync_service
  -> keep_extractor
  -> notion_writer
  -> PostgreSQL

External managed services
  -> Supabase Storage
  -> Notion API
  -> Google Keep login flow
```

## Production Checklist

- domain names ready
- HTTPS termination configured
- PostgreSQL backup strategy configured
- Supabase project and public bucket ready
- secrets injected securely
- health checks enabled
- log retention defined
- alerting defined

## Required Secrets

Infrastructure/runtime:

- `DATABASE_URL`
- `ENCRYPTION_KEY`
- `SECRET_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_STORAGE_BUCKET`

Stored in app database through credential UI:

- Google Keep master token
- Notion API token
- Notion root page or main database reference

## Kubernetes Notes

If deploying to Kubernetes:

- run PostgreSQL outside cluster or as managed service if possible
- inject env vars via Secret and ConfigMap
- expose only `admin_interface` and `api_gateway`
- keep other services ClusterIP-only
- add readiness and liveness probes
- add network policies if your cluster supports them

## Scale Guidance

### Usually enough

- `admin_interface`: 1 replica
- `api_gateway`: 1-2 replicas
- `sync_service`: 1-2 replicas
- `keep_extractor`: 1-2 replicas
- `notion_writer`: 1-2 replicas

### Watch before scaling

- Notion API rate limits
- Google Keep extraction latency
- Supabase Storage upload throughput
- sync job queue depth

## Backups

Back up:

- PostgreSQL database
- deployment manifests / env definitions
- `ENCRYPTION_KEY` in your secret system

Without the correct `ENCRYPTION_KEY`, stored credentials cannot be decrypted.

## Smoke Tests

After deployment:

```bash
curl https://YOUR_DOMAIN/api/v1/health
curl https://YOUR_ADMIN_DOMAIN/
```

Then:

1. log into admin UI
2. confirm credentials page loads
3. trigger incremental sync
4. verify job detail updates
5. confirm text and images appear in Notion

## Rollback

Rollback steps should include:

1. switch traffic to previous image set
2. keep database untouched unless schema changed
3. verify health endpoints
4. trigger small sync validation run

## Production Rules

- do not use placeholder Supabase values
- keep Supabase bucket public only if required for Notion image URLs
- prefer a dedicated Notion root page for auto-created databases
- do not rotate `ENCRYPTION_KEY` casually
