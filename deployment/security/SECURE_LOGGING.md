# Secure Logging

Keep logs useful, but never leak credentials or private note content unnecessarily.

## Never Log

- Google Keep master token
- Notion API token
- `SUPABASE_SERVICE_ROLE_KEY`
- `ENCRYPTION_KEY`
- raw passwords
- full credential payloads

## Log Safely

Good examples:

- job id
- user id
- keep note id
- target database name
- success/failure counts
- high-level API failure messages

Avoid:

- dumping request bodies with secrets
- logging full env vars
- logging decrypted credentials

## Redaction Targets

Redact any line that may contain:

- `secret_`
- `SUPABASE_SERVICE_ROLE_KEY`
- `ENCRYPTION_KEY`
- long bearer tokens

## Operational Advice

- centralize service logs
- set retention limits
- separate app logs from audit logs
- protect access to logs

## App-Specific Risks

Sensitive data may appear during:

- credential save flows
- authentication failures
- traceback dumps
- debug logging of outbound requests

Use lower verbosity in production unless actively investigating an issue.
