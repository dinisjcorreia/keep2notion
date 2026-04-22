"""Encryption utilities for credential management."""

import base64
import os
from typing import Optional
from cryptography.fernet import Fernet


class EncryptionService:
    """Handles AES-256 encryption and decryption of credentials."""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption service.
        
        Args:
            encryption_key: Base64-encoded encryption key. If not provided,
                          will attempt to load from ENCRYPTION_KEY env var,
                          then legacy AWS_ENCRYPTION_KEY env var,
                          or generate a new key (not recommended for production)
        """
        if encryption_key:
            self.key = encryption_key.encode()
        else:
            env_key = os.getenv('ENCRYPTION_KEY') or os.getenv('AWS_ENCRYPTION_KEY')
            if env_key:
                self.key = env_key.encode()
            else:
                # Generate a key (only for development/testing)
                self.key = Fernet.generate_key()
        
        self.cipher = Fernet(self.key)
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string using AES-256.
        
        Args:
            plaintext: The string to encrypt
            
        Returns:
            Base64-encoded encrypted string
        """
        if not plaintext:
            return ""
        
        encrypted_bytes = self.cipher.encrypt(plaintext.encode())
        return base64.b64encode(encrypted_bytes).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt an encrypted string.
        
        Args:
            ciphertext: Base64-encoded encrypted string
            
        Returns:
            Decrypted plaintext string
        """
        if not ciphertext:
            return ""
        
        encrypted_bytes = base64.b64decode(ciphertext.encode())
        decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
        return decrypted_bytes.decode()
    
    @staticmethod
    def generate_key() -> str:
        """
        Generate a new encryption key.
        
        Returns:
            Base64-encoded encryption key
        """
        return Fernet.generate_key().decode()
