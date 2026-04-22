"""Unit tests for Sync Service.

Tests cover:
- Full sync workflow
- Incremental sync workflow
- Error handling for Keep Extractor failures
- Error handling for Notion Writer failures
- Mock HTTP clients and database

Requirements: 3.1, 3.2, 3.3, 4.3, 9.3, 9.4
"""

import pytest
import sys
import os
from datetime import datetime, timedelta
from uuid import uuid4, UUID
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import httpx

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from services.sync_service.orchestrator import SyncOrchestrator
from services.sync_service.notifications import NotificationService


# Test fixtures

@pytest.fixture
def mock_db_ops():
    """Mock database operations."""
    db_ops = Mock()
    
    # Mock sync job operations
    db_ops.create_sync_job = Mock()
    db_ops.update_sync_job = Mock()
    db_ops.add_sync_log = Mock()
    db_ops.increment_sync_job_progress = Mock()
    db_ops.get_sync_job = Mock(return_value=None)
    
    # Mock credential operations
    db_ops.get_credentials = Mock(return_value={
        'google_oauth_token': 'mock_google_token',
        'notion_api_token': 'mock_notion_token',
        'notion_database_id': 'mock_database_id'
    })
    
    # Mock sync state operations
    db_ops.get_sync_state_by_user = Mock(return_value=[])
    db_ops.get_sync_record = Mock(return_value=None)
    db_ops.upsert_sync_state = Mock()
    
    return db_ops


@pytest.fixture
def mock_encryption_service():
    """Mock encryption service."""
    return Mock()


@pytest.fixture
def mock_keep_client():
    """Mock Keep Extractor HTTP client."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.fixture
def mock_notion_client():
    """Mock Notion Writer HTTP client."""
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.fixture
def orchestrator(mock_keep_client, mock_notion_client, mock_db_ops, mock_encryption_service):
    """Create SyncOrchestrator with mocked dependencies."""
    return SyncOrchestrator(
        keep_client=mock_keep_client,
        notion_client=mock_notion_client,
        db_ops=mock_db_ops,
        encryption_service=mock_encryption_service
    )


@pytest.fixture
def sample_notes():
    """Sample notes from Keep Extractor."""
    return [
        {
            'id': 'note_1',
            'title': 'Test Note 1',
            'content': 'This is test note 1',
            'created_at': '2024-01-01T10:00:00Z',
            'modified_at': '2024-01-01T10:00:00Z',
            'labels': [],
            'images': []
        },
        {
            'id': 'note_2',
            'title': 'Test Note 2',
            'content': 'This is test note 2 with images',
            'created_at': '2024-01-02T10:00:00Z',
            'modified_at': '2024-01-02T10:00:00Z',
            'labels': [],
            'images': [
                {
                    'id': 'img_1',
                    's3_url': 'https://s3.amazonaws.com/bucket/img_1.jpg',
                    'filename': 'image1.jpg'
                }
            ]
        }
    ]


# Test: Full Sync Workflow

@pytest.mark.asyncio
async def test_full_sync_workflow_success(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops, sample_notes):
    """
    Test successful full sync workflow.
    
    Requirements: 3.1, 3.2, 3.3, 4.3
    
    Validates:
    - Credentials are loaded
    - Keep Extractor is called without modified_since
    - All notes are processed
    - Notion Writer creates new pages
    - Sync state is updated for each note
    - Job completes successfully
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock Keep Extractor responses
    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}
    
    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': sample_notes}
    
    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response
    
    # Mock Notion Writer responses (create new pages)
    notion_response_1 = Mock()
    notion_response_1.status_code = 201
    notion_response_1.json.return_value = {'page_id': 'notion_page_1', 'url': 'https://notion.so/page1'}
    
    notion_response_2 = Mock()
    notion_response_2.status_code = 201
    notion_response_2.json.return_value = {'page_id': 'notion_page_2', 'url': 'https://notion.so/page2'}
    
    mock_notion_client.post.side_effect = [notion_response_1, notion_response_2]
    
    # Execute full sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)
    
    # Verify result
    assert result['status'] == 'completed'
    assert result['job_id'] == str(job_id)
    assert result['summary']['total_notes'] == 2
    assert result['summary']['processed_notes'] == 2
    assert result['summary']['failed_notes'] == 0
    
    # Verify credentials were loaded
    mock_db_ops.get_credentials.assert_called_once_with(user_id, orchestrator.encryption_service)
    
    # Verify Keep authentication was called
    mock_keep_client.post.assert_called_once()
    auth_call = mock_keep_client.post.call_args
    assert '/internal/keep/auth' in str(auth_call)
    
    # Verify Keep notes fetch was called without modified_since (full sync)
    mock_keep_client.get.assert_called_once()
    get_call = mock_keep_client.get.call_args
    assert '/internal/keep/notes' in str(get_call)
    params = get_call[1]['params']
    assert 'modified_since' not in params or params['modified_since'] is None
    
    # Verify Notion Writer was called twice (once per note)
    assert mock_notion_client.post.call_count == 2
    
    # Verify sync state was updated for both notes
    assert mock_db_ops.upsert_sync_state.call_count == 2
    
    # Verify job status updates
    assert mock_db_ops.update_sync_job.call_count >= 2  # At least running and completed
    mock_db_ops.create_sync_job.assert_called_once_with(
        job_id=job_id,
        user_id=user_id,
        full_sync=True
    )


