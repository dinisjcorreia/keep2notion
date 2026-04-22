"""Unit tests for Supabase Storage client."""

import asyncio
from unittest.mock import Mock, patch

import pytest
import requests

from services.keep_extractor.supabase_storage import SupabaseStorageClient


@pytest.fixture
def storage_client():
    """Create a Supabase Storage client for tests."""
    return SupabaseStorageClient(
        supabase_url="https://example.supabase.co",
        service_role_key="service-role-key",
        bucket_name="keep-images",
    )


def test_upload_image_returns_public_url(storage_client):
    """Upload should hit storage API and return public URL."""
    response = Mock()
    response.raise_for_status.return_value = None

    with patch("services.keep_extractor.supabase_storage.requests.post", return_value=response) as mock_post:
        result = asyncio.run(
            storage_client.upload_image(image_data=b"image-bytes", key="notes/test.jpg")
        )

    assert result == "https://example.supabase.co/storage/v1/object/public/keep-images/notes/test.jpg"
    mock_post.assert_called_once()
    called_url = mock_post.call_args.args[0]
    assert called_url == "https://example.supabase.co/storage/v1/object/keep-images/notes/test.jpg"
    headers = mock_post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer service-role-key"
    assert headers["apikey"] == "service-role-key"
    assert headers["x-upsert"] == "true"


def test_delete_image_calls_storage_api(storage_client):
    """Delete should call Supabase delete endpoint."""
    response = Mock()
    response.raise_for_status.return_value = None

    with patch("services.keep_extractor.supabase_storage.requests.delete", return_value=response) as mock_delete:
        result = asyncio.run(storage_client.delete_image("notes/test.jpg"))

    assert result is True
    mock_delete.assert_called_once()
    called_url = mock_delete.call_args.args[0]
    assert called_url == "https://example.supabase.co/storage/v1/object/keep-images/notes/test.jpg"


def test_upload_image_raises_request_exception_on_failure(storage_client):
    """Upload should surface Supabase response details on failure."""
    response = Mock()
    response.text = '{"message":"bucket not found"}'
    response.raise_for_status.side_effect = requests.HTTPError("400 Client Error")

    with patch("services.keep_extractor.supabase_storage.requests.post", return_value=response):
        with pytest.raises(requests.RequestException, match="bucket not found"):
            asyncio.run(storage_client.upload_image(image_data=b"image-bytes", key="notes/test.jpg"))
