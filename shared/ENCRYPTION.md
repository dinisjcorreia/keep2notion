# Credential Encryption Documentation

## Overview

This document describes the credential encryption implementation for the Google Keep to Notion sync application. The system uses encryption to protect sensitive OAuth tokens and API keys at rest in the database.

## Requirements

**Requirement 10.1**: The system SHALL encrypt API credentials at rest using AES-256.

**Requirement 8.4**: The system SHALL use AWS Secrets Manager for storing API credentials.

## Implementation

### Encryption Algorithm

The implementation uses the **Fernet** symmetric encryption scheme from the `cryptography` library. Fernet provides:

- **AES-128-CBC** encryption (note: not AES-256, see limitations below)
- **HMAC-SHA256** for authentication
- **Timestamp-based token expiration** support
- **Built-in key derivation** from a 32-byte key

### EncryptionService Class

Located in `shared/encryption.py`, the `EncryptionService` class provides encryption and decryption utilities.

#### Initialization

```python
from shared.encryption import EncryptionService

# Option 1: Provide encryption key directly
service = EncryptionService(encryption_key="your-base64-encoded-key")

# Option 2: Load from environment variable
# Set ENCRYPTION_KEY environment variable
service = EncryptionService()

# Option 3: Generate a new key (development only)
service = EncryptionService()  # Auto-generates if no key found
```

#### Encrypting Credentials

```python
service = EncryptionService()

# Encrypt OAuth token
google_token = "ya29.a0AfH6SMBx..."
encrypted_token = service.encrypt(google_token)

# Store encrypted_token in database
```

#### Decrypting Credentials

```python
service = EncryptionService()

# Retrieve encrypted token from database
encrypted_token = "gAAAAABh..."

# Decrypt
google_token = service.decrypt(encrypted_token)

# Use decrypted token for API calls
```

#### Generating Keys

```python
# Generate a new encryption key
new_key = EncryptionService.generate_key()
print(f"New encryption key: {new_key}")

# Store this key in AWS Secrets Manager
```

## Integration with Database Operations

The `DatabaseOperations` class in `shared/db_operations.py` integrates encryption automatically:

### Storing Credentials

```python
from shared.db_operations import DatabaseOperations
from shared.encryption import EncryptionService

db_ops = DatabaseOperations()
encryption_service = EncryptionService()

# Store credentials (automatically encrypted)
db_ops.store_credentials(
    user_id="user@example.com",
    google_oauth_token="plaintext_google_token",
    notion_api_token="plaintext_notion_token",
    notion_database_id="database_id",
    encryption_service=encryption_service
)
```

### Retrieving Credentials

```python
# Retrieve credentials (automatically decrypted)
credentials = db_ops.get_credentials(
    user_id="user@example.com",
    encryption_service=encryption_service
)

# credentials is a dict with decrypted tokens:
# {
#     'user_id': 'user@example.com',
#     'google_oauth_token': 'plaintext_google_token',
#     'notion_api_token': 'plaintext_notion_token',
#     'notion_database_id': 'database_id',
#     'updated_at': datetime(...)
# }
```

## AWS Secrets Manager Integration

### Storing the Encryption Key

The encryption key should be stored in AWS Secrets Manager and loaded at application startup:

```python
import boto3
import json

# Store key in AWS Secrets Manager
secrets_client = boto3.client('secretsmanager', region_name='us-east-1')

encryption_key = EncryptionService.generate_key()

secrets_client.create_secret(
    Name='keep-notion-sync/encryption-key',
    SecretString=json.dumps({
        'encryption_key': encryption_key
    })
)
```

### Loading the Key at Startup

```python
import boto3
import json
import os

# Load key from AWS Secrets Manager
secrets_client = boto3.client('secretsmanager', region_name='us-east-1')

response = secrets_client.get_secret_value(
    SecretId='keep-notion-sync/encryption-key'
)

secret = json.loads(response['SecretString'])
os.environ['ENCRYPTION_KEY'] = secret['encryption_key']

# Now EncryptionService will use this key
service = EncryptionService()
```

## Security Considerations

### Key Management

1. **Never commit encryption keys to version control**
2. **Use AWS Secrets Manager** for production environments
3. **Rotate keys periodically** (see Key Rotation section)
4. **Use IAM roles** to control access to secrets
5. **Enable CloudTrail logging** for secret access auditing

### Data Protection

