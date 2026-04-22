# Image Cleanup Notes

Keep2Notion stores note images in Supabase Storage and references them from Notion using public URLs.

## Why Cleanup Matters

Without cleanup, object storage can accumulate:

- outdated note images
- test images from staging
- orphaned uploads from failed experiments

## Current Behavior

App does not implement automatic object cleanup as part of the sync workflow.

That means:

- successful sync does not automatically delete old objects
- failed sync can leave uploaded objects behind
- cleanup policy should be handled operationally

## Recommended Approach

Use one or more of:

- bucket retention policy
- periodic manual cleanup
- prefix-based lifecycle strategy
- separate staging and production buckets

## Practical Rules

- dedicate a bucket to Keep2Notion images
- do not reuse same bucket for unrelated assets
- use separate bucket or prefix for staging
- periodically review unused objects

## Safety Warning

Do not delete objects aggressively if existing Notion pages still reference those URLs.

If you remove an object still referenced by Notion, image blocks will break.
