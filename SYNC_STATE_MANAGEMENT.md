# Sync State Management

## Problem

When you delete Notion pages manually, the sync_state database still contains records pointing to those deleted page IDs. On the next sync, the system tries to **update** those non-existent pages instead of creating new ones, resulting in errors:

### Error Sequence:
1. **First sync after deletion**: `Can't edit block that is archived` (pages in trash)
2. **After emptying trash**: `Could not find page with ID: xxx` (pages permanently deleted)

## Root Cause

The sync system maintains a `sync_state` table that maps:
- `keep_note_id` → `notion_page_id`

This mapping tells the system whether to:
- **CREATE** a new Notion page (no mapping exists)
- **UPDATE** an existing Notion page (mapping exists)

When you delete Notion pages but the sync_state records remain, the system incorrectly tries to update deleted pages.

## Solution

Added a "Clear Sync State" feature in the admin dashboard that removes sync_state records for a user. This forces the next sync to create fresh Notion pages.

### How to Use:

1. Go to **Credential Configuration** page in admin dashboard
2. Find your user in the "Existing Credentials" table
3. Click the **"Clear State"** button next to your user
4. Confirm the action
5. Run a new sync - it will create new Notion pages

### When to Use:

- **Testing**: When you want to re-sync notes without duplicates
- **After manual deletion**: When you've deleted Notion pages manually
- **Fresh start**: When you want to reset the sync relationship

### What It Does:

```sql
DELETE FROM sync_state WHERE user_id = 'your@email.com';
```

This removes all sync state records for the user, so the next sync will:
- ✓ Create new Notion pages for all Keep notes
- ✓ Upload images to Supabase Storage (if configured correctly)
- ✓ Establish new sync_state mappings

## Production Considerations

**DO NOT use "Clear Sync State" in production** unless you intentionally want to:
- Create duplicate Notion pages
- Re-establish sync relationships after manual deletions

In production, the sync_state should remain intact to enable proper incremental syncing.

## Technical Details

### Files Modified:

1. **`shared/db_operations.py`**
   - Added `delete_sync_state()` method

2. **`services/admin_interface/sync_admin/views.py`**
   - Added `clear_sync_state()` view

3. **`services/admin_interface/admin_project/urls.py`**
   - Added route: `/config/credentials/<user_id>/clear-sync-state/`

4. **`services/admin_interface/templates/credential_config.html`**
   - Added "Clear State" button in credentials table

### Database Schema:

```sql
CREATE TABLE sync_state (
    user_id VARCHAR NOT NULL,
    keep_note_id VARCHAR NOT NULL,
    notion_page_id VARCHAR NOT NULL,
    keep_modified_at TIMESTAMP NOT NULL,
    last_synced_at TIMESTAMP NOT NULL,
    PRIMARY KEY (user_id, keep_note_id)
);
```

## Alternative Approaches Considered

1. **Auto-detect deleted pages**: Check if Notion page exists before updating
   - ❌ Adds API calls and latency to every sync
   - ❌ Notion API rate limits would be hit faster

2. **Soft delete in sync_state**: Mark records as "deleted" instead of removing
   - ❌ More complex logic
   - ❌ Doesn't solve the immediate problem

3. **Manual database cleanup**: Run SQL directly
   - ❌ Requires database access
   - ❌ Not user-friendly for testing

4. **Clear sync state button** (chosen solution)
   - ✓ Simple and explicit
   - ✓ User-friendly
   - ✓ Safe for testing
   - ✓ Clear intent
