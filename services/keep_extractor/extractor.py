"""Note extraction logic for Google Keep."""

import logging
from datetime import datetime
from typing import List, Optional

import gkeepapi
import requests
from requests.exceptions import RequestException

from supabase_storage import SupabaseStorageClient
from retry import retry_with_exponential_backoff

logger = logging.getLogger(__name__)


class NoteExtractor:
    """Extracts notes from Google Keep."""

    def __init__(self, keep_client: gkeepapi.Keep, storage_client: Optional[SupabaseStorageClient] = None):
        """
        Initialize the note extractor.
        
        Args:
            keep_client: Authenticated gkeepapi.Keep client
            storage_client: Optional storage client for image uploads
        """
        self.keep_client = keep_client
        self.storage_client = storage_client
    
    async def extract_notes(
        self, 
        modified_since: Optional[datetime] = None, 
        upload_images: bool = False,
        limit: Optional[int] = None
    ) -> List[dict]:
        """
        Extract notes from Google Keep.
        
        Args:
            modified_since: Optional datetime to filter notes modified after this time
            upload_images: Whether to download and upload images to external storage
            limit: Optional limit on number of notes to extract (applied early to avoid processing all images)
            
        Returns:
            List of note dictionaries with extracted data
        """
        try:
            # Get all notes from Keep
            all_notes = self.keep_client.all()
            
            extracted_notes = []
            notes_to_process = []
            
            # First pass: filter notes without processing images
            for note in all_notes:
                # Skip archived and trashed notes
                if note.archived or note.trashed:
                    continue
                
                # Filter by modification time if specified
                if modified_since:
                    note_modified = note.timestamps.updated
                    if note_modified < modified_since:
                        continue
                
                notes_to_process.append(note)
                
                # Apply limit early to avoid processing unnecessary images
                if limit and len(notes_to_process) >= limit:
                    logger.info(f"Reached note limit of {limit}, stopping extraction")
                    break
            
            # Second pass: extract data from filtered notes
            note_counter = 1
            for note in notes_to_process:
                note_data = await self._extract_note_data(note, upload_images, note_counter)
                extracted_notes.append(note_data)
                note_counter += 1
            
            logger.info(f"Extracted {len(extracted_notes)} notes from Google Keep")
            return extracted_notes
        
        except Exception as e:
            logger.error(f"Error extracting notes: {e}", exc_info=True)
            raise
    
    async def _extract_note_data(self, note: gkeepapi.node.TopLevelNode, upload_images: bool = False, note_number: int = 1) -> dict:
        """
        Extract data from a single Keep note.
        
        Args:
            note: gkeepapi note object
            upload_images: Whether to download and upload images to external storage
            note_number: Serial number for untitled notes
            
        Returns:
            Dictionary with note data
        """
        # Extract title - use serial number if empty
        title = note.title if hasattr(note, 'title') and note.title else ""
        if not title or title.strip() == "":
            title = f"Note #{note_number}"
        
        # Extract content/text
        content = note.text if hasattr(note, 'text') else ""
        
        # Extract timestamps
        created_at = note.timestamps.created if hasattr(note.timestamps, 'created') else datetime.now()
        modified_at = note.timestamps.updated if hasattr(note.timestamps, 'updated') else datetime.now()
        
        # Extract labels
        labels = []
        if hasattr(note, 'labels'):
            labels = [label.name for label in note.labels.all()]
        
        # Extract and upload images
        images = []
        if hasattr(note, 'blobs') and upload_images and self.storage_client:
            images = await self._process_images(note)
        elif hasattr(note, 'blobs'):
            # Just extract image metadata without uploading
            for blob in note.blobs:
                images.append({
                    "id": blob.blob_id if hasattr(blob, 'blob_id') else str(id(blob)),
                    "filename": blob.text if hasattr(blob, 'text') and blob.text else f"image_{blob.blob_id}.jpg",
                    "s3_url": None
                })
        
        return {
            "id": note.id,
            "title": title,
            "content": content,
            "created_at": created_at,
            "modified_at": modified_at,
            "labels": labels,
            "images": images
        }
    
    async def _process_images(self, note: gkeepapi.node.TopLevelNode) -> List[dict]:
        """
        Download images from Keep and upload to Supabase Storage.
        
        Args:
            note: gkeepapi note object
            
        Returns:
            List of image metadata with public URLs
        """
        import uuid
        images = []
        
        for blob in note.blobs:
            try:
                blob_id = blob.blob_id if hasattr(blob, 'blob_id') else str(id(blob))
                filename = blob.text if hasattr(blob, 'text') and blob.text else f"image_{blob_id}.jpg"
                
                # Download image from Keep with retry logic
                logger.info(f"Downloading image {blob_id} from Keep")
                image_data = await self._download_image_with_retry(blob)
                
                # Generate a simple unique filename to avoid folder nesting
                # Use UUID to ensure uniqueness and avoid special characters
                unique_id = str(uuid.uuid4())
                storage_key = f"keep-images/{unique_id}.jpg"

                storage_url = await self._upload_to_storage_with_retry(
                    image_data=image_data,
                    key=storage_key
                )
                
                images.append({
                    "id": blob_id,
                    "filename": filename,
                    # Keep legacy field name for compatibility with downstream services.
                    "s3_url": storage_url
                })
                
                logger.info(f"Successfully uploaded image {blob_id} to storage: {storage_url}")
            
            except Exception as e:
                logger.error(f"Failed to process image {blob_id} after retries: {e}", exc_info=True)
                # Continue processing other images
                images.append({
                    "id": blob_id,
                    "filename": filename,
                    "s3_url": None,
                    "error": str(e)
                })
        
        return images
    
    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1.0,
        exponential_base=2.0,
        exceptions=(RequestException, ConnectionError, TimeoutError)
    )
    async def _download_image_with_retry(self, blob) -> bytes:
        """
        Download image from Keep with retry logic.
        
        Args:
            blob: gkeepapi blob object
            
        Returns:
            Image binary data
        """
        image_url = self.keep_client.getMediaLink(blob)
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        return response.content
    
    @retry_with_exponential_backoff(
        max_retries=3,
        initial_delay=1.0,
        exponential_base=2.0,
        exceptions=(Exception,)
    )
    async def _upload_to_storage_with_retry(self, image_data: bytes, key: str) -> str:
        """
        Upload image to external storage with retry logic.
        
        Args:
            image_data: Image binary data
            key: Storage object key
            
        Returns:
            Public URL
        """
        return await self.storage_client.upload_image(
            image_data=image_data,
            key=key,
            content_type="image/jpeg"
        )
