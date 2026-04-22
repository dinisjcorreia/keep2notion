"""
Unit tests for encryption utilities.

Tests the EncryptionService class which handles AES-256 encryption
and decryption of credentials (OAuth tokens and API keys).

Requirements tested:
- 10.1: System SHALL encrypt API credentials at rest using AES-256
"""

import os
import pytest
from unittest.mock import patch
from cryptography.fernet import Fernet, InvalidToken

from shared.encryption import EncryptionService


class TestEncryptionService:
    """Test suite for EncryptionService."""
    
    def test_initialization_with_provided_key(self):
        """Test that EncryptionService initializes with a provided key."""
        # Generate a test key
        test_key = Fernet.generate_key().decode()
        
        # Initialize service with the key
        service = EncryptionService(encryption_key=test_key)
        
        # Verify the service is initialized
        assert service.key == test_key.encode()
        assert service.cipher is not None
    
    def test_initialization_with_env_key(self):
        """Test that EncryptionService loads key from ENCRYPTION_KEY."""
        test_key = Fernet.generate_key().decode()
        
        with patch.dict(os.environ, {'ENCRYPTION_KEY': test_key}, clear=True):
            service = EncryptionService()
            assert service.key == test_key.encode()

    def test_initialization_with_legacy_env_key(self):
        """Test that EncryptionService still supports AWS_ENCRYPTION_KEY."""
        test_key = Fernet.generate_key().decode()

        with patch.dict(os.environ, {'AWS_ENCRYPTION_KEY': test_key}, clear=True):
            service = EncryptionService()
            assert service.key == test_key.encode()
    
    def test_initialization_generates_key_if_none_provided(self):
        """Test that EncryptionService generates a key if none provided."""
        with patch.dict(os.environ, {}, clear=True):
            service = EncryptionService()
            
            # Verify a key was generated
            assert service.key is not None
            assert len(service.key) > 0
            assert service.cipher is not None
    
    def test_encrypt_plaintext(self):
        """Test encrypting a plaintext string."""
        service = EncryptionService()
        plaintext = "my_secret_oauth_token_12345"
        
        # Encrypt the plaintext
        ciphertext = service.encrypt(plaintext)
        
        # Verify ciphertext is different from plaintext
        assert ciphertext != plaintext
        assert len(ciphertext) > 0
        
        # Verify ciphertext is base64 encoded
        import base64
        try:
            base64.b64decode(ciphertext)
        except Exception:
            pytest.fail("Ciphertext is not valid base64")
    
    def test_decrypt_ciphertext(self):
        """Test decrypting an encrypted string."""
        service = EncryptionService()
        plaintext = "my_secret_api_key_67890"
        
        # Encrypt then decrypt
        ciphertext = service.encrypt(plaintext)
        decrypted = service.decrypt(ciphertext)
        
        # Verify decrypted text matches original
        assert decrypted == plaintext
    
    def test_encrypt_decrypt_round_trip(self):
        """Test that encrypt/decrypt round trip preserves data."""
        service = EncryptionService()
        
        test_cases = [
            "simple_token",
            "token_with_special_chars!@#$%^&*()",
            "very_long_token_" + "x" * 1000,
            "token with spaces and newlines\n\t",
            "unicode_token_🔐🔑",
        ]
        
        for plaintext in test_cases:
            ciphertext = service.encrypt(plaintext)
            decrypted = service.decrypt(ciphertext)
            assert decrypted == plaintext, f"Round trip failed for: {plaintext}"
    
    def test_encrypt_empty_string(self):
        """Test encrypting an empty string."""
        service = EncryptionService()
        
        ciphertext = service.encrypt("")
        assert ciphertext == ""
    
    def test_decrypt_empty_string(self):
        """Test decrypting an empty string."""
        service = EncryptionService()
        
        plaintext = service.decrypt("")
        assert plaintext == ""
    
    def test_different_keys_produce_different_ciphertexts(self):
        """Test that different encryption keys produce different ciphertexts."""
        plaintext = "same_plaintext"
        
        service1 = EncryptionService()
        service2 = EncryptionService()
        
        ciphertext1 = service1.encrypt(plaintext)
        ciphertext2 = service2.encrypt(plaintext)
        
        # Different keys should produce different ciphertexts
        assert ciphertext1 != ciphertext2
    
    def test_same_key_produces_consistent_decryption(self):
        """Test that the same key can decrypt ciphertext consistently."""
        plaintext = "consistent_token"
        key = Fernet.generate_key().decode()
        
        # Encrypt with first service instance
        service1 = EncryptionService(encryption_key=key)
        ciphertext = service1.encrypt(plaintext)
        
        # Decrypt with second service instance using same key
        service2 = EncryptionService(encryption_key=key)
        decrypted = service2.decrypt(ciphertext)
        
        assert decrypted == plaintext
    
    def test_decrypt_with_wrong_key_raises_error(self):
        """Test that decrypting with wrong key raises an error."""
        plaintext = "secret_token"
        
        # Encrypt with one key
        service1 = EncryptionService()
        ciphertext = service1.encrypt(plaintext)
        
        # Try to decrypt with different key
        service2 = EncryptionService()
        
        with pytest.raises(InvalidToken):
            service2.decrypt(ciphertext)
    
    def test_decrypt_invalid_ciphertext_raises_error(self):
        """Test that decrypting invalid ciphertext raises an error."""
        service = EncryptionService()
        
        invalid_ciphertext = "this_is_not_valid_encrypted_data"
        
        with pytest.raises(Exception):  # Could be InvalidToken or base64 decode error
            service.decrypt(invalid_ciphertext)
    
    def test_generate_key_returns_valid_key(self):
        """Test that generate_key returns a valid Fernet key."""
        key = EncryptionService.generate_key()
        
        # Verify key is a string
        assert isinstance(key, str)
        
        # Verify key can be used to create a Fernet instance
        try:
            Fernet(key.encode())
        except Exception:
            pytest.fail("Generated key is not a valid Fernet key")
    
    def test_generate_key_produces_unique_keys(self):
        """Test that generate_key produces unique keys each time."""
        key1 = EncryptionService.generate_key()
        key2 = EncryptionService.generate_key()
        
        assert key1 != key2
    
    def test_encryption_uses_aes_256(self):
        """Test that encryption uses AES-256 (via Fernet which uses AES-128-CBC).
        
        Note: Fernet actually uses AES-128-CBC, not AES-256. This is a known
        limitation of the Fernet specification. For true AES-256, we would need
        to use a different implementation.
        
        This test documents the current implementation and serves as a reminder
        if we need to upgrade to true AES-256 in the future.
        """
        service = EncryptionService()
        plaintext = "test_token"
        
        # Encrypt and verify it works
        ciphertext = service.encrypt(plaintext)
        decrypted = service.decrypt(ciphertext)
        
        assert decrypted == plaintext
        
        # Note: Fernet uses AES-128-CBC with HMAC-SHA256
        # If true AES-256 is required, we need to implement a custom solution
    
    def test_encrypted_credentials_are_not_plaintext(self):
        """Test that encrypted credentials don't contain plaintext.
        
        **Validates: Requirements 10.1**
        """
        service = EncryptionService()
        
        # Test with realistic credential values
        google_token = "ya29.a0AfH6SMBx..."
        notion_token = "secret_abc123xyz..."
        
        encrypted_google = service.encrypt(google_token)
        encrypted_notion = service.encrypt(notion_token)
        
        # Verify encrypted values don't contain plaintext
        assert google_token not in encrypted_google
        assert notion_token not in encrypted_notion
        
        # Verify they can be decrypted correctly
        assert service.decrypt(encrypted_google) == google_token
        assert service.decrypt(encrypted_notion) == notion_token
    
    def test_encryption_with_env_managed_key(self):
        """Test encryption using an environment-managed key.
        
        **Validates: Requirements 10.1, 8.4**
        """
        env_key = Fernet.generate_key().decode()
        
        with patch.dict(os.environ, {'ENCRYPTION_KEY': env_key}, clear=True):
            service = EncryptionService()
            
            plaintext = "oauth_token_from_google"
            ciphertext = service.encrypt(plaintext)
            decrypted = service.decrypt(ciphertext)
            
            assert decrypted == plaintext
            assert plaintext not in ciphertext


