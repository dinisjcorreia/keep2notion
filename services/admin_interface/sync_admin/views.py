"""Views for the sync_admin app."""

from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.utils import timezone
from django.contrib import messages
from datetime import timedelta, datetime
import httpx
from django.conf import settings
from .models import SyncJob, SyncState, Credential, SyncLog
import sys
import os

# Add shared directory to path to import encryption utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../shared'))
from encryption import EncryptionService


def dashboard(request):
    """
    Dashboard view showing recent sync jobs, statistics, and system health.
    
    Requirements: 6.1 - Display dashboard showing recent sync jobs and their status
    """
    # Get recent sync jobs (last 20)
    recent_jobs = SyncJob.objects.all()[:20]
    
    # Calculate statistics for the last 24 hours
    last_24h = timezone.now() - timedelta(hours=24)
    
    # Success/failure statistics
    stats = {
        'total_jobs': SyncJob.objects.count(),
        'jobs_last_24h': SyncJob.objects.filter(created_at__gte=last_24h).count(),
        'successful_jobs': SyncJob.objects.filter(status='completed').count(),
        'failed_jobs': SyncJob.objects.filter(status='failed').count(),
        'running_jobs': SyncJob.objects.filter(status='running').count(),
        'queued_jobs': SyncJob.objects.filter(status='queued').count(),
    }
    
    # Calculate success rate
    if stats['total_jobs'] > 0:
        stats['success_rate'] = round(
            (stats['successful_jobs'] / stats['total_jobs']) * 100, 1
        )
    else:
        stats['success_rate'] = 0
    
    # Get total notes synced
    stats['total_notes_synced'] = SyncState.objects.count()
    
    # Get unique users
    stats['total_users'] = Credential.objects.count()
    
    # Check system health
    health_status = check_system_health()
    
    context = {
        'recent_jobs': recent_jobs,
        'stats': stats,
        'health_status': health_status,
    }
    
    return render(request, 'dashboard.html', context)


def check_system_health():
    """
    Check the health of various system components.
    
    Returns:
        dict: Health status of each component
    """
    health = {
        'database': 'up',
        'sync_service': 'unknown',
        'overall': 'healthy',
    }
    
    # Check database connectivity
    try:
        SyncJob.objects.count()
        health['database'] = 'up'
    except Exception as e:
        health['database'] = 'down'
        health['overall'] = 'degraded'
    
    # Check Sync Service connectivity
    try:
        sync_service_url = settings.SYNC_SERVICE_URL
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{sync_service_url}/health")
            if response.status_code == 200:
                health['sync_service'] = 'up'
            else:
                health['sync_service'] = 'down'
                health['overall'] = 'degraded'
    except Exception as e:
        health['sync_service'] = 'down'
        health['overall'] = 'degraded'
    
    return health



