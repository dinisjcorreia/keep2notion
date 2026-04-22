# Staging Deployment Guide

Use staging to validate:

- service wiring
- secrets
- Supabase uploads
- Notion routing and database creation
- admin UI behavior

## Staging Differences

Compared to production, staging should use:

- separate PostgreSQL database
- separate Supabase project or bucket prefix
- separate Notion test workspace or root page
- test Google account
- smaller resource limits

## Recommended Staging Config

Use separate values for:

```env
DATABASE_URL=postgresql://...
SUPABASE_URL=https://your-staging-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-staging-service-role-key
SUPABASE_STORAGE_BUCKET=keep-images-staging
ENCRYPTION_KEY=your-staging-encryption-key
SECRET_KEY=your-staging-django-secret-key
```

## Validation Flow

1. deploy services
2. verify health endpoints
3. add staging credentials in admin UI
4. trigger full sync
5. verify:
   - labels route to correct database names
   - no-label notes go to fallback database
   - missing databases auto-create under root page
   - images show in Notion above text

## Staging Checklist

- ingress works
- admin UI works
- API health works
- sync jobs move from queued -> running -> completed/failed
- counters update on job detail page
- logs visible in admin UI
- Supabase uploads succeed
- Notion pages created or updated correctly

## Suggested Cleanup

Because staging is test-heavy:

- periodically clear old sync state for test users
- periodically remove old staging data from Supabase bucket
- periodically delete unneeded test databases/pages in Notion