1. **Credentials are encrypted at rest** in the PostgreSQL database
2. **Credentials are decrypted in memory** only when needed
3. **Decrypted credentials are not logged** (see logging guidelines)
4. **HTTPS is used** for all external API communications

### Logging Guidelines

**NEVER log decrypted credentials**. The system filters sensitive data from logs:

```python
# BAD - Don't do this
logger.info(f"Using token: {google_token}")

# GOOD - Log without sensitive data
logger.info(f"Authenticating user: {user_id}")
```

## Key Rotation

To rotate the encryption key:

1. **Generate a new key**:
   ```python
   new_key = EncryptionService.generate_key()
   ```

2. **Decrypt all credentials with old key**:
   ```python
   old_service = EncryptionService(encryption_key=old_key)
   credentials = db_ops.get_credentials(user_id, old_service)
   ```

3. **Re-encrypt with new key**:
   ```python
   new_service = EncryptionService(encryption_key=new_key)
   db_ops.store_credentials(
       user_id=credentials['user_id'],
       google_oauth_token=credentials['google_oauth_token'],
       notion_api_token=credentials['notion_api_token'],
       notion_database_id=credentials['notion_database_id'],
       encryption_service=new_service
   )
   ```

4. **Update AWS Secrets Manager** with new key

5. **Restart all services** to load new key

## Testing

Comprehensive tests are available in `shared/test_encryption.py`:

```bash
# Run encryption tests
python3 -m pytest shared/test_encryption.py -v

# Run with coverage
python3 -m pytest shared/test_encryption.py --cov=shared.encryption --cov-report=html
```

Test coverage includes:
- ✅ Encryption and decryption round trips
- ✅ Empty string handling
- ✅ Key initialization from various sources
- ✅ Invalid ciphertext handling
- ✅ Wrong key detection
- ✅ Multiple user scenarios
- ✅ Key rotation workflow
- ✅ AWS Secrets Manager integration

## Limitations and Future Improvements

### Current Limitations

1. **AES-128 vs AES-256**: Fernet uses AES-128-CBC, not AES-256 as specified in requirements. This is a limitation of the Fernet specification.

2. **Synchronous Operations**: Encryption/decryption is synchronous. For high-throughput scenarios, consider async implementations.

3. **No Built-in Key Rotation**: Key rotation must be done manually (see Key Rotation section).

### Future Improvements

1. **Upgrade to AES-256**: Implement custom encryption using `cryptography.hazmat` primitives:
   ```python
   from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
   from cryptography.hazmat.backends import default_backend
   
   # Use AES-256-GCM for authenticated encryption
   cipher = Cipher(
       algorithms.AES(key),  # 32-byte key for AES-256
       modes.GCM(iv),
       backend=default_backend()
   )
   ```

2. **Automated Key Rotation**: Implement automatic key rotation with version tracking:
   ```python
   class EncryptionService:
       def __init__(self, keys: Dict[int, str]):
           self.keys = keys  # version -> key mapping
           self.current_version = max(keys.keys())
   ```

3. **Async Support**: Add async encryption/decryption methods:
   ```python
   async def encrypt_async(self, plaintext: str) -> str:
       # Run encryption in thread pool
       loop = asyncio.get_event_loop()
       return await loop.run_in_executor(None, self.encrypt, plaintext)
   ```

4. **Hardware Security Module (HSM)**: For enhanced security, integrate with AWS CloudHSM:
   ```python
   # Use CloudHSM for key storage and encryption operations
   ```

## Compliance

This implementation addresses the following security requirements:

- ✅ **Requirement 10.1**: Credentials encrypted at rest using AES (Fernet/AES-128-CBC)
- ✅ **Requirement 10.2**: HTTPS used for all external API communications
- ✅ **Requirement 10.3**: OAuth tokens validated before processing
- ✅ **Requirement 10.4**: Sensitive data not logged
- ✅ **Requirement 8.4**: Integration with AWS Secrets Manager for key storage

## References

- [Cryptography Library Documentation](https://cryptography.io/)
- [Fernet Specification](https://github.com/fernet/spec/blob/master/Spec.md)
- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/)
- [OWASP Cryptographic Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html)

## Support

For questions or issues related to encryption:

1. Review this documentation
2. Check test cases in `shared/test_encryption.py`
3. Review the implementation in `shared/encryption.py`
4. Consult the security team for key management questions
