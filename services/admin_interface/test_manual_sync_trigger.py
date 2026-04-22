"""
Unit tests for manual sync trigger functionality.

Requirements: 6.2 - Provide form to manually trigger sync jobs
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'admin_project.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock
from sync_admin.models import Credential, SyncJob
import uuid


class ManualSyncTriggerTestCase(TestCase):
    """Test cases for manual sync trigger view."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        
        # Create test credentials
        self.test_user_id = "test_user_1"
        self.credential = Credential.objects.create(
            user_id=self.test_user_id,
            google_oauth_token="encrypted_google_token",
            notion_api_token="encrypted_notion_token",
            notion_database_id="test_database_id"
        )
        
        # Create another test user
        self.test_user_id_2 = "test_user_2"
        self.credential_2 = Credential.objects.create(
            user_id=self.test_user_id_2,
            google_oauth_token="encrypted_google_token_2",
            notion_api_token="encrypted_notion_token_2",
            notion_database_id="test_database_id_2"
        )
    
    def test_get_manual_sync_trigger_page(self):
        """Test GET request to manual sync trigger page."""
        url = reverse('manual_sync_trigger')
        response = self.client.get(url)
        
        # Check response status
        assert response.status_code == 200
        
        # Check template used
        self.assertTemplateUsed(response, 'manual_sync_trigger.html')
        
        # Check users are in context
        assert 'users' in response.context
        users = list(response.context['users'])
        assert self.test_user_id in users
        assert self.test_user_id_2 in users
        
        # Check page content
        content = response.content.decode('utf-8')
        assert 'Manual Sync Trigger' in content
        assert 'Select a user' in content
        assert 'Sync Type' in content
        assert self.test_user_id in content
        assert self.test_user_id_2 in content
    
    @patch('sync_admin.views.httpx.Client')
    def test_post_manual_sync_trigger_incremental(self, mock_httpx_client):
        """Test POST request to trigger incremental sync."""
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        test_job_id = str(uuid.uuid4())
        mock_response.json.return_value = {
            'job_id': test_job_id,
            'status': 'queued'
        }
        
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.__exit__.return_value = None
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value = mock_client_instance
        
        # Make POST request
        url = reverse('manual_sync_trigger')
        response = self.client.post(url, {
            'user_id': self.test_user_id,
            'sync_type': 'incremental',
            'main_database_name': 'Keep'
        })
        
        # Check redirect to job detail page
        assert response.status_code == 302
        assert f'/sync-jobs/{test_job_id}/' in response.url
        
        # Verify HTTP client was called correctly
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        assert '/internal/sync/execute' in call_args[0][0]
        assert call_args[1]['json']['user_id'] == self.test_user_id
        assert call_args[1]['json']['full_sync'] is False
        assert call_args[1]['json']['main_database_name'] == 'Keep'
    
    @patch('sync_admin.views.httpx.Client')
    def test_post_manual_sync_trigger_full(self, mock_httpx_client):
        """Test POST request to trigger full sync."""
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        test_job_id = str(uuid.uuid4())
        mock_response.json.return_value = {
            'job_id': test_job_id,
            'status': 'queued'
        }
        
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.__exit__.return_value = None
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value = mock_client_instance
        
        # Make POST request
        url = reverse('manual_sync_trigger')
        response = self.client.post(url, {
            'user_id': self.test_user_id,
            'sync_type': 'full',
            'main_database_name': 'Keep'
        })
        
        # Check redirect to job detail page
        assert response.status_code == 302
        assert f'/sync-jobs/{test_job_id}/' in response.url
        
        # Verify HTTP client was called correctly
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        assert call_args[1]['json']['user_id'] == self.test_user_id
        assert call_args[1]['json']['full_sync'] is True
        assert call_args[1]['json']['main_database_name'] == 'Keep'
    
    def test_post_manual_sync_trigger_missing_user(self):
        """Test POST request with missing user_id."""
        url = reverse('manual_sync_trigger')
        response = self.client.post(url, {
            'sync_type': 'incremental',
            'main_database_name': 'Keep'
        })
        
        # Should return to form with error
        assert response.status_code == 200
        self.assertTemplateUsed(response, 'manual_sync_trigger.html')
        
        # Check for error message in messages
        messages = list(response.context['messages'])
        assert len(messages) > 0
        assert 'select a user' in str(messages[0]).lower()
    
    def test_post_manual_sync_trigger_missing_sync_type(self):
        """Test POST request with missing sync_type."""
        url = reverse('manual_sync_trigger')
        response = self.client.post(url, {
            'user_id': self.test_user_id,
            'main_database_name': 'Keep'
        })
        
        # Should return to form with error
        assert response.status_code == 200
        self.assertTemplateUsed(response, 'manual_sync_trigger.html')
        
        # Check for error message
        messages = list(response.context['messages'])
        assert len(messages) > 0
        assert 'select a sync type' in str(messages[0]).lower()
    
    def test_post_manual_sync_trigger_missing_main_database_name(self):
        """Test POST request with missing main database name."""
        url = reverse('manual_sync_trigger')
        response = self.client.post(url, {
            'user_id': self.test_user_id,
            'sync_type': 'incremental',
            'main_database_name': ''
        })

        assert response.status_code == 200
        self.assertTemplateUsed(response, 'manual_sync_trigger.html')

        messages = list(response.context['messages'])
        assert len(messages) > 0
        assert 'main notion database name' in str(messages[0]).lower()

    def test_post_manual_sync_trigger_user_without_credentials(self):
        """Test POST request with user that has no credentials."""
        url = reverse('manual_sync_trigger')
        response = self.client.post(url, {
            'user_id': 'nonexistent_user',
            'sync_type': 'incremental',
            'main_database_name': 'Keep'
        })
        
        # Should return to form with error
        assert response.status_code == 200
        self.assertTemplateUsed(response, 'manual_sync_trigger.html')
        
        # Check for error message
        messages = list(response.context['messages'])
        assert len(messages) > 0
        assert 'no credentials found' in str(messages[0]).lower()
    
    @patch('sync_admin.views.httpx.Client')
    def test_post_manual_sync_trigger_sync_service_error(self, mock_httpx_client):
        """Test POST request when Sync Service returns an error."""
        # Mock the HTTP response with error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.__exit__.return_value = None
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value = mock_client_instance
        
        # Make POST request
        url = reverse('manual_sync_trigger')
        response = self.client.post(url, {
            'user_id': self.test_user_id,
            'sync_type': 'incremental',
            'main_database_name': 'Keep'
        })
        
        # Should return to form with error
        assert response.status_code == 200
        self.assertTemplateUsed(response, 'manual_sync_trigger.html')
        
        # Check for error message
        messages = list(response.context['messages'])
        assert len(messages) > 0
        assert 'failed to initiate' in str(messages[0]).lower()
    
    @patch('sync_admin.views.httpx.Client')
    def test_post_manual_sync_trigger_connection_error(self, mock_httpx_client):
        """Test POST request when connection to Sync Service fails."""
        # Mock connection error
        import httpx
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__.return_value = mock_client_instance
        mock_client_instance.__exit__.return_value = None
        mock_client_instance.post.side_effect = httpx.RequestError("Connection failed")
        mock_httpx_client.return_value = mock_client_instance
        
        # Make POST request
        url = reverse('manual_sync_trigger')
        response = self.client.post(url, {
            'user_id': self.test_user_id,
            'sync_type': 'incremental',
            'main_database_name': 'Keep'
        })
        
        # Should return to form with error
        assert response.status_code == 200
        self.assertTemplateUsed(response, 'manual_sync_trigger.html')
        
        # Check for error message
        messages = list(response.context['messages'])
        assert len(messages) > 0
        assert 'failed to connect' in str(messages[0]).lower()
    
    def test_manual_sync_trigger_no_users(self):
        """Test manual sync trigger page when no users have credentials."""
        # Delete all credentials
        Credential.objects.all().delete()
        
        url = reverse('manual_sync_trigger')
        response = self.client.get(url)
        
        # Check response
        assert response.status_code == 200
        
        # Check that warning is displayed
        content = response.content.decode('utf-8')
        assert 'No users found' in content or 'no users' in content.lower()


def run_tests():
    """Run the manual sync trigger tests."""
    from django.test.utils import get_runner
    from django.conf import settings
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False, keepdb=False)
    
    # Run only this test case
    failures = test_runner.run_tests(['__main__'])
    
    return failures


if __name__ == '__main__':
    print("Running manual sync trigger tests...")
    print("=" * 70)
    
    failures = run_tests()
    
    print("=" * 70)
    if failures == 0:
        print("✓ All manual sync trigger tests passed!")
    else:
        print(f"✗ {failures} test(s) failed")
        sys.exit(1)