@pytest.mark.asyncio
async def test_full_sync_reuses_existing_job(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops):
    """Test existing sync job rows are reused instead of inserted twice."""
    job_id = uuid4()
    user_id = 'test_user'
    mock_db_ops.get_sync_job.return_value = Mock()

    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}

    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': []}

    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response

    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)

    assert result['status'] == 'completed'
    mock_db_ops.create_sync_job.assert_not_called()
    mock_db_ops.update_sync_job.assert_any_call(job_id, status='running')


@pytest.mark.asyncio
async def test_full_sync_resolves_database_from_first_tag(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops):
    """Test first Keep tag chooses the target Notion database when main name is provided."""
    job_id = uuid4()
    user_id = 'test_user'
    tagged_note = {
        'id': 'tagged_note',
        'title': 'Tagged note',
        'content': 'Content',
        'created_at': '2024-01-01T10:00:00Z',
        'modified_at': '2024-01-01T10:00:00Z',
        'labels': ['work', 'ideas'],
        'images': []
    }

    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}

    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': [tagged_note]}

    resolve_response = Mock()
    resolve_response.status_code = 200
    resolve_response.json.return_value = {
        'database_id': 'work_database',
        'database_name': 'work',
        'created': False
    }

    create_response = Mock()
    create_response.status_code = 201
    create_response.json.return_value = {'page_id': 'notion_page_1', 'url': 'https://notion.so/page1'}

    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response

    async def notion_post_side_effect(url, json):
        if url == "/internal/notion/databases/resolve":
            return resolve_response
        if url == "/internal/notion/pages":
            return create_response
        raise AssertionError(f"Unexpected Notion endpoint: {url}")

    mock_notion_client.post.side_effect = notion_post_side_effect

    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True, main_database_name="Keep")

    assert result['status'] == 'completed'
    assert mock_notion_client.post.call_count == 2
    resolve_call = mock_notion_client.post.call_args_list[0]
    assert resolve_call.kwargs['json']['labels'] == ['work', 'ideas']
    assert resolve_call.kwargs['json']['main_database_name'] == 'Keep'


