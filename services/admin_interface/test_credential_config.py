"""
Unit tests for credential configuration view.

Tests the credential management functionality including:
- Viewing the credential configuration page
- Creating new credentials with encryption
- Updating existing credentials
- Deleting credentials
- Form validation
"""

import os
import sys
import django
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from unittest.mock import patch, MagicMock

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'admin_project.settings')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
django.setup()

from sync_admin.models import Credential


@override_settings(ALLOWED_HOSTS=['*'])
class CredentialConfigViewTests(TestCase):
    """Test cases for credential configuration view."""
    
    def setUp(self):
        """Set up test client and test data."""
        self.client = Client()
        self.url = reverse('credential_config')
        
        # Create test credentials
        self.test_user_id = 'test_user@example.com'
        self.test_google_token = 'test_google_oauth_token_12345'
        self.test_notion_token = 'secret_test_notion_token_67890'
        self.test_database_id = 'abc123def456ghi789jkl012'
    
    def tearDown(self):
        """Clean up after tests."""
        Credential.objects.all().delete()
    
    def test_view_credential_config_page(self):
        """Test that the credential configuration page loads successfully."""
        response = self.client.get(self.url)
        
        # Debug: print response details if not 200
        if response.status_code != 200:
            print(f"Status code: {response.status_code}")
            print(f"Content: {response.content.decode()[:500]}")
        
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'credential_config.html')
        self.assertContains(response, 'Credential Configuration')
        self.assertContains(response, 'Add New Credentials')
    
    def test_view_shows_existing_credentials(self):
        """Test that existing credentials are displayed in the list."""
        # Create test credential
        Credential.objects.create(
            user_id=self.test_user_id,
            google_oauth_token='encrypted_token_1',
            notion_api_token='encrypted_token_2',
            notion_database_id=self.test_database_id
        )
        
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.test_user_id)
        self.assertContains(response, self.test_database_id)
    
    def test_create_new_credential(self):
        """Test creating a new credential with encryption."""
        # Submit form to create credential
        response = self.client.post(self.url, {
            'action': 'save',
            'user_id': self.test_user_id,
            'google_oauth_token': self.test_google_token,
            'notion_api_token': self.test_notion_token,
            'notion_database_id': self.test_database_id,
        })
        
        # Should redirect after successful creation
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.url)
        
        # Verify credential was created
        credential = Credential.objects.get(user_id=self.test_user_id)
        self.assertEqual(credential.user_id, self.test_user_id)
        self.assertEqual(credential.notion_database_id, self.test_database_id)
        
        # Verify tokens are encrypted (not equal to plaintext)
        self.assertNotEqual(credential.google_oauth_token, self.test_google_token)
        self.assertNotEqual(credential.notion_api_token, self.test_notion_token)
    
    def test_update_existing_credential(self):
        """Test updating an existing credential."""
        # Create initial credential
        Credential.objects.create(
            user_id=self.test_user_id,
            google_oauth_token='old_google_token',
            notion_api_token='old_notion_token',
            notion_database_id='old_database_id'
        )
        
        # Update credential
        new_google_token = 'new_google_token'
        new_notion_token = 'new_notion_token'
        new_database_id = 'new_database_id_123'
        
        response = self.client.post(self.url, {
            'action': 'save',
            'user_id': self.test_user_id,
            'google_oauth_token': new_google_token,
            'notion_api_token': new_notion_token,
            'notion_database_id': new_database_id,
        })
        
        # Should redirect after successful update
        self.assertEqual(response.status_code, 302)
        
        # Verify credential was updated
        credential = Credential.objects.get(user_id=self.test_user_id)
        self.assertEqual(credential.notion_database_id, new_database_id)
        # Tokens should be encrypted (not equal to plaintext)
        self.assertNotEqual(credential.google_oauth_token, new_google_token)
        self.assertNotEqual(credential.notion_api_token, new_notion_token)
        
        # Verify only one credential exists
        self.assertEqual(Credential.objects.count(), 1)

    def test_update_existing_credential_preserves_masked_tokens(self):
        """Test editing database/root reference without re-entering tokens."""
        user_id = 'masked-token-user@example.com'
        Credential.objects.filter(user_id=user_id).delete()
        Credential.objects.create(
            user_id=user_id,
            google_oauth_token='existing_google_encrypted',
            notion_api_token='existing_notion_encrypted',
            notion_database_id='old_database_id'
        )

        new_database_id = 'https://www.notion.so/Notas-34a39cb1c2ac80fb81efd00697b44032'

        response = self.client.post(self.url, {
            'action': 'save',
            'user_id': user_id,
            'google_oauth_token': '********',
            'notion_api_token': '********',
            'notion_database_id': new_database_id,
        })

        self.assertEqual(response.status_code, 302)

        credential = Credential.objects.get(user_id=user_id)
        self.assertEqual(credential.notion_database_id, new_database_id)
        self.assertEqual(credential.google_oauth_token, 'existing_google_encrypted')
        self.assertEqual(credential.notion_api_token, 'existing_notion_encrypted')
    
    def test_delete_credential(self):
        """Test deleting a credential."""
        # Create credential
        Credential.objects.create(
            user_id=self.test_user_id,
            google_oauth_token='encrypted_token_1',
            notion_api_token='encrypted_token_2',
            notion_database_id=self.test_database_id
        )
        
        # Delete credential
        response = self.client.post(self.url, {
            'action': 'delete',
            'user_id': self.test_user_id,
        })
        
        # Should redirect after successful deletion
        self.assertEqual(response.status_code, 302)
        
        # Verify credential was deleted
        self.assertEqual(Credential.objects.filter(user_id=self.test_user_id).count(), 0)
    
    def test_validation_user_id_required(self):
        """Test that user_id is required."""
        response = self.client.post(self.url, {
            'action': 'save',
            'user_id': '',
            'google_oauth_token': self.test_google_token,
            'notion_api_token': self.test_notion_token,
            'notion_database_id': self.test_database_id,
        })
        
        # Should not redirect (stays on same page with error)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'User ID is required')
        
        # Verify no credential was created
        self.assertEqual(Credential.objects.count(), 0)
    
    def test_validation_google_token_required(self):
        """Test that Google OAuth token is required."""
        response = self.client.post(self.url, {
            'action': 'save',
            'user_id': self.test_user_id,
            'google_oauth_token': '',
            'notion_api_token': self.test_notion_token,
            'notion_database_id': self.test_database_id,
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Google OAuth token is required')
        self.assertEqual(Credential.objects.count(), 0)
    
    def test_validation_notion_token_required(self):
        """Test that Notion API token is required."""
        response = self.client.post(self.url, {
            'action': 'save',
            'user_id': self.test_user_id,
            'google_oauth_token': self.test_google_token,
            'notion_api_token': '',
            'notion_database_id': self.test_database_id,
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Notion API token is required')
        self.assertEqual(Credential.objects.count(), 0)
    
    def test_validation_database_id_required(self):
        """Test that Notion database ID is required."""
        response = self.client.post(self.url, {
            'action': 'save',
            'user_id': self.test_user_id,
            'google_oauth_token': self.test_google_token,
            'notion_api_token': self.test_notion_token,
            'notion_database_id': '',
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Notion database ID is required')
        self.assertEqual(Credential.objects.count(), 0)
    
    def test_edit_credential_loads_form(self):
        """Test that selecting a credential for editing loads the form."""
        # Create credential
        Credential.objects.create(
            user_id=self.test_user_id,
            google_oauth_token='encrypted_token_1',
            notion_api_token='encrypted_token_2',
            notion_database_id=self.test_database_id
        )
        
        # Load edit form
        response = self.client.get(f'{self.url}?user_id={self.test_user_id}')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'Edit Credentials for {self.test_user_id}')
        self.assertContains(response, self.test_database_id)
        self.assertContains(response, '********')  # Masked tokens
    
    def test_delete_nonexistent_credential(self):
        """Test deleting a credential that doesn't exist."""
        response = self.client.post(self.url, {
            'action': 'delete',
            'user_id': 'nonexistent_user',
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No credentials found')
    
    def test_encryption_error_handling(self):
        """Test that encryption errors are handled gracefully."""
        # Patch the encryption service to raise an error
        with patch('sync_admin.views.EncryptionService') as mock_enc:
            mock_enc.return_value.encrypt.side_effect = Exception('Encryption failed')
            
            response = self.client.post(self.url, {
                'action': 'save',
                'user_id': self.test_user_id,
                'google_oauth_token': self.test_google_token,
                'notion_api_token': self.test_notion_token,
                'notion_database_id': self.test_database_id,
            })
            
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Failed to save credentials')
            self.assertEqual(Credential.objects.count(), 0)
    
    def test_multiple_credentials_displayed(self):
        """Test that multiple credentials are displayed correctly."""
        # Create multiple credentials
        for i in range(3):
            Credential.objects.create(
                user_id=f'user{i}@example.com',
                google_oauth_token=f'encrypted_google_{i}',
                notion_api_token=f'encrypted_notion_{i}',
                notion_database_id=f'database_id_{i}'
            )
        
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, 200)
        for i in range(3):
            self.assertContains(response, f'user{i}@example.com')
            self.assertContains(response, f'database_id_{i}')


if __name__ == '__main__':
    import unittest
    unittest.main()
