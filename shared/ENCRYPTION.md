# Credential Encryption Documentation

## Overview

Keep2Notion encrypts stored credentials before writing them to PostgreSQL.

Encrypted values include:

- Google Keep master token
- Notion API token

## Current Runtime Behavior

The app uses `EncryptionService` from `shared/encryption.py`.

Current expected source of encryption key:

- `ENCRYPTION_KEY` environment variable

If the key changes, previously stored credentials cannot be decrypted unless they are re-encrypted with the new key.

## Current Assumption

Current app/runtime expects:

- `ENCRYPTION_KEY`

How that value reaches the app is a deployment choice.

## Encryption Primitive

Implementation uses Fernet from the `cryptography` package.

That gives:

- symmetric authenticated encryption
- signed ciphertext
- simple key handling for app secrets

## Basic Usage

```python
from shared.encryption import EncryptionService

service = EncryptionService()

encrypted = service.encrypt("secret_value")
decrypted = service.decrypt(encrypted)
```

## Database Integration

`DatabaseOperations` handles encryption/decryption for credentials automatically.

### Store credentials

```python
from shared.db_operations import DatabaseOperations
from shared.encryption import EncryptionService

db_ops = DatabaseOperations()
encryption = EncryptionService()

db_ops.store_credentials(
    user_id="user@example.com",
    google_oauth_token="google-keep-master-token",
    notion_api_token="secret_...",
    notion_database_id="https://www.notion.so/Root-Page-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    encryption_service=encryption,
)
```

### Read credentials

```python
credentials = db_ops.get_credentials(
    user_id="user@example.com",
    encryption_service=encryption,
)
```

Returned values are decrypted in memory only when needed.

## Generate a Key

```python
from shared.encryption import EncryptionService

print(EncryptionService.generate_key())
```

Or from shell:

```bash
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

## Security Notes

- never commit `ENCRYPTION_KEY`
- never log decrypted tokens
- use different keys per environment
- keep backup of production key before rotation

## Key Rotation

High-level process:

1. load old key
2. decrypt stored credentials
3. re-encrypt with new key
4. update `ENCRYPTION_KEY`
5. restart services

## Testing

```bash
pytest shared/test_encryption.py -v
```

## Public Repo Note

Current application logic only requires `ENCRYPTION_KEY`.