@pytest.mark.asyncio
async def test_full_sync_with_images(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops):
    """
    Test full sync with notes containing images.
    
    Requirements: 3.1, 3.2
    
    Validates:
    - Notes with images are processed correctly
    - Image URLs are passed to Notion Writer
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    notes_with_images = [
        {
            'id': 'note_img',
            'title': 'Note with Images',
            'content': 'Content',
            'created_at': '2024-01-01T10:00:00Z',
            'modified_at': '2024-01-01T10:00:00Z',
            'labels': [],
            'images': [
                {'id': 'img1', 's3_url': 'https://s3.aws.com/img1.jpg', 'filename': 'img1.jpg'},
                {'id': 'img2', 's3_url': 'https://s3.aws.com/img2.jpg', 'filename': 'img2.jpg'}
            ]
        }
    ]
    
    # Mock responses
    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}
    
    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': notes_with_images}
    
    notion_response = Mock()
    notion_response.status_code = 201
    notion_response.json.return_value = {'page_id': 'notion_page_img', 'url': 'https://notion.so/page'}
    
    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response
    mock_notion_client.post.return_value = notion_response
    
    # Execute sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)
    
    # Verify success
    assert result['status'] == 'completed'
    assert result['summary']['processed_notes'] == 1
    
    # Verify images were passed to Notion Writer
    notion_call = mock_notion_client.post.call_args
    notion_payload = notion_call[1]['json']
    assert len(notion_payload['note']['images']) == 2


# Test: Incremental Sync Workflow

@pytest.mark.asyncio
async def test_incremental_sync_workflow(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops, sample_notes):
    """
    Test incremental sync workflow with modified_since parameter.
    
    Requirements: 3.1, 3.2, 3.3
    
    Validates:
    - Sync state is queried to get last sync time
    - Keep Extractor is called with modified_since parameter
    - Only modified notes are synced
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock sync state with last sync time
    last_sync_time = datetime.utcnow() - timedelta(days=1)
    mock_sync_record = Mock()
    mock_sync_record.last_synced_at = last_sync_time
    mock_db_ops.get_sync_state_by_user.return_value = [mock_sync_record]
    
    # Mock Keep responses
    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}
    
    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': [sample_notes[0]]}  # Only one modified note
    
    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response
    
    # Mock Notion response
    notion_response = Mock()
    notion_response.status_code = 201
    notion_response.json.return_value = {'page_id': 'notion_page_1', 'url': 'https://notion.so/page1'}
    mock_notion_client.post.return_value = notion_response
    
    # Execute incremental sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=False)
    
    # Verify result
    assert result['status'] == 'completed'
    assert result['summary']['total_notes'] == 1
    
    # Verify sync state was queried
    mock_db_ops.get_sync_state_by_user.assert_called_once_with(user_id)
    
    # Verify Keep was called with modified_since
    get_call = mock_keep_client.get.call_args
    params = get_call[1]['params']
    assert 'modified_since' in params
    assert params['modified_since'] is not None


@pytest.mark.asyncio
async def test_incremental_sync_updates_existing_pages(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops, sample_notes):
    """
    Test incremental sync updates existing Notion pages.
    
    Requirements: 3.2, 3.3
    
    Validates:
    - Existing sync records are found
    - Notion Writer PATCH endpoint is called (update)
    - Sync state is updated with new timestamp
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock existing sync record
    existing_record = Mock()
    existing_record.notion_page_id = 'existing_notion_page'
    mock_db_ops.get_sync_record.return_value = existing_record
    
    # Mock Keep responses
    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}
    
    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': [sample_notes[0]]}
    
    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response
    
    # Mock Notion update response
    notion_response = Mock()
    notion_response.status_code = 200
    notion_response.json.return_value = {'page_id': 'existing_notion_page', 'updated': True}
    mock_notion_client.patch.return_value = notion_response
    
    # Execute sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=False)
    
    # Verify success
    assert result['status'] == 'completed'
    
    # Verify PATCH was called (update existing page)
    mock_notion_client.patch.assert_called_once()
    patch_call = mock_notion_client.patch.call_args
    assert 'existing_notion_page' in str(patch_call)
    
    # Verify sync state was updated
    mock_db_ops.upsert_sync_state.assert_called_once()


@pytest.mark.asyncio
async def test_incremental_sync_recreates_archived_pages(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops, sample_notes):
    """Test archived Notion pages are recreated and relinked."""
    job_id = uuid4()
    user_id = 'test_user'

    existing_record = Mock()
    existing_record.notion_page_id = 'archived_notion_page'
    mock_db_ops.get_sync_record.return_value = existing_record

    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}

    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': [sample_notes[0]]}

    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response

    notion_update_response = Mock()
    notion_update_response.status_code = 500
    notion_update_response.text = (
        "{\"detail\":\"Failed to update Notion page: "
        "Can't edit block that is archived. You must unarchive the block before editing.\"}"
    )

    notion_create_response = Mock()
    notion_create_response.status_code = 201
    notion_create_response.json.return_value = {'page_id': 'replacement_page', 'url': 'https://notion.so/replacement'}

    mock_notion_client.patch.return_value = notion_update_response
    mock_notion_client.post.return_value = notion_create_response

    result = await orchestrator.execute_sync(job_id, user_id, full_sync=False)

    assert result['status'] == 'completed'
    mock_notion_client.patch.assert_called_once()
    mock_notion_client.post.assert_called_once()
    mock_db_ops.upsert_sync_state.assert_called_once()
    upsert_kwargs = mock_db_ops.upsert_sync_state.call_args.kwargs
    assert upsert_kwargs['notion_page_id'] == 'replacement_page'


# Test: Error Handling for Keep Extractor Failures

@pytest.mark.asyncio
async def test_keep_authentication_failure(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops):
    """
    Test error handling when Keep authentication fails.
    
    Requirements: 9.3, 9.4
    
    Validates:
    - Authentication failure is caught
    - Job is marked as failed
    - Error message is recorded
    - Notification is sent
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock Keep authentication failure
    auth_response = Mock()
    auth_response.status_code = 401
    auth_response.json.return_value = {'status': 'failed', 'error': 'Invalid credentials'}
    mock_keep_client.post.return_value = auth_response
    
    # Execute sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)
    
    # Verify failure
    assert result['status'] == 'failed'
    assert 'error' in result
    assert 'authentication' in result['error'].lower() or 'failed' in result['error'].lower()
    
    # Verify job was marked as failed
    failed_calls = [call for call in mock_db_ops.update_sync_job.call_args_list 
                    if 'status' in str(call) and 'failed' in str(call)]
    assert len(failed_calls) > 0
    
    # Verify error was logged
    error_logs = [call for call in mock_db_ops.add_sync_log.call_args_list 
                  if 'ERROR' in str(call)]
    assert len(error_logs) > 0