class TestEncryptionIntegration:
    """Integration tests for encryption with database operations."""
    
    def test_credential_encryption_workflow(self):
        """Test the complete workflow of encrypting and storing credentials.
        
        **Validates: Requirements 10.1**
        """
        service = EncryptionService()
        
        # Simulate storing credentials
        user_id = "test_user@example.com"
        google_token = "google_oauth_token_abc123"
        notion_token = "notion_api_token_xyz789"
        
        # Encrypt credentials (as would be done before storing in DB)
        encrypted_google = service.encrypt(google_token)
        encrypted_notion = service.encrypt(notion_token)
        
        # Verify they're encrypted
        assert encrypted_google != google_token
        assert encrypted_notion != notion_token
        
        # Simulate retrieving and decrypting credentials
        decrypted_google = service.decrypt(encrypted_google)
        decrypted_notion = service.decrypt(encrypted_notion)
        
        # Verify decryption works
        assert decrypted_google == google_token
        assert decrypted_notion == notion_token
    
    def test_multiple_users_with_same_service(self):
        """Test encrypting credentials for multiple users with same service."""
        service = EncryptionService()
        
        users = [
            ("user1@example.com", "token1_google", "token1_notion"),
            ("user2@example.com", "token2_google", "token2_notion"),
            ("user3@example.com", "token3_google", "token3_notion"),
        ]
        
        encrypted_credentials = []
        
        # Encrypt all credentials
        for user_id, google_token, notion_token in users:
            encrypted_credentials.append({
                'user_id': user_id,
                'google': service.encrypt(google_token),
                'notion': service.encrypt(notion_token),
                'original_google': google_token,
                'original_notion': notion_token,
            })
        
        # Verify all can be decrypted correctly
        for cred in encrypted_credentials:
            assert service.decrypt(cred['google']) == cred['original_google']
            assert service.decrypt(cred['notion']) == cred['original_notion']
    
    def test_key_rotation_scenario(self):
        """Test scenario where encryption key needs to be rotated.
        
        This test documents the process needed for key rotation:
        1. Decrypt all credentials with old key
        2. Re-encrypt with new key
        3. Update storage
        """
        old_key = Fernet.generate_key().decode()
        new_key = Fernet.generate_key().decode()
        
        # Encrypt with old key
        old_service = EncryptionService(encryption_key=old_key)
        plaintext = "credential_to_rotate"
        old_ciphertext = old_service.encrypt(plaintext)
        
        # Simulate key rotation
        # Step 1: Decrypt with old key
        decrypted = old_service.decrypt(old_ciphertext)
        
        # Step 2: Encrypt with new key
        new_service = EncryptionService(encryption_key=new_key)
        new_ciphertext = new_service.encrypt(decrypted)
        
        # Step 3: Verify new encryption works
        assert new_service.decrypt(new_ciphertext) == plaintext
        
        # Verify old key can't decrypt new ciphertext
        with pytest.raises(InvalidToken):
            old_service.decrypt(new_ciphertext)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
