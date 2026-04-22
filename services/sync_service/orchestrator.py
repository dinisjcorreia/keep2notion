"""Sync orchestration logic."""

import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID
import httpx

from shared.db_operations import DatabaseOperations
from shared.encryption import EncryptionService
from services.sync_service.notifications import NotificationService

logger = logging.getLogger(__name__)


class SyncOrchestrator:
    """Orchestrates the synchronization workflow between Keep Extractor and Notion Writer."""
    
    def __init__(
        self,
        keep_client: httpx.AsyncClient,
        notion_client: httpx.AsyncClient,
        db_ops: DatabaseOperations,
        encryption_service: EncryptionService
    ):
        """
        Initialize the sync orchestrator.
        
        Args:
            keep_client: HTTP client for Keep Extractor service
            notion_client: HTTP client for Notion Writer service
            db_ops: Database operations instance
            encryption_service: Encryption service for credentials
        """
        self.keep_client = keep_client
        self.notion_client = notion_client
        self.db_ops = db_ops
        self.encryption_service = encryption_service
        self.notification_service = NotificationService()
        self.database_cache: Dict[tuple, str] = {}

    def _should_recreate_notion_page(self, response: httpx.Response) -> bool:
        """Return True when an update failure means the saved page link is stale."""
        response_text = response.text.lower()
        return any(
            marker in response_text
            for marker in (
                "archived",
                "object_not_found",
                "could not find block",
                "could not find page",
            )
        )

    async def _create_notion_page(
        self,
        notion_token: str,
        notion_database_id: str,
        note: Dict
    ) -> str:
        """Create a new Notion page for a Keep note and return its page id."""
        response = await self.notion_client.post(
            "/internal/notion/pages",
            json={
                "api_token": notion_token,
                "database_id": notion_database_id,
                "note": {
                    "title": note['title'],
                    "content": note['content'],
                    "created_at": note['created_at'],
                    "labels": note['labels'],
                    "images": note['images']
                }
            }
        )

        if response.status_code != 201:
            raise Exception(f"Failed to create Notion page: {response.text}")

        result = response.json()
        return result['page_id']

    async def _resolve_target_database_id(
        self,
        notion_token: str,
        notion_root_reference: str,
        labels: List[str],
        main_database_name: Optional[str]
    ) -> str:
        """Resolve or create the correct Notion database for the note."""
        has_labels = any(label and label.strip() for label in labels)
        if not has_labels and not (main_database_name and main_database_name.strip()):
            return notion_root_reference

        target_name = next((label.strip() for label in labels if label and label.strip()), None)
        target_name = target_name or (main_database_name.strip() if main_database_name and main_database_name.strip() else "Keep")

        cache_key = (notion_root_reference, target_name)
        cached_database_id = self.database_cache.get(cache_key)
        if cached_database_id:
            return cached_database_id

        response = await self.notion_client.post(
            "/internal/notion/databases/resolve",
            json={
                "api_token": notion_token,
                "root_reference": notion_root_reference,
                "labels": labels,
                "main_database_name": main_database_name
            }
        )

        if response.status_code != 200:
            raise Exception(f"Failed to resolve Notion database: {response.text}")

        result = response.json()
        self.database_cache[cache_key] = result["database_id"]
        return result["database_id"]
    
    async def execute_sync(
        self,
        job_id: UUID,
        user_id: str,
        full_sync: bool,
        main_database_name: Optional[str] = None
    ) -> Dict:
        """
        Execute the synchronization workflow.
        
        This is the main orchestration method that:
        1. Loads user credentials
        2. Queries sync state to determine what needs syncing
        3. Calls Keep Extractor to fetch notes
        4. For each note, checks if it exists in Notion
        5. Calls Notion Writer to create or update pages
        6. Updates sync state after each successful write
        7. Tracks progress and handles errors gracefully
        
        Args:
            job_id: Unique job identifier
            user_id: User ID to sync for
            full_sync: Whether to perform full sync or incremental
            
        Returns:
            Dictionary with sync summary
        """
        logger.info(f"Starting sync job {job_id} for user {user_id} (full_sync={full_sync})")
        
        # API Gateway and the internal sync endpoint may create the job before
        # the background task starts. Only insert when the row does not exist.
        existing_job = self.db_ops.get_sync_job(job_id)
        if not existing_job:
            self.db_ops.create_sync_job(
                job_id=job_id,
                user_id=user_id,
                full_sync=full_sync
            )
        
        # Update status to 'running' now that the job exists
        self.db_ops.update_sync_job(job_id, status='running')
        
        # Now we can add logs since the job exists
        self.db_ops.add_sync_log(job_id, 'INFO', f'Starting sync for user {user_id}')
        
        try:
            # Step 1: Load user credentials
            logger.info(f"Loading credentials for user {user_id}")
            credentials = self.db_ops.get_credentials(user_id, self.encryption_service)
            
            if not credentials:
                error_msg = f"No credentials found for user {user_id}"
                logger.error(error_msg)
                self.db_ops.update_sync_job(
                    job_id,
                    status='failed',
                    error_message=error_msg,
                    completed_at=datetime.utcnow()
                )
                self.db_ops.add_sync_log(job_id, 'ERROR', error_msg)
                
                # Send critical error notification
                await self.notification_service.send_critical_error_notification(
                    job_id=str(job_id),
                    user_id=user_id,
                    error_message=error_msg,
                    context={"stage": "credential_loading"}
                )
                
                return {
                    "job_id": str(job_id),
                    "status": "failed",
                    "error": error_msg
                }
            
            # Step 2: Determine notes to sync
            logger.info(f"Determining notes to sync (full_sync={full_sync})")
            modified_since = None
            
            if not full_sync:
                # Get the last sync time for incremental sync
                sync_state = self.db_ops.get_sync_state_by_user(user_id)
                if sync_state:
                    # Find the most recent sync time
                    last_sync_times = [record.last_synced_at for record in sync_state]
                    if last_sync_times:
                        modified_since = max(last_sync_times).isoformat()
                        logger.info(f"Incremental sync from {modified_since}")
            
            self.db_ops.add_sync_log(
                job_id,
                'INFO',
                f'Fetching notes from Keep (modified_since={modified_since})'
            )
            
            # Step 3: Call Keep Extractor to fetch notes
            logger.info(f"Calling Keep Extractor for user {user_id}")
            notes = await self._fetch_notes_from_keep(
                username=user_id,
                google_token=credentials['google_oauth_token'],
                modified_since=modified_since
            )
            
            total_notes = len(notes)
            logger.info(f"Fetched {total_notes} notes from Keep")
            
            # Update job with total notes count
            self.db_ops.update_sync_job(job_id, total_notes=total_notes)
            self.db_ops.add_sync_log(
                job_id,
                'INFO',
                f'Fetched {total_notes} notes from Keep'
            )
            
            # Step 4-6: Process each note
            processed_count = 0
            failed_count = 0
            results = []
            
            for note in notes:
                try:
                    result = await self._process_note(
                        job_id=job_id,
                        user_id=user_id,
                        note=note,
                        notion_token=credentials['notion_api_token'],
                        notion_database_id=credentials['notion_database_id'],
                        main_database_name=main_database_name
                    )
                    
                    if result['status'] == 'success':
                        processed_count += 1
                    else:
                        failed_count += 1
                    
                    results.append(result)
                    
                    # Update progress
                    self.db_ops.increment_sync_job_progress(
                        job_id,
                        processed=1 if result['status'] == 'success' else 0,
                        failed=1 if result['status'] == 'failed' else 0
                    )
                
                except Exception as e:
                    logger.error(f"Error processing note {note.get('id', 'unknown')}: {e}", exc_info=True)
                    failed_count += 1
                    results.append({
                        "note_id": note.get('id', 'unknown'),
                        "status": "failed",
                        "error": str(e)
                    })
                    
                    self.db_ops.add_sync_log(
                        job_id,
                        'ERROR',
                        f"Failed to process note {note.get('id', 'unknown')}: {str(e)}",
                        keep_note_id=note.get('id')
                    )
                    
                    self.db_ops.increment_sync_job_progress(job_id, failed=1)
            
            # Step 7: Complete the job
            logger.info(f"Sync job {job_id} completed: {processed_count} processed, {failed_count} failed")
            
            self.db_ops.update_sync_job(
                job_id,
                status='completed',
                completed_at=datetime.utcnow()
            )
            
            self.db_ops.add_sync_log(
                job_id,
                'INFO',
                f'Sync completed: {processed_count} processed, {failed_count} failed'
            )
            
            return {
                "job_id": str(job_id),
                "status": "completed",
                "summary": {
                    "total_notes": total_notes,
                    "processed_notes": processed_count,
                    "failed_notes": failed_count
                }
            }
        
        except Exception as e:
            logger.error(f"Sync job {job_id} failed with error: {e}", exc_info=True)
            
            error_msg = str(e)
            self.db_ops.update_sync_job(
                job_id,
                status='failed',
                error_message=error_msg,
                completed_at=datetime.utcnow()
            )
            
            self.db_ops.add_sync_log(job_id, 'ERROR', f'Sync failed: {error_msg}')
            
            # Send critical error notification
            await self.notification_service.send_critical_error_notification(
                job_id=str(job_id),
                user_id=user_id,
                error_message=error_msg,
                context={"stage": "sync_execution", "full_sync": full_sync}
            )
            
            return {
                "job_id": str(job_id),
                "status": "failed",
                "error": error_msg
            }
    
    async def _fetch_notes_from_keep(
        self,
        username: str,
        google_token: str,
        modified_since: Optional[str] = None
    ) -> List[Dict]:
        """
        Fetch notes from Keep Extractor service.
        
        Args:
            username: Google account username
            google_token: Google OAuth token (or master token)
            modified_since: Optional ISO datetime string for incremental sync
            
        Returns:
            List of note dictionaries
        """
        # First, authenticate with Keep
        # Use master token for authentication
        auth_response = await self.keep_client.post(
            "/internal/keep/auth",
            json={
                "username": username,
                "master_token": google_token
            }
        )
        
        if auth_response.status_code != 200:
            raise Exception(f"Keep authentication failed: {auth_response.text}")
        
        auth_data = auth_response.json()
        if auth_data.get('status') != 'authenticated':
            raise Exception(f"Keep authentication failed: {auth_data.get('error', 'Unknown error')}")
        
        # Fetch notes
        params = {
            "username": username,
            "upload_images": True  # Always upload images to external storage
        }
        
        if modified_since:
            params["modified_since"] = modified_since
        
        # Check for note limit (for testing)
        import os
        note_limit = os.getenv("SYNC_NOTE_LIMIT")
        if note_limit and note_limit.strip():
            try:
                params["limit"] = int(note_limit)
                logger.info(f"Limiting sync to {note_limit} notes (SYNC_NOTE_LIMIT env var)")
            except ValueError:
                logger.warning(f"Invalid SYNC_NOTE_LIMIT value: {note_limit}, ignoring")
        
        notes_response = await self.keep_client.get(
            "/internal/keep/notes",
            params=params
        )
        
        if notes_response.status_code != 200:
            raise Exception(f"Failed to fetch notes from Keep: {notes_response.text}")
        
        notes_data = notes_response.json()
        return notes_data.get('notes', [])
    
    async def _process_note(
        self,
        job_id: UUID,
        user_id: str,
        note: Dict,
        notion_token: str,
        notion_database_id: str,
        main_database_name: Optional[str] = None
    ) -> Dict:
        """
        Process a single note: create or update in Notion and update sync state.
        
        Args:
            job_id: Sync job ID
            user_id: User ID
            note: Note dictionary from Keep
            notion_token: Notion API token
            notion_database_id: Notion database ID
            
        Returns:
            Dictionary with processing result
        """
        note_id = note['id']
        logger.info(f"Processing note {note_id}")
        
        try:
            # Check if note exists in sync state
            existing = self.db_ops.get_sync_record(user_id, note_id)
            
            if existing:
                # Update existing page
                logger.info(f"Updating existing Notion page {existing.notion_page_id} for note {note_id}")
                
                response = await self.notion_client.patch(
                    f"/internal/notion/pages/{existing.notion_page_id}",
                    json={
                        "api_token": notion_token,
                        "note": {
                            "title": note['title'],
                            "content": note['content'],
                            "created_at": note['created_at'],
                            "labels": note['labels'],
                            "images": note['images']
                        }
                    }
                )
                
                if response.status_code != 200:
                    if self._should_recreate_notion_page(response):
                        logger.warning(
                            "Existing Notion page %s for note %s is unavailable; creating a replacement page",
                            existing.notion_page_id,
                            note_id
                        )
                        notion_page_id = await self._create_notion_page(
                            notion_token=notion_token,
                            notion_database_id=await self._resolve_target_database_id(
                                notion_token=notion_token,
                                notion_root_reference=notion_database_id,
                                labels=note['labels'],
                                main_database_name=main_database_name
                            ),
                            note=note
                        )
                    else:
                        raise Exception(f"Failed to update Notion page: {response.text}")
                else:
                    result = response.json()
                    notion_page_id = result['page_id']
            
            else:
                # Create new page
                logger.info(f"Creating new Notion page for note {note_id}")
                notion_page_id = await self._create_notion_page(
                    notion_token=notion_token,
                    notion_database_id=await self._resolve_target_database_id(
                        notion_token=notion_token,
                        notion_root_reference=notion_database_id,
                        labels=note['labels'],
                        main_database_name=main_database_name
                    ),
                    note=note
                )
            
            # Update sync state
            modified_at = datetime.fromisoformat(note['modified_at'].replace('Z', '+00:00'))
            
            self.db_ops.upsert_sync_state(
                user_id=user_id,
                keep_note_id=note_id,
                notion_page_id=notion_page_id,
                keep_modified_at=modified_at
            )
            
            logger.info(f"Successfully processed note {note_id}")
            
            self.db_ops.add_sync_log(
                job_id,
                'INFO',
                f"Successfully synced note {note_id} to Notion page {notion_page_id}",
                keep_note_id=note_id
            )
            
            return {
                "note_id": note_id,
                "status": "success",
                "notion_page_id": notion_page_id
            }
        
        except Exception as e:
            logger.error(f"Failed to process note {note_id}: {e}", exc_info=True)
            
            self.db_ops.add_sync_log(
                job_id,
                'ERROR',
                f"Failed to process note {note_id}: {str(e)}",
                keep_note_id=note_id
            )
            
            return {
                "note_id": note_id,
                "status": "failed",
                "error": str(e)
            }