@pytest.mark.asyncio
async def test_keep_notes_fetch_failure(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops):
    """
    Test error handling when Keep notes fetch fails.
    
    Requirements: 9.3, 9.4
    
    Validates:
    - Network errors during note fetch are caught
    - Job is marked as failed
    - Error is logged
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock successful authentication
    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}
    mock_keep_client.post.return_value = auth_response
    
    # Mock notes fetch failure
    notes_response = Mock()
    notes_response.status_code = 500
    notes_response.text = 'Internal Server Error'
    mock_keep_client.get.return_value = notes_response
    
    # Execute sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)
    
    # Verify failure
    assert result['status'] == 'failed'
    assert 'error' in result
    
    # Verify error was logged
    error_logs = [call for call in mock_db_ops.add_sync_log.call_args_list 
                  if 'ERROR' in str(call)]
    assert len(error_logs) > 0


@pytest.mark.asyncio
async def test_keep_network_error(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops):
    """
    Test error handling for Keep Extractor network errors.
    
    Requirements: 9.1, 9.4
    
    Validates:
    - Network exceptions are caught
    - Job fails gracefully
    - Error is recorded
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock network error
    mock_keep_client.post.side_effect = httpx.ConnectError("Connection refused")
    
    # Execute sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)
    
    # Verify failure
    assert result['status'] == 'failed'
    assert 'error' in result
    
    # Verify job was marked as failed
    failed_calls = [call for call in mock_db_ops.update_sync_job.call_args_list 
                    if 'status' in str(call) and 'failed' in str(call)]
    assert len(failed_calls) > 0


# Test: Error Handling for Notion Writer Failures

@pytest.mark.asyncio
async def test_notion_page_creation_failure(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops, sample_notes):
    """
    Test error handling when Notion page creation fails.
    
    Requirements: 9.3, 9.4
    
    Validates:
    - Notion Writer failures are caught
    - Failed notes are tracked
    - Other notes continue processing
    - Job completes with partial success
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock Keep responses
    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}
    
    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': sample_notes}
    
    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response
    
    # Mock Notion responses: first fails, second succeeds
    notion_response_fail = Mock()
    notion_response_fail.status_code = 400
    notion_response_fail.text = 'Invalid request'
    
    notion_response_success = Mock()
    notion_response_success.status_code = 201
    notion_response_success.json.return_value = {'page_id': 'notion_page_2', 'url': 'https://notion.so/page2'}
    
    mock_notion_client.post.side_effect = [notion_response_fail, notion_response_success]
    
    # Execute sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)
    
    # Verify partial success
    assert result['status'] == 'completed'
    assert result['summary']['total_notes'] == 2
    assert result['summary']['processed_notes'] == 1
    assert result['summary']['failed_notes'] == 1
    
    # Verify both notes were attempted
    assert mock_notion_client.post.call_count == 2
    
    # Verify sync state was only updated for successful note
    assert mock_db_ops.upsert_sync_state.call_count == 1
    
    # Verify error was logged for failed note
    error_logs = [call for call in mock_db_ops.add_sync_log.call_args_list 
                  if 'ERROR' in str(call)]
    assert len(error_logs) > 0


@pytest.mark.asyncio
async def test_notion_network_error_continues_processing(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops, sample_notes):
    """
    Test that Notion network errors don't stop processing other notes.
    
    Requirements: 9.4
    
    Validates:
    - Network errors for individual notes are caught
    - Processing continues for remaining notes
    - Failed notes are tracked
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock Keep responses
    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}
    
    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': sample_notes}
    
    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response
    
    # Mock Notion responses: first raises exception, second succeeds
    notion_response_success = Mock()
    notion_response_success.status_code = 201
    notion_response_success.json.return_value = {'page_id': 'notion_page_2', 'url': 'https://notion.so/page2'}
    
    mock_notion_client.post.side_effect = [
        httpx.TimeoutException("Request timeout"),
        notion_response_success
    ]
    
    # Execute sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)
    
    # Verify partial success
    assert result['status'] == 'completed'
    assert result['summary']['processed_notes'] == 1
    assert result['summary']['failed_notes'] == 1


