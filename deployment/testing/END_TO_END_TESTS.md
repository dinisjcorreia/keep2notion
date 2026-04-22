# End-to-End Deployment Tests

Use these tests after staging or production rollout.

## What to Validate

- health endpoints
- admin UI reachable
- sync start works
- sync job progress updates
- Supabase image upload works
- Notion page creation/update works
- routing by label works

## Test Inputs

Prepare:

- Google test account with sample notes
- notes with labels like `work` and `ideas`
- at least one note without labels
- at least one note with image attachments
- Notion test root page connected to integration

## Environment

Example:

```env
API_BASE_URL=https://api.example.com
ADMIN_BASE_URL=https://admin.example.com

TEST_USER_ID=test-user@example.com
TEST_MAIN_DATABASE_NAME=Keep

SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_STORAGE_BUCKET=keep-images
```

## Smoke Test Sequence

1. verify health endpoints
2. log into admin UI
3. add or confirm credentials
4. trigger incremental sync
5. open job detail page
6. verify counters move during run
7. inspect Notion output

## Assertions

Expected outcomes:

- labeled note goes to first label database
- unlabeled note goes to fallback database
- missing target database gets auto-created
- images render in Notion
- images appear above text
- completed job shows processed/synced/error counts

## Example Manual Checks

```bash
curl https://YOUR_API_DOMAIN/api/v1/health
curl https://YOUR_ADMIN_DOMAIN/
```

Then confirm in UI:

- sync job list updates
- sync job detail logs stream by refresh
- Notion content matches Keep note content
