"""Unit tests for Notion Writer service."""

import sys
import os
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from notion_client.errors import APIResponseError

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import with absolute imports to avoid relative import issues
import writer
from writer import NotionWriter


class TestNotionWriter:
    """Tests for NotionWriter class."""

    @pytest.fixture
    def mock_notion_client(self):
        """Create a mock Notion client."""
        mock_client = Mock()
        mock_client.pages = Mock()
        mock_client.blocks = Mock()
        mock_client.databases = Mock()
        mock_client.databases.retrieve.return_value = {
            "properties": {
                "Name": {"type": "title"}
            }
        }
        return mock_client

    @pytest.fixture
    def writer(self, mock_notion_client):
        """Create a NotionWriter instance with mocked client."""
        with patch('writer.Client', return_value=mock_notion_client):
            writer = NotionWriter(api_token="test_token")
            writer.client = mock_notion_client
            return writer

    @pytest.mark.asyncio
    async def test_create_page_basic_note(self, writer, mock_notion_client):
        """Test creating a page with basic note (no images, no labels)."""
        # Setup mock response
        mock_notion_client.pages.create.return_value = {
            "id": "page123",
            "url": "https://notion.so/page123"
        }

        # Create note data
        note = {
            "title": "Test Note",
            "content": "This is test content",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        # Call create_page
        result = await writer.create_page(
            database_id="db123",
            note=note
        )

        # Verify result
        assert result["page_id"] == "page123"
        assert result["url"] == "https://notion.so/page123"

        # Verify Notion API was called correctly
        mock_notion_client.pages.create.assert_called_once()
        call_args = mock_notion_client.pages.create.call_args

        # Check parent
        assert call_args.kwargs["parent"]["database_id"] == "db123"

        # Check properties
        properties = call_args.kwargs["properties"]
        assert properties["Name"]["title"][0]["text"]["content"] == "Test Note"
        assert properties["Created"]["date"]["start"] == "2024-01-01T10:00:00"

        # Check content blocks
        children = call_args.kwargs["children"]
        assert len(children) == 1
        assert children[0]["type"] == "paragraph"
        assert children[0]["paragraph"]["rich_text"][0]["text"]["content"] == "This is test content"

    @pytest.mark.asyncio
    async def test_create_page_with_labels(self, writer, mock_notion_client):
        """Test creating a page with labels."""
        mock_notion_client.pages.create.return_value = {
            "id": "page456",
            "url": "https://notion.so/page456"
        }

        note = {
            "title": "Note with Labels",
            "content": "Content",
            "created_at": "2024-01-01T10:00:00",
            "labels": ["work", "important", "urgent"],
            "images": []
        }

        result = await writer.create_page(database_id="db123", note=note)

        assert result["page_id"] == "page456"

        # Verify labels were added
        call_args = mock_notion_client.pages.create.call_args
        properties = call_args.kwargs["properties"]
        tags = properties["Tags"]["multi_select"]
        assert len(tags) == 3
        assert tags[0]["name"] == "work"
        assert tags[1]["name"] == "important"
        assert tags[2]["name"] == "urgent"

    @pytest.mark.asyncio
    async def test_create_page_with_images(self, writer, mock_notion_client):
        """Test creating a page with images."""
        mock_notion_client.pages.create.return_value = {
            "id": "page789",
            "url": "https://notion.so/page789"
        }

        note = {
            "title": "Note with Images",
            "content": "Check out these images",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": [
                {
                    "id": "img1",
                    "s3_url": "https://s3.amazonaws.com/bucket/img1.jpg",
                    "filename": "img1.jpg"
                },
                {
                    "id": "img2",
                    "s3_url": "https://s3.amazonaws.com/bucket/img2.png",
                    "filename": "img2.png"
                }
            ]
        }

        result = await writer.create_page(database_id="db123", note=note)

        assert result["page_id"] == "page789"

        # Verify images were added as blocks
        call_args = mock_notion_client.pages.create.call_args
        children = call_args.kwargs["children"]
        
        # Should have 1 paragraph + 2 images = 3 blocks
        assert len(children) == 3

        # Check image blocks first
        assert children[0]["type"] == "image"
        assert children[0]["image"]["external"]["url"] == "https://s3.amazonaws.com/bucket/img1.jpg"

        assert children[1]["type"] == "image"
        assert children[1]["image"]["external"]["url"] == "https://s3.amazonaws.com/bucket/img2.png"

        # Text now comes after images
        assert children[2]["type"] == "paragraph"

    @pytest.mark.asyncio
    async def test_create_page_chunks_children_over_100(self, writer, mock_notion_client):
        """Test page creation splits large child block payloads into safe chunks."""
        mock_notion_client.pages.create.return_value = {
            "id": "page_big",
            "url": "https://notion.so/page_big"
        }
        mock_notion_client.blocks.children.append.return_value = {}

        lines = [f"Line {i}" for i in range(105)]
        note = {
            "title": "Big Note",
            "content": "\n".join(lines),
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        result = await writer.create_page(database_id="db123", note=note)

        assert result["page_id"] == "page_big"
        create_children = mock_notion_client.pages.create.call_args.kwargs["children"]
        assert len(create_children) == 100

        mock_notion_client.blocks.children.append.assert_called_once()
        append_children = mock_notion_client.blocks.children.append.call_args.kwargs["children"]
        assert len(append_children) == 5

    @pytest.mark.asyncio
    async def test_create_page_multiline_content(self, writer, mock_notion_client):
        """Test creating a page with multi-line content."""
        mock_notion_client.pages.create.return_value = {
            "id": "page999",
            "url": "https://notion.so/page999"
        }

        note = {
            "title": "Multi-line Note",
            "content": "Line 1\nLine 2\nLine 3",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        result = await writer.create_page(database_id="db123", note=note)

        # Verify multiple paragraph blocks were created
        call_args = mock_notion_client.pages.create.call_args
        children = call_args.kwargs["children"]
        
        assert len(children) == 3
        assert children[0]["paragraph"]["rich_text"][0]["text"]["content"] == "Line 1"
        assert children[1]["paragraph"]["rich_text"][0]["text"]["content"] == "Line 2"
        assert children[2]["paragraph"]["rich_text"][0]["text"]["content"] == "Line 3"

    @pytest.mark.asyncio
    async def test_create_page_empty_content(self, writer, mock_notion_client):
        """Test creating a page with empty content."""
        mock_notion_client.pages.create.return_value = {
            "id": "page111",
            "url": "https://notion.so/page111"
        }

        note = {
            "title": "Empty Note",
            "content": "",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        result = await writer.create_page(database_id="db123", note=note)

        # Verify no content blocks were created
        call_args = mock_notion_client.pages.create.call_args
        children = call_args.kwargs["children"]
        assert len(children) == 0

    @pytest.mark.asyncio
    async def test_create_page_datetime_object(self, writer, mock_notion_client):
        """Test creating a page with datetime object instead of string."""
        mock_notion_client.pages.create.return_value = {
            "id": "page222",
            "url": "https://notion.so/page222"
        }

        created_at = datetime(2024, 1, 1, 10, 0, 0)
        note = {
            "title": "DateTime Note",
            "content": "Content",
            "created_at": created_at,
            "labels": [],
            "images": []
        }

        result = await writer.create_page(database_id="db123", note=note)

        # Verify datetime was converted to ISO format
        call_args = mock_notion_client.pages.create.call_args
        properties = call_args.kwargs["properties"]
        assert properties["Created"]["date"]["start"] == created_at.isoformat()

    @pytest.mark.asyncio
    async def test_create_page_api_error(self, writer, mock_notion_client):
        """Test handling API error during page creation."""
        # Setup mock to raise APIResponseError
        error = APIResponseError(
            response=Mock(status_code=400),
            message="Invalid request",
            code="validation_error"
        )
        mock_notion_client.pages.create.side_effect = error

        note = {
            "title": "Test Note",
            "content": "Content",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        # Verify error is raised
        with pytest.raises(APIResponseError):
            await writer.create_page(database_id="db123", note=note)

    @pytest.mark.asyncio
    async def test_update_page_basic(self, writer, mock_notion_client):
        """Test updating a page with basic note."""
        mock_notion_client.pages.update.return_value = {"id": "page123"}
        mock_notion_client.blocks.children.append.return_value = {}

        note = {
            "title": "Updated Title",
            "content": "Updated content",
            "created_at": "2024-01-01T10:00:00",
            "labels": ["updated"],
            "images": []
        }

        result = await writer.update_page(page_id="page123", note=note)

        assert result["page_id"] == "page123"
        assert result["updated"] is True

        # Verify pages.update was called
        mock_notion_client.pages.update.assert_called_once()
        update_args = mock_notion_client.pages.update.call_args
        assert update_args.kwargs["page_id"] == "page123"
        
        properties = update_args.kwargs["properties"]
        assert properties["Name"]["title"][0]["text"]["content"] == "Updated Title"
        assert properties["Tags"]["multi_select"][0]["name"] == "updated"

        # Verify blocks.children.append was called
        mock_notion_client.blocks.children.append.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_page_with_images(self, writer, mock_notion_client):
        """Test updating a page with images."""
        mock_notion_client.pages.update.return_value = {"id": "page456"}
        mock_notion_client.blocks.children.append.return_value = {}

        note = {
            "title": "Updated Note",
            "content": "New content",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": [
                {
                    "id": "img1",
                    "s3_url": "https://s3.amazonaws.com/bucket/new_img.jpg",
                    "filename": "new_img.jpg"
                }
            ]
        }

        result = await writer.update_page(page_id="page456", note=note)

        assert result["updated"] is True

        # Verify blocks were appended
        append_args = mock_notion_client.blocks.children.append.call_args
        children = append_args.kwargs["children"]
        
        # Should have 1 paragraph + 1 image
        assert len(children) == 2
        assert children[0]["type"] == "image"
        assert children[1]["type"] == "paragraph"

    @pytest.mark.asyncio
    async def test_update_page_chunks_children_over_100(self, writer, mock_notion_client):
        """Test page updates append large payloads in multiple requests."""
        mock_notion_client.pages.update.return_value = {"id": "page_chunked"}
        mock_notion_client.blocks.children.append.return_value = {}

        lines = [f"Line {i}" for i in range(205)]
        note = {
            "title": "Updated Big Note",
            "content": "\n".join(lines),
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        result = await writer.update_page(page_id="page_chunked", note=note)

        assert result["updated"] is True
        assert mock_notion_client.blocks.children.append.call_count == 3
        append_calls = mock_notion_client.blocks.children.append.call_args_list
        assert len(append_calls[0].kwargs["children"]) == 100
        assert len(append_calls[1].kwargs["children"]) == 100
        assert len(append_calls[2].kwargs["children"]) == 5

    @pytest.mark.asyncio
    async def test_update_page_empty_content(self, writer, mock_notion_client):
        """Test updating a page with empty content."""
        mock_notion_client.pages.update.return_value = {"id": "page789"}

        note = {
            "title": "Updated Title Only",
            "content": "",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        result = await writer.update_page(page_id="page789", note=note)

        assert result["updated"] is True

        # Verify pages.update was called
        mock_notion_client.pages.update.assert_called_once()

        # Verify blocks.children.append was NOT called (no content)
        mock_notion_client.blocks.children.append.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_page_api_error(self, writer, mock_notion_client):
        """Test handling API error during page update."""
        error = APIResponseError(
            response=Mock(status_code=404),
            message="Page not found",
            code="object_not_found"
        )
        mock_notion_client.pages.update.side_effect = error

        note = {
            "title": "Test",
            "content": "Content",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        with pytest.raises(APIResponseError):
            await writer.update_page(page_id="invalid_page", note=note)


class TestNotionWriterRateLimit:
    """Tests for rate limit handling in NotionWriter."""

    @pytest.fixture
    def mock_notion_client(self):
        """Create a mock Notion client."""
        mock_client = Mock()
        mock_client.pages = Mock()
        mock_client.blocks = Mock()
        mock_client.databases = Mock()
        mock_client.databases.retrieve.return_value = {
            "properties": {
                "Name": {"type": "title"}
            }
        }
        return mock_client

    @pytest.fixture
    def writer(self, mock_notion_client):
        """Create a NotionWriter instance with mocked client."""
        with patch('writer.Client', return_value=mock_notion_client):
            writer = NotionWriter(api_token="test_token")
            writer.client = mock_notion_client
            return writer

    @pytest.mark.asyncio
    async def test_rate_limit_retry_success(self, writer, mock_notion_client):
        """Test successful retry after rate limit."""
        # First call raises rate limit error, second succeeds
        rate_limit_error = APIResponseError(
            response=Mock(
                status_code=429,
                headers={'Retry-After': '1'},
                json=lambda: {}
            ),
            message="Rate limited",
            code="rate_limited"
        )
        
        mock_notion_client.pages.create.side_effect = [
            rate_limit_error,
            {
                "id": "page123",
                "url": "https://notion.so/page123"
            }
        ]

        note = {
            "title": "Test Note",
            "content": "Content",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        with patch('time.sleep'):  # Mock sleep to speed up test
            result = await writer.create_page(database_id="db123", note=note)

        assert result["page_id"] == "page123"
        assert mock_notion_client.pages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_max_retries_exceeded(self, writer, mock_notion_client):
        """Test failure after exceeding max retries."""
        rate_limit_error = APIResponseError(
            response=Mock(
                status_code=429,
                headers={'Retry-After': '1'},
                json=lambda: {}
            ),
            message="Rate limited",
            code="rate_limited"
        )
        
        # Always raise rate limit error
        mock_notion_client.pages.create.side_effect = rate_limit_error

        note = {
            "title": "Test Note",
            "content": "Content",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        with patch('time.sleep'):  # Mock sleep to speed up test
            with pytest.raises(APIResponseError):
                await writer.create_page(database_id="db123", note=note)

        # Should have tried 4 times (initial + 3 retries)
        assert mock_notion_client.pages.create.call_count == 4

    @pytest.mark.asyncio
    async def test_rate_limit_update_page(self, writer, mock_notion_client):
        """Test rate limit handling during page update."""
        rate_limit_error = APIResponseError(
            response=Mock(
                status_code=429,
                headers={'Retry-After': '1'},
                json=lambda: {}
            ),
            message="Rate limited",
            code="rate_limited"
        )
        
        mock_notion_client.pages.update.side_effect = [
            rate_limit_error,
            {"id": "page123"}
        ]
        mock_notion_client.blocks.children.append.return_value = {}

        note = {
            "title": "Updated",
            "content": "Content",
            "created_at": "2024-01-01T10:00:00",
            "labels": [],
            "images": []
        }

        with patch('time.sleep'):
            result = await writer.update_page(page_id="page123", note=note)

        assert result["updated"] is True
        assert mock_notion_client.pages.update.call_count == 2


class TestBuildPageProperties:
    """Tests for _build_page_properties method."""

    def test_build_properties_minimal(self):
        """Test building properties with minimal note data."""
        writer = NotionWriter(api_token="test_token")
        
        note = {
            "title": "Test",
            "content": "Content",
            "labels": [],
            "images": []
        }
        
        properties = writer._build_page_properties(note)
        
        assert "Name" in properties
        assert properties["Name"]["title"][0]["text"]["content"] == "Test"
        assert "Tags" not in properties  # No labels
        assert "Created" not in properties  # No created_at

    def test_build_properties_with_all_fields(self):
        """Test building properties with all fields."""
        writer = NotionWriter(api_token="test_token")
        
        note = {
            "title": "Complete Note",
            "content": "Content",
            "created_at": "2024-01-01T10:00:00",
            "labels": ["tag1", "tag2"],
            "images": []
        }
        
        properties = writer._build_page_properties(note)
        
        assert properties["Name"]["title"][0]["text"]["content"] == "Complete Note"
        assert len(properties["Tags"]["multi_select"]) == 2
        assert properties["Tags"]["multi_select"][0]["name"] == "tag1"
        assert properties["Created"]["date"]["start"] == "2024-01-01T10:00:00"

    def test_build_properties_untitled(self):
        """Test building properties with missing title."""
        writer = NotionWriter(api_token="test_token")
        
        note = {
            "content": "Content",
            "labels": [],
            "images": []
        }
        
        properties = writer._build_page_properties(note)
        
        assert properties["Name"]["title"][0]["text"]["content"] == "Untitled"


class TestBuildContentBlocks:
    """Tests for _build_content_blocks method."""

    def test_build_blocks_single_paragraph(self):
        """Test building blocks with single paragraph."""
        writer = NotionWriter(api_token="test_token")
        
        note = {
            "title": "Test",
            "content": "Single paragraph",
            "labels": [],
            "images": []
        }
        
        blocks = writer._build_content_blocks(note)
        
        assert len(blocks) == 1
        assert blocks[0]["type"] == "paragraph"
        assert blocks[0]["paragraph"]["rich_text"][0]["text"]["content"] == "Single paragraph"

    def test_build_blocks_multiple_paragraphs(self):
        """Test building blocks with multiple paragraphs."""
        writer = NotionWriter(api_token="test_token")
        
        note = {
            "title": "Test",
            "content": "Para 1\nPara 2\nPara 3",
            "labels": [],
            "images": []
        }
        
        blocks = writer._build_content_blocks(note)
        
        assert len(blocks) == 3
        assert blocks[0]["paragraph"]["rich_text"][0]["text"]["content"] == "Para 1"
        assert blocks[1]["paragraph"]["rich_text"][0]["text"]["content"] == "Para 2"
        assert blocks[2]["paragraph"]["rich_text"][0]["text"]["content"] == "Para 3"

    def test_build_blocks_empty_lines_skipped(self):
        """Test that empty lines are skipped."""
        writer = NotionWriter(api_token="test_token")
        
        note = {
            "title": "Test",
            "content": "Para 1\n\nPara 2\n\n\nPara 3",
            "labels": [],
            "images": []
        }
        
        blocks = writer._build_content_blocks(note)
        
        assert len(blocks) == 3  # Empty lines should be skipped

    def test_build_blocks_with_images(self):
        """Test building blocks with images."""
        writer = NotionWriter(api_token="test_token")
        
        note = {
            "title": "Test",
            "content": "Text content",
            "labels": [],
            "images": [
                {"id": "img1", "s3_url": "https://s3.aws.com/img1.jpg", "filename": "img1.jpg"},
                {"id": "img2", "s3_url": "https://s3.aws.com/img2.jpg", "filename": "img2.jpg"}
            ]
        }
        
        blocks = writer._build_content_blocks(note)
        
        assert len(blocks) == 3  # 1 paragraph + 2 images
        assert blocks[0]["type"] == "image"
        assert blocks[0]["image"]["external"]["url"] == "https://s3.aws.com/img1.jpg"
        assert blocks[1]["type"] == "image"
        assert blocks[1]["image"]["external"]["url"] == "https://s3.aws.com/img2.jpg"
        assert blocks[2]["type"] == "paragraph"

    def test_build_blocks_empty_content(self):
        """Test building blocks with empty content."""
        writer = NotionWriter(api_token="test_token")
        
        note = {
            "title": "Test",
            "content": "",
            "labels": [],
            "images": []
        }
        
        blocks = writer._build_content_blocks(note)
        
        assert len(blocks) == 0

    def test_build_blocks_only_images(self):
        """Test building blocks with only images, no text."""
        writer = NotionWriter(api_token="test_token")
        
        note = {
            "title": "Test",
            "content": "",
            "labels": [],
            "images": [
                {"id": "img1", "s3_url": "https://s3.aws.com/img1.jpg", "filename": "img1.jpg"}
            ]
        }
        
        blocks = writer._build_content_blocks(note)
        
        assert len(blocks) == 1
        assert blocks[0]["type"] == "image"

    def test_build_blocks_skips_images_without_url(self):
        """Test images without public URLs are ignored."""
        writer = NotionWriter(api_token="test_token")

        note = {
            "title": "Test",
            "content": "Text content",
            "labels": [],
            "images": [
                {"id": "img1", "s3_url": None, "filename": "img1.jpg"},
                {"id": "img2", "s3_url": "https://s3.aws.com/img2.jpg", "filename": "img2.jpg"}
            ]
        }

        blocks = writer._build_content_blocks(note)

        assert len(blocks) == 2
        assert blocks[0]["type"] == "image"
        assert blocks[0]["image"]["external"]["url"] == "https://s3.aws.com/img2.jpg"
        assert blocks[1]["type"] == "paragraph"


class TestResolveTargetDatabase:
    """Tests for tag-aware database resolution."""

    @pytest.fixture
    def mock_notion_client(self):
        """Create a mock Notion client."""
        mock_client = Mock()
        mock_client.pages = Mock()
        mock_client.blocks = Mock()
        mock_client.databases = Mock()
        mock_client.search = Mock()
        return mock_client

    @pytest.fixture
    def writer(self, mock_notion_client):
        """Create a NotionWriter instance with mocked client."""
        with patch('writer.Client', return_value=mock_notion_client):
            notion_writer = NotionWriter(api_token="test_token")
            notion_writer.client = mock_notion_client
            return notion_writer

    @pytest.mark.asyncio
    async def test_resolve_target_database_reuses_existing_main_database(self, writer, mock_notion_client):
        """Test root database is reused when its title matches the main database name."""
        main_db_id = "1234567890abcdef1234567890abcdef"
        parent_page_id = "abcdef1234567890abcdef1234567890"
        mock_notion_client.databases.retrieve.return_value = {
            "id": main_db_id,
            "title": [{"plain_text": "Keep"}],
            "parent": {"type": "page_id", "page_id": parent_page_id}
        }

        result = await writer.resolve_target_database(
            root_reference=main_db_id,
            labels=[],
            main_database_name="Keep"
        )

        assert result["database_id"] == main_db_id
        assert result["created"] is False
        mock_notion_client.search.assert_not_called()
        mock_notion_client.databases.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_target_database_finds_existing_tag_database(self, writer, mock_notion_client):
        """Test first tag reuses an existing database under the same parent page."""
        main_db_id = "1234567890abcdef1234567890abcdef"
        parent_page_id = "abcdef1234567890abcdef1234567890"
        work_db_id = "fedcba0987654321fedcba0987654321"
        mock_notion_client.databases.retrieve.return_value = {
            "id": main_db_id,
            "title": [{"plain_text": "Keep"}],
            "parent": {"type": "page_id", "page_id": parent_page_id}
        }
        mock_notion_client.search.return_value = {
            "results": [
                {
                    "id": work_db_id,
                    "title": [{"plain_text": "work"}],
                    "parent": {"type": "page_id", "page_id": parent_page_id}
                }
            ],
            "has_more": False,
            "next_cursor": None
        }

        result = await writer.resolve_target_database(
            root_reference=main_db_id,
            labels=["work", "ideas"],
            main_database_name="Keep"
        )

        assert result["database_id"] == work_db_id
        assert result["database_name"] == "work"
        assert result["created"] is False
        mock_notion_client.databases.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_target_database_creates_missing_database_under_page(self, writer, mock_notion_client):
        """Test missing tag database is created under the configured parent page."""
        page_root_id = "abcdef1234567890abcdef1234567890"
        new_db_id = "fedcba0987654321fedcba0987654321"
        mock_notion_client.databases.retrieve.side_effect = APIResponseError(
            response=Mock(status_code=404),
            message="Database not found",
            code="object_not_found"
        )
        mock_notion_client.pages.retrieve.return_value = {
            "id": page_root_id,
            "object": "page"
        }
        mock_notion_client.search.return_value = {
            "results": [],
            "has_more": False,
            "next_cursor": None
        }
        mock_notion_client.databases.create.return_value = {
            "id": new_db_id,
            "title": [{"plain_text": "work"}]
        }

        result = await writer.resolve_target_database(
            root_reference=page_root_id,
            labels=["work"],
            main_database_name="Keep"
        )

        assert result["database_id"] == new_db_id
        assert result["database_name"] == "work"
        assert result["created"] is True
        mock_notion_client.databases.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_target_database_treats_page_not_database_error_as_page_root(self, writer, mock_notion_client):
        """Test page root still works when Notion returns validation error instead of object_not_found."""
        page_root_id = "34a39cb1c2ac80fb81efd00697b44032"
        new_db_id = "fedcba0987654321fedcba0987654321"
        mock_notion_client.databases.retrieve.side_effect = APIResponseError(
            response=Mock(status_code=400),
            message=(
                f"Provided ID {page_root_id[:8]}-{page_root_id[8:12]}-{page_root_id[12:16]}-"
                f"{page_root_id[16:20]}-{page_root_id[20:]} is a page, not a database. "
                "Use the retrieve page API instead"
            ),
            code="validation_error"
        )
        mock_notion_client.pages.retrieve.return_value = {
            "id": page_root_id,
            "object": "page"
        }
        mock_notion_client.search.return_value = {
            "results": [],
            "has_more": False,
            "next_cursor": None
        }
        mock_notion_client.databases.create.return_value = {
            "id": new_db_id,
            "title": [{"plain_text": "Keep"}]
        }

        result = await writer.resolve_target_database(
            root_reference=page_root_id,
            labels=[],
            main_database_name="Keep"
        )

        assert result["database_id"] == new_db_id
        assert result["database_name"] == "Keep"
        assert result["created"] is True
