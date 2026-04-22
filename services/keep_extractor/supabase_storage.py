"""Supabase Storage client for image storage."""

import logging
from typing import Optional
from urllib.parse import quote

import requests
from requests import Response
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class SupabaseStorageClient:
    """Handles Supabase Storage operations for image storage."""

    def __init__(
        self,
        supabase_url: str,
        service_role_key: str,
        bucket_name: str,
    ):
        """
        Initialize Supabase Storage client.

        Args:
            supabase_url: Supabase project URL
            service_role_key: Supabase service role key
            bucket_name: Supabase storage bucket name
        """
        if not supabase_url:
            raise ValueError("SUPABASE_URL is required")
        if not service_role_key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is required")
        if not bucket_name:
            raise ValueError("SUPABASE_STORAGE_BUCKET is required")

        self.supabase_url = supabase_url.rstrip("/")
        self.service_role_key = service_role_key
        self.bucket_name = bucket_name
        self.object_base_url = f"{self.supabase_url}/storage/v1/object"
        self.public_base_url = f"{self.object_base_url}/public/{quote(self.bucket_name, safe='')}"
        self.headers = {
            "Authorization": f"Bearer {self.service_role_key}",
            "apikey": self.service_role_key,
        }

    async def upload_image(
        self,
        image_data: bytes,
        key: str,
        content_type: str = "image/jpeg"
    ) -> str:
        """
        Upload image to Supabase Storage and return public URL.

        Args:
            image_data: Image binary data
            key: Storage object key (path)
            content_type: MIME type of the image

        Returns:
            Public URL of uploaded image
        """
        try:
            upload_url = f"{self.object_base_url}/{quote(self.bucket_name, safe='')}/{quote(key, safe='/')}"
            response = requests.post(
                upload_url,
                data=image_data,
                headers={
                    **self.headers,
                    "Content-Type": content_type,
                    "x-upsert": "true",
                    "Cache-Control": "3600",
                },
                timeout=30,
            )
            self._raise_for_status(response)

            public_url = f"{self.public_base_url}/{quote(key, safe='/')}"
            logger.info(f"Successfully uploaded image to Supabase Storage: {public_url}")
            return public_url
        except RequestException as exc:
            logger.error(f"Failed to upload image to Supabase Storage: {exc}", exc_info=True)
            raise

    async def delete_image(self, key: str) -> bool:
        """
        Delete image from Supabase Storage.

        Args:
            key: Storage object key (path)

        Returns:
            True if successful, False otherwise
        """
        try:
            delete_url = f"{self.object_base_url}/{quote(self.bucket_name, safe='')}/{quote(key, safe='/')}"
            response = requests.delete(
                delete_url,
                headers=self.headers,
                timeout=30,
            )
            self._raise_for_status(response)
            logger.info(f"Successfully deleted image from Supabase Storage: {key}")
            return True
        except RequestException as exc:
            logger.error(f"Failed to delete image from Supabase Storage: {exc}", exc_info=True)
            return False

    def get_public_url(self, key: str) -> str:
        """Get public URL for an object key."""
        return f"{self.public_base_url}/{quote(key, safe='/')}"

    @staticmethod
    def _raise_for_status(response: Response) -> None:
        """Raise a request exception with Supabase response details when upload fails."""
        try:
            response.raise_for_status()
        except RequestException as exc:
            error_text = response.text.strip()
            if error_text:
                raise RequestException(
                    f"{exc}. Supabase response: {error_text}"
                ) from exc
            raise
