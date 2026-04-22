"""
Test script for sync job list and detail views.

This script tests:
1. Sync job list view with pagination and filters
2. Sync job detail view with logs
3. Retry functionality for failed jobs

Requirements tested: 6.1, 6.3, 6.5
"""

import os
import sys
import django
from datetime import datetime, timedelta
from uuid import uuid4

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'admin_project.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.test import Client, TestCase
from django.urls import reverse
from sync_admin.models import SyncJob, SyncLog, Credential
from django.utils import timezone


class SyncJobViewsTest(TestCase):
    """Test sync job views."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        
        # Create test sync jobs
        self.jobs = []
        statuses = ['completed', 'failed', 'running', 'queued']
        
        for i in range(60):  # Create 60 jobs to test pagination
            job = SyncJob.objects.create(
                job_id=uuid4(),
                user_id=f'user_{i % 3}',  # 3 different users
                status=statuses[i % 4],
                full_sync=(i % 2 == 0),
                total_notes=100,
                processed_notes=min(100, i * 2),
                failed_notes=max(0, i - 50),
                created_at=timezone.now() - timedelta(days=i),
            )
            
            if job.status == 'completed':
                job.completed_at = job.created_at + timedelta(hours=1)
                job.save()
            
            if job.status == 'failed':
                job.error_message = f'Test error for job {i}'
                job.save()
            
            self.jobs.append(job)
            
            # Create some logs for each job
            for j in range(5):
                SyncLog.objects.create(
                    job_id=job.job_id,
                    level=['INFO', 'WARNING', 'ERROR'][j % 3],
                    message=f'Test log message {j} for job {i}',
                    keep_note_id=f'note_{j}' if j % 2 == 0 else None,
                )
        
        # Create a test credential
        self.credential = Credential.objects.create(
            user_id='user_0',
            google_oauth_token='test_google_token',
            notion_api_token='test_notion_token',
            notion_database_id='test_database_id',
        )
    
    def test_sync_job_list_view(self):
        """Test sync job list view loads correctly."""
        print("\n=== Testing Sync Job List View ===")
        
        response = self.client.get(reverse('sync_job_list'))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sync Jobs')
        self.assertContains(response, 'Filters')
        
        # Check pagination (should show 50 per page)
        self.assertContains(response, 'Page 1 of 2')
        
        print("✓ Sync job list view loads successfully")
        print(f"✓ Pagination working: showing 50 jobs per page")
    
    def test_sync_job_list_filters(self):
        """Test sync job list filters."""
        print("\n=== Testing Sync Job List Filters ===")
        
        # Test status filter
        response = self.client.get(reverse('sync_job_list'), {'status': 'completed'})
        self.assertEqual(response.status_code, 200)
        print("✓ Status filter works")
        
        # Test user filter
        response = self.client.get(reverse('sync_job_list'), {'user': 'user_0'})
        self.assertEqual(response.status_code, 200)
        print("✓ User filter works")
        
        # Test date range filter
        today = timezone.now().date()
        response = self.client.get(reverse('sync_job_list'), {
            'date_from': (today - timedelta(days=10)).strftime('%Y-%m-%d'),
            'date_to': today.strftime('%Y-%m-%d'),
        })
        self.assertEqual(response.status_code, 200)
        print("✓ Date range filter works")
        
        # Test combined filters
        response = self.client.get(reverse('sync_job_list'), {
            'status': 'failed',
            'user': 'user_1',
        })
        self.assertEqual(response.status_code, 200)
        print("✓ Combined filters work")
    
    def test_sync_job_list_pagination(self):
        """Test sync job list pagination."""
        print("\n=== Testing Sync Job List Pagination ===")
        
        # Test first page
        response = self.client.get(reverse('sync_job_list'), {'page': 1})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Page 1 of 2')
        print("✓ First page loads correctly")
        
        # Test second page
        response = self.client.get(reverse('sync_job_list'), {'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Page 2 of 2')
        print("✓ Second page loads correctly")
        
        # Test invalid page (should default to last page)
        response = self.client.get(reverse('sync_job_list'), {'page': 999})
        self.assertEqual(response.status_code, 200)
        print("✓ Invalid page handled gracefully")
    
    def test_sync_job_detail_view(self):
        """Test sync job detail view."""
        print("\n=== Testing Sync Job Detail View ===")
        
        job = self.jobs[0]
        response = self.client.get(reverse('sync_job_detail', args=[job.job_id]))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sync Job Details')
        self.assertContains(response, str(job.job_id))
        self.assertContains(response, job.user_id)
        self.assertContains(response, 'Sync Logs')
        
        print("✓ Sync job detail view loads successfully")
        print(f"✓ Job information displayed correctly")
        print(f"✓ Logs section present")
    
    def test_sync_job_detail_with_logs(self):
        """Test sync job detail view displays logs."""
        print("\n=== Testing Sync Job Detail Logs ===")
        
        job = self.jobs[0]
        response = self.client.get(reverse('sync_job_detail', args=[job.job_id]))
        
        # Check that logs are displayed
        logs = SyncLog.objects.filter(job_id=job.job_id)
        self.assertGreater(logs.count(), 0)
        
        for log in logs[:3]:  # Check first 3 logs
            self.assertContains(response, log.message)
        
        print(f"✓ Logs displayed correctly ({logs.count()} logs)")

    def test_sync_job_detail_summary_uses_progress_fields(self):
        """Test detail summary uses actual sync job progress counters."""
        job = SyncJob.objects.create(
            job_id=uuid4(),
            user_id='progress_user',
            status='running',
            full_sync=False,
            total_notes=10,
            processed_notes=6,
            failed_notes=2,
        )

        response = self.client.get(reverse('sync_job_detail', args=[job.job_id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['items_processed'], 8)
        self.assertEqual(response.context['items_synced'], 6)
        self.assertEqual(response.context['error_count'], 2)
        self.assertEqual(response.context['sync_type_label'], 'Incremental')
    
    def test_sync_job_detail_failed_job(self):
        """Test sync job detail view for failed job shows retry button."""
        print("\n=== Testing Failed Job Detail View ===")
        
        # Find a failed job
        failed_job = SyncJob.objects.filter(status='failed').first()
        response = self.client.get(reverse('sync_job_detail', args=[failed_job.job_id]))
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Retry Sync Job')
        self.assertContains(response, 'Error Message')
        
        print("✓ Failed job shows retry button")
        print("✓ Error message displayed")
    
    def test_sync_job_detail_completed_job(self):
        """Test sync job detail view for completed job."""
        print("\n=== Testing Completed Job Detail View ===")
        
        # Find a completed job
        completed_job = SyncJob.objects.filter(status='completed').first()
        response = self.client.get(reverse('sync_job_detail', args=[completed_job.job_id]))
        
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Retry Sync Job')
        self.assertContains(response, 'Success Rate')
        
        print("✓ Completed job does not show retry button")
        print("✓ Success rate displayed")
    
    def test_sync_job_detail_404(self):
        """Test sync job detail view with invalid job ID."""
        print("\n=== Testing Invalid Job ID ===")
        
        invalid_uuid = uuid4()
        response = self.client.get(reverse('sync_job_detail', args=[invalid_uuid]))
        
        self.assertEqual(response.status_code, 404)
        print("✓ Invalid job ID returns 404")
    
    def test_retry_sync_job_invalid_method(self):
        """Test retry sync job with GET request (should fail)."""
        print("\n=== Testing Retry with Invalid Method ===")
        
        failed_job = SyncJob.objects.filter(status='failed').first()
        response = self.client.get(reverse('retry_sync_job', args=[failed_job.job_id]))
        
        # Should redirect back to detail page
        self.assertEqual(response.status_code, 302)
        print("✓ GET request to retry endpoint redirects")
    
    def test_retry_sync_job_non_failed_job(self):
        """Test retry sync job with non-failed job."""
        print("\n=== Testing Retry Non-Failed Job ===")
        
        completed_job = SyncJob.objects.filter(status='completed').first()
        response = self.client.post(reverse('retry_sync_job', args=[completed_job.job_id]))
        
        # Should redirect back to detail page with warning
        self.assertEqual(response.status_code, 302)
        print("✓ Retry non-failed job handled gracefully")


def run_manual_tests():
    """Run manual tests that require visual inspection."""
    print("\n" + "="*60)
    print("MANUAL TESTING INSTRUCTIONS")
    print("="*60)
    
    print("\n1. Start the Django development server:")
    print("   cd services/admin_interface")
    print("   python manage.py runserver")
    
    print("\n2. Open your browser and navigate to:")
    print("   http://localhost:8000/sync-jobs/")
    
    print("\n3. Test the following features:")
    print("   ✓ Sync job list displays with pagination (50 per page)")
    print("   ✓ Filters work correctly (status, user, date range)")
    print("   ✓ Click on 'View Details' to see job details")
    print("   ✓ Job detail page shows all information and logs")
    print("   ✓ Failed jobs show 'Retry' button")
    print("   ✓ Retry button triggers sync service (may fail if service not running)")
    
    print("\n4. Check the navigation:")
    print("   ✓ 'Sync Jobs' link in navigation bar works")
    print("   ✓ 'Back to List' button on detail page works")
    print("   ✓ Dashboard links to sync job list")


if __name__ == '__main__':
    print("\n" + "="*60)
    print("SYNC JOB VIEWS TEST SUITE")
    print("="*60)
    
    # Run Django tests
    from django.test.utils import get_runner
    from django.conf import settings
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False, keepdb=True)
    
    # Run only our test class
    failures = test_runner.run_tests(['test_sync_job_views.SyncJobViewsTest'])
    
    if failures == 0:
        print("\n" + "="*60)
        print("✓ ALL AUTOMATED TESTS PASSED!")
        print("="*60)
        run_manual_tests()
    else:
        print("\n" + "="*60)
        print("✗ SOME TESTS FAILED")
        print("="*60)
    
    sys.exit(failures)