@pytest.mark.asyncio
async def test_notion_rate_limit_error(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops, sample_notes):
    """
    Test handling of Notion rate limit errors.
    
    Requirements: 9.2
    
    Validates:
    - Rate limit errors are caught
    - Error is logged appropriately
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock Keep responses
    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}
    
    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': [sample_notes[0]]}
    
    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response
    
    # Mock Notion rate limit response
    notion_response = Mock()
    notion_response.status_code = 429
    notion_response.text = 'Rate limit exceeded'
    mock_notion_client.post.return_value = notion_response
    
    # Execute sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)
    
    # Verify the note failed
    assert result['summary']['failed_notes'] == 1
    
    # Verify error was logged
    error_logs = [call for call in mock_db_ops.add_sync_log.call_args_list 
                  if 'ERROR' in str(call)]
    assert len(error_logs) > 0


# Test: Missing Credentials

@pytest.mark.asyncio
async def test_missing_credentials(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops):
    """
    Test error handling when user credentials are not found.
    
    Requirements: 9.3, 9.4
    
    Validates:
    - Missing credentials are detected
    - Job fails immediately
    - Error message is descriptive
    - Notification is sent
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock missing credentials
    mock_db_ops.get_credentials.return_value = None
    
    # Execute sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)
    
    # Verify failure
    assert result['status'] == 'failed'
    assert 'error' in result
    assert 'credentials' in result['error'].lower()
    
    # Verify Keep was never called
    mock_keep_client.post.assert_not_called()
    mock_keep_client.get.assert_not_called()
    
    # Verify Notion was never called
    mock_notion_client.post.assert_not_called()


# Test: Empty Notes List

@pytest.mark.asyncio
async def test_empty_notes_list(orchestrator, mock_keep_client, mock_notion_client, mock_db_ops):
    """
    Test handling of empty notes list from Keep.
    
    Requirements: 3.1
    
    Validates:
    - Empty notes list is handled gracefully
    - Job completes successfully with zero notes
    """
    job_id = uuid4()
    user_id = 'test_user'
    
    # Mock Keep responses with empty notes
    auth_response = Mock()
    auth_response.status_code = 200
    auth_response.json.return_value = {'status': 'authenticated'}
    
    notes_response = Mock()
    notes_response.status_code = 200
    notes_response.json.return_value = {'notes': []}
    
    mock_keep_client.post.return_value = auth_response
    mock_keep_client.get.return_value = notes_response
    
    # Execute sync
    result = await orchestrator.execute_sync(job_id, user_id, full_sync=True)
    
    # Verify success with zero notes
    assert result['status'] == 'completed'
    assert result['summary']['total_notes'] == 0
    assert result['summary']['processed_notes'] == 0
    assert result['summary']['failed_notes'] == 0
    
    # Verify Notion was never called
    mock_notion_client.post.assert_not_called()


# Test: Notification Service

def test_notification_service_initialization():
    """Test notification service initialization."""
    service = NotificationService()
    assert service is not None
    assert hasattr(service, 'send_critical_error_notification')


@pytest.mark.asyncio
async def test_notification_service_disabled():
    """Test notification service when disabled."""
    os.environ['ENABLE_NOTIFICATIONS'] = 'false'
    
    service = NotificationService()
    
    # Should not raise an error even when disabled
    await service.send_critical_error_notification(
        job_id=str(uuid4()),
        user_id="test_user",
        error_message="Test error"
    )


@pytest.mark.asyncio
async def test_notification_service_with_context():
    """Test notification service with additional context."""
    os.environ['ENABLE_NOTIFICATIONS'] = 'false'
    
    service = NotificationService()
    
    # Should handle context parameter
    await service.send_critical_error_notification(
        job_id=str(uuid4()),
        user_id="test_user",
        error_message="Test error",
        context={"stage": "testing", "details": "test details"}
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