def sync_job_list(request):
    """
    Paginated list view for sync jobs with filters.
    
    Requirements: 6.1, 6.5 - Display paginated list of sync jobs with filters
    """
    # Get filter parameters from request
    status_filter = request.GET.get('status', '')
    user_filter = request.GET.get('user', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    # Start with all sync jobs
    jobs = SyncJob.objects.all()
    
    # Apply filters
    if status_filter:
        jobs = jobs.filter(status=status_filter)
    
    if user_filter:
        jobs = jobs.filter(user_id__icontains=user_filter)
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            jobs = jobs.filter(created_at__gte=date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day to include the entire end date
            date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
            jobs = jobs.filter(created_at__lte=date_to_obj)
        except ValueError:
            pass
    
    # Paginate results (50 per page as per requirement 6.5)
    paginator = Paginator(jobs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    # Get available status choices for filter dropdown
    status_choices = SyncJob.STATUS_CHOICES
    
    # Get unique users for filter dropdown (limit to 100 for performance)
    unique_users = SyncJob.objects.values_list('user_id', flat=True).distinct()[:100]
    
    context = {
        'page_obj': page_obj,
        'status_choices': status_choices,
        'unique_users': unique_users,
        'current_filters': {
            'status': status_filter,
            'user': user_filter,
            'date_from': date_from,
            'date_to': date_to,
        },
        'total_count': paginator.count,
    }
    
    return render(request, 'sync_job_list.html', context)


def sync_job_detail(request, job_id):
    """
    Detail view for a single sync job showing information and logs.
    
    Requirements: 6.3 - Display detailed logs for each sync job
    """
    # Get the sync job or return 404
    job = get_object_or_404(SyncJob, job_id=job_id)
    
    # Get all logs for this job
    logs = SyncLog.objects.filter(job_id=job_id).order_by('-created_at')
    
    # Paginate logs (100 per page)
    paginator = Paginator(logs, 100)
    page_number = request.GET.get('page', 1)
    logs_page = paginator.get_page(page_number)
    
    # Calculate job duration if completed
    duration = None
    if job.completed_at and job.created_at:
        duration = job.completed_at - job.created_at
    
    # Calculate success rate
    success_rate = 0
    if job.total_notes > 0:
        success_rate = round(
            ((job.processed_notes - job.failed_notes) / job.total_notes) * 100, 1
        )
    
    context = {
        'job': job,
        'logs_page': logs_page,
        'duration': duration,
        'success_rate': success_rate,
    }
    
    return render(request, 'sync_job_detail.html', context)


def retry_sync_job(request, job_id):
    """
    Retry a failed sync job.
    
    Requirements: 6.3 - Allow retry of failed jobs
    """
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('sync_job_detail', job_id=job_id)
    
    # Get the sync job
    job = get_object_or_404(SyncJob, job_id=job_id)
    
    # Check if job is in a failed state
    if job.status != 'failed':
        messages.warning(request, f'Job {job_id} is not in a failed state. Current status: {job.status}')
        return redirect('sync_job_detail', job_id=job_id)
    
    try:
        # Get user credentials
        try:
            credential = Credential.objects.get(user_id=job.user_id)
        except Credential.DoesNotExist:
            messages.error(request, f'No credentials found for user {job.user_id}')
            return redirect('sync_job_detail', job_id=job_id)
        
        # Call Sync Service to retry the job
        sync_service_url = settings.SYNC_SERVICE_URL
        
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{sync_service_url}/internal/sync/execute",
                json={
                    "user_id": job.user_id,
                    "full_sync": job.full_sync,
                    "main_database_name": "Keep",
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                new_job_id = result.get('job_id')
                messages.success(
                    request, 
                    f'Sync job retry initiated successfully. New job ID: {new_job_id}'
                )
                # Redirect to the new job
                return redirect('sync_job_detail', job_id=new_job_id)
            else:
                messages.error(
                    request, 
                    f'Failed to retry sync job. Status: {response.status_code}, Error: {response.text}'
                )
    
    except httpx.RequestError as e:
        messages.error(request, f'Failed to connect to Sync Service: {str(e)}')
    except Exception as e:
        messages.error(request, f'Unexpected error: {str(e)}')
    
    return redirect('sync_job_detail', job_id=job_id)


def abort_sync_job(request, job_id):
    """
    Abort a running or queued sync job.
    
    Requirements: 6.3 - Allow aborting running jobs
    """
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('sync_job_detail', job_id=job_id)
    
    # Get the sync job
    job = get_object_or_404(SyncJob, job_id=job_id)
    
    # Check if job can be aborted
    if job.status not in ['running', 'queued']:
        messages.warning(request, f'Job {job_id} cannot be aborted. Current status: {job.status}')
        return redirect('sync_job_detail', job_id=job_id)
    
    try:
        # Call Sync Service to abort the job
        sync_service_url = settings.SYNC_SERVICE_URL
        
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{sync_service_url}/internal/sync/abort/{job_id}"
            )
            
            if response.status_code == 200:
                result = response.json()
                messages.success(
                    request, 
                    f'Sync job {job_id} has been aborted successfully.'
                )
            else:
                messages.error(
                    request, 
                    f'Failed to abort sync job. Status: {response.status_code}, Error: {response.text}'
                )
    
    except httpx.RequestError as e:
        messages.error(request, f'Failed to connect to Sync Service: {str(e)}')
    except Exception as e:
        messages.error(request, f'Unexpected error: {str(e)}')
    
    return redirect('sync_job_detail', job_id=job_id)


def manual_sync_trigger(request):
    """
    Manual sync trigger form view.
    
    Requirements: 6.2 - Provide form to manually trigger sync jobs
    """
    # Get all users with credentials for the dropdown
    users = Credential.objects.all().values_list('user_id', flat=True)
    
    if request.method == 'POST':
        # Get form data
        user_id = request.POST.get('user_id')
        sync_type = request.POST.get('sync_type')
        main_database_name = request.POST.get('main_database_name', '').strip()
        
        # Validate inputs
        if not user_id:
            messages.error(request, 'Please select a user.')
            return render(request, 'manual_sync_trigger.html', {'users': users})
        
        if not sync_type:
            messages.error(request, 'Please select a sync type.')
            return render(request, 'manual_sync_trigger.html', {'users': users})

        if not main_database_name:
            messages.error(request, 'Please enter the main Notion database name.')
            return render(request, 'manual_sync_trigger.html', {'users': users})
        
        # Determine if it's a full sync
        full_sync = (sync_type == 'full')
        
        try:
            # Verify user has credentials
            try:
                credential = Credential.objects.get(user_id=user_id)
            except Credential.DoesNotExist:
                messages.error(request, f'No credentials found for user {user_id}')
                return render(request, 'manual_sync_trigger.html', {'users': users})
            
            # Call Sync Service to initiate sync
            sync_service_url = settings.SYNC_SERVICE_URL
            
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{sync_service_url}/internal/sync/execute",
                    json={
                        "user_id": user_id,
                        "full_sync": full_sync,
                        "main_database_name": main_database_name,
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    job_id = result.get('job_id')
                    messages.success(
                        request,
                        f'Sync job initiated successfully! Job ID: {job_id}'
                    )
                    # Redirect to the job detail page
                    return redirect('sync_job_detail', job_id=job_id)
                else:
                    messages.error(
                        request,
                        f'Failed to initiate sync job. Status: {response.status_code}, Error: {response.text}'
                    )
        
        except httpx.RequestError as e:
            messages.error(request, f'Failed to connect to Sync Service: {str(e)}')
        except Exception as e:
            messages.error(request, f'Unexpected error: {str(e)}')
        
        return render(request, 'manual_sync_trigger.html', {'users': users})
    
    # GET request - display the form
    return render(request, 'manual_sync_trigger.html', {'users': users})


def credential_config(request):
    """
    Credential configuration view for managing Google Keep and Notion credentials.
    
    Requirements: 6.4 - Allow configuration of Google Keep and Notion credentials
    Requirements: 10.1 - Encrypt credentials before storing
    """
    # Initialize encryption service
    encryption_service = EncryptionService()
    
    # Get all existing credentials
    credentials = Credential.objects.all()
    
    # Handle credential selection for editing
    selected_user_id = request.GET.get('user_id', '')
    selected_credential = None
    
    if selected_user_id:
        try:
            selected_credential = Credential.objects.get(user_id=selected_user_id)
        except Credential.DoesNotExist:
            messages.warning(request, f'No credentials found for user {selected_user_id}')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'save':
            # Get form data
            user_id = request.POST.get('user_id', '').strip()
            google_oauth_token = request.POST.get('google_oauth_token', '').strip()
            notion_api_token = request.POST.get('notion_api_token', '').strip()
            notion_database_id = request.POST.get('notion_database_id', '').strip()
            existing_credential = Credential.objects.filter(user_id=user_id).first() if user_id else None
            
            # Validate inputs
            if not user_id:
                messages.error(request, 'User ID is required.')
                return render(request, 'credential_config.html', {
                    'credentials': credentials,
                    'selected_credential': selected_credential,
                })
            
            if not google_oauth_token and not existing_credential:
                messages.error(request, 'Google OAuth token is required.')
                return render(request, 'credential_config.html', {
                    'credentials': credentials,
                    'selected_credential': selected_credential,
                })
            
            if not notion_api_token and not existing_credential:
                messages.error(request, 'Notion API token is required.')
                return render(request, 'credential_config.html', {
                    'credentials': credentials,
                    'selected_credential': selected_credential,
                })
            
            if not notion_database_id:
                messages.error(request, 'Notion database ID is required.')
                return render(request, 'credential_config.html', {
                    'credentials': credentials,
                    'selected_credential': selected_credential,
                })
            
            try:
                if existing_credential and (not google_oauth_token or google_oauth_token == '********'):
                    encrypted_google_token = existing_credential.google_oauth_token
                else:
                    encrypted_google_token = encryption_service.encrypt(google_oauth_token)

                if existing_credential and (not notion_api_token or notion_api_token == '********'):
                    encrypted_notion_token = existing_credential.notion_api_token
                else:
                    encrypted_notion_token = encryption_service.encrypt(notion_api_token)
                
                # Create or update credential
                credential, created = Credential.objects.update_or_create(
                    user_id=user_id,
                    defaults={
                        'google_oauth_token': encrypted_google_token,
                        'notion_api_token': encrypted_notion_token,
                        'notion_database_id': notion_database_id,
                    }
                )
                
                if created:
                    messages.success(request, f'Credentials for user {user_id} created successfully.')
                else:
                    messages.success(request, f'Credentials for user {user_id} updated successfully.')
                
                # Redirect to clear form
                return redirect('credential_config')
            
            except Exception as e:
                messages.error(request, f'Failed to save credentials: {str(e)}')
        
        elif action == 'delete':
            # Delete credential
            user_id = request.POST.get('user_id', '').strip()
            
            if not user_id:
                messages.error(request, 'User ID is required for deletion.')
            else:
                try:
                    credential = Credential.objects.get(user_id=user_id)
                    credential.delete()
                    messages.success(request, f'Credentials for user {user_id} deleted successfully.')
                    return redirect('credential_config')
                except Credential.DoesNotExist:
                    messages.error(request, f'No credentials found for user {user_id}')
                except Exception as e:
                    messages.error(request, f'Failed to delete credentials: {str(e)}')
    
    context = {
        'credentials': credentials,
        'selected_credential': selected_credential,
        'selected_user_id': selected_user_id,
    }
    
    return render(request, 'credential_config.html', context)


def clear_sync_state(request, user_id):
    """
    Clear sync state for a user (for testing purposes).
    
    This removes all sync state records for a user, causing the next sync
    to create new Notion pages instead of trying to update existing ones.
    
    Use case: When Notion pages have been deleted but sync state still exists.
    """
    if request.method != 'POST':
        messages.error(request, 'Invalid request method.')
        return redirect('credential_config')
    
    try:
        # Get count of records to delete
        sync_state_count = SyncState.objects.filter(user_id=user_id).count()
        
        if sync_state_count == 0:
            messages.info(request, f'No sync state records found for user {user_id}')
            return redirect('credential_config')
        
        # Delete all sync state records for this user
        SyncState.objects.filter(user_id=user_id).delete()
        
        messages.success(
            request,
            f'Cleared {sync_state_count} sync state record(s) for user {user_id}. '
            f'Next sync will create new Notion pages.'
        )
    
    except Exception as e:
        messages.error(request, f'Failed to clear sync state: {str(e)}')
    
    return redirect('credential_config')
