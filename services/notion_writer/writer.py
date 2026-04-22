"""Notion Writer - handles page creation and updates in Notion."""

import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from notion_client import Client
from notion_client.errors import APIResponseError

# Handle both relative and absolute imports
try:
    from .rate_limit import handle_rate_limit
except ImportError:
    from rate_limit import handle_rate_limit

logger = logging.getLogger(__name__)


class NotionWriter:
    """Handles writing notes to Notion databases."""

    MAX_BLOCKS_PER_REQUEST = 100
    
    def __init__(self, api_token: str):
        """
        Initialize Notion Writer.
        
        Args:
            api_token: Notion API integration token
        """
        self.client = Client(auth=api_token)
        self.api_token = api_token

    @handle_rate_limit(max_retries=3)
    async def resolve_target_database(
        self,
        root_reference: str,
        labels: List[str],
        main_database_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve or create the database that should receive this note."""
        target_database_name = self._select_database_name(labels, main_database_name)
        root_context = self._resolve_root_reference(root_reference)

        if (
            root_context.get("database_id")
            and self._normalize_name(root_context.get("database_name")) == self._normalize_name(target_database_name)
        ):
            return {
                "database_id": root_context["database_id"],
                "database_name": root_context["database_name"],
                "created": False
            }

        parent_page_id = root_context.get("parent_page_id")
        if not parent_page_id:
            raise ValueError(
                "Notion root reference must be a page or a database inside a page "
                "to auto-create tag databases."
            )

        existing_database = self._find_database_under_parent(parent_page_id, target_database_name)
        if existing_database:
            return {
                "database_id": existing_database["id"],
                "database_name": existing_database["title"],
                "created": False
            }

        created_database = self._create_database_under_parent(parent_page_id, target_database_name)
        return {
            "database_id": created_database["id"],
            "database_name": created_database["title"],
            "created": True
        }
    
    @handle_rate_limit(max_retries=3)
    async def create_page(
        self,
        database_id: str,
        note: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Create a new Notion page from a Google Keep note.
        
        Args:
            database_id: Notion database ID where the page will be created
            note: Dictionary containing note data with keys:
                - title: str
                - content: str
                - created_at: str (ISO format)
                - labels: List[str]
                - images: List[Dict] with keys: s3_url, filename
                  (`s3_url` is a legacy field name for any public image URL)
        
        Returns:
            Dictionary with page_id and url
        
        Raises:
            APIResponseError: If Notion API request fails
        """
        try:
            # Get database schema to find the title property name
            database = self.client.databases.retrieve(database_id=database_id)
            title_property_name = None
            
            # Find the title property
            for prop_name, prop_config in database.get("properties", {}).items():
                if prop_config.get("type") == "title":
                    title_property_name = prop_name
                    break
            
            if not title_property_name:
                # Fallback to "Name" if no title property found (shouldn't happen)
                title_property_name = "Name"
                logger.warning(f"No title property found in database, using default: {title_property_name}")
            
            # Prepare page properties using the correct title property name
            properties = self._build_page_properties(note, title_property_name)
            
            # Prepare page content blocks
            children = self._build_content_blocks(note)
            
            initial_children = children[:self.MAX_BLOCKS_PER_REQUEST]

            # Create page in Notion
            logger.info(f"Creating Notion page for note: {note.get('title', 'Untitled')}")
            response = self.client.pages.create(
                parent={"database_id": database_id},
                properties=properties,
                children=initial_children
            )
            
            page_id = response["id"]
            page_url = response["url"]

            # Notion allows at most 100 child blocks per request.
            remaining_children = children[self.MAX_BLOCKS_PER_REQUEST:]
            self._append_blocks_in_chunks(page_id, remaining_children)
            
            logger.info(f"Successfully created Notion page: {page_id}")
            
            return {
                "page_id": page_id,
                "url": page_url
            }
        
        except APIResponseError as e:
            logger.error(f"Notion API error creating page: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating page: {e}", exc_info=True)
            raise
    
    @handle_rate_limit(max_retries=3)
    async def update_page(
        self,
        page_id: str,
        note: Dict[str, Any]
    ) -> Dict[str, bool]:
        """
        Update an existing Notion page.
        
        Args:
            page_id: Notion page ID to update
            note: Dictionary containing note data (same format as create_page)
        
        Returns:
            Dictionary with page_id and updated status
        
        Raises:
            APIResponseError: If Notion API request fails
        """
        try:
            # Update page properties
            properties = self._build_page_properties(note)
            
            logger.info(f"Updating Notion page: {page_id}")
            self.client.pages.update(
                page_id=page_id,
                properties=properties
            )
            
            # Append new content blocks
            children = self._build_content_blocks(note)
            if children:
                self._append_blocks_in_chunks(page_id, children)
            
            logger.info(f"Successfully updated Notion page: {page_id}")
            
            return {
                "page_id": page_id,
                "updated": True
            }
        
        except APIResponseError as e:
            logger.error(f"Notion API error updating page: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error updating page: {e}", exc_info=True)
            raise
    
    def _build_page_properties(self, note: Dict[str, Any], title_property_name: str = "Name") -> Dict[str, Any]:
        """
        Build Notion page properties from note data.
        
        Args:
            note: Note dictionary
            title_property_name: Name of the title property in the database
        
        Returns:
            Dictionary of Notion page properties
        """
        properties = {}
        
        # Title property - use the database's actual title property name
        title = note.get("title", "Untitled")
        properties[title_property_name] = {
            "title": [
                {
                    "type": "text",
                    "text": {"content": title}
                }
            ]
        }
        
        # Don't add other properties - they may not exist in the database
        # Users can add them manually in Notion if needed
        
        return properties
    
    def _build_content_blocks(self, note: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Build Notion content blocks from note data.
        
        Args:
            note: Note dictionary
        
        Returns:
            List of Notion block objects
        """
        blocks = []

        # Add images first so Keep attachments appear above note text in Notion.
        images = note.get("images", [])
        for image in images:
            s3_url = image.get("s3_url")
            if s3_url:
                blocks.append({
                    "object": "block",
                    "type": "image",
                    "image": {
                        "type": "external",
                        "external": {"url": s3_url}
                    }
                })

        # Add text content as paragraph blocks after images.
        content = note.get("content", "")
        if content:
            paragraphs = content.split("\n")
            for paragraph in paragraphs:
                if paragraph.strip():  # Skip empty lines
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {"content": paragraph}
                                }
                            ]
                        }
                    })
        
        return blocks

    def _append_blocks_in_chunks(self, block_id: str, children: List[Dict[str, Any]]) -> None:
        """Append child blocks in Notion-safe batches."""
        for index in range(0, len(children), self.MAX_BLOCKS_PER_REQUEST):
            chunk = children[index:index + self.MAX_BLOCKS_PER_REQUEST]
            self.client.blocks.children.append(
                block_id=block_id,
                children=chunk
            )

    def _select_database_name(self, labels: List[str], main_database_name: Optional[str]) -> str:
        """Pick first matching Keep tag or the configured main database name."""
        for label in labels or []:
            if label and label.strip():
                return label.strip()

        if main_database_name and main_database_name.strip():
            return main_database_name.strip()

        return "Keep"

    def _resolve_root_reference(self, root_reference: str) -> Dict[str, Optional[str]]:
        """Resolve a page or database reference into a parent page context."""
        notion_id = self._clean_notion_id(root_reference)

        try:
            database = self.client.databases.retrieve(database_id=notion_id)
            database_name = self._extract_title_text(database.get("title", [])) or "Keep"
            parent = database.get("parent", {})
            return {
                "database_id": notion_id,
                "database_name": database_name,
                "parent_page_id": parent.get("page_id") if parent.get("type") == "page_id" else None,
            }
        except APIResponseError as exc:
            if not self._should_fallback_to_page_lookup(exc):
                raise

        try:
            self.client.pages.retrieve(page_id=notion_id)
            return {
                "database_id": None,
                "database_name": None,
                "parent_page_id": notion_id,
            }
        except APIResponseError as exc:
            logger.error("Failed to resolve Notion root reference %s: %s", root_reference, exc)
            raise

    def _find_database_under_parent(self, parent_page_id: str, database_name: str) -> Optional[Dict[str, str]]:
        """Find an existing database with the given name under the parent page."""
        next_cursor = None

        while True:
            search_kwargs = {
                "query": database_name,
                "filter": {"property": "object", "value": "database"}
            }
            if next_cursor:
                search_kwargs["start_cursor"] = next_cursor

            response = self.client.search(**search_kwargs)
            for result in response.get("results", []):
                parent = result.get("parent", {})
                title = self._extract_title_text(result.get("title", []))
                if (
                    parent.get("type") == "page_id"
                    and parent.get("page_id") == parent_page_id
                    and self._normalize_name(title) == self._normalize_name(database_name)
                ):
                    return {
                        "id": result["id"],
                        "title": title or database_name,
                    }

            if not response.get("has_more"):
                return None

            next_cursor = response.get("next_cursor")

    def _create_database_under_parent(self, parent_page_id: str, database_name: str) -> Dict[str, str]:
        """Create a new Notion database under the target parent page."""
        response = self.client.databases.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[
                {
                    "type": "text",
                    "text": {"content": database_name}
                }
            ],
            properties={
                "Name": {"title": {}}
            }
        )

        return {
            "id": response["id"],
            "title": self._extract_title_text(response.get("title", [])) or database_name,
        }

    def _clean_notion_id(self, notion_reference: str) -> str:
        """Extract a raw Notion ID from plain ids or Notion URLs."""
        notion_reference = notion_reference.strip()

        if notion_reference.startswith("http"):
            match = re.search(r'([a-f0-9]{32}|[a-f0-9-]{36})(?:\?|$)', notion_reference)
            if match:
                notion_reference = match.group(1)

        notion_reference = notion_reference.replace("-", "")
        if "?" in notion_reference:
            notion_reference = notion_reference.split("?")[0]

        if not re.match(r'^[a-f0-9]{32}$', notion_reference):
            raise ValueError(
                f"Invalid Notion reference format: {notion_reference}. Expected 32 hex characters."
            )

        return notion_reference

    def _extract_title_text(self, title_data: List[Dict[str, Any]]) -> str:
        """Flatten Notion title rich text into plain text."""
        return "".join(
            item.get("plain_text", "") or item.get("text", {}).get("content", "")
            for item in title_data
        ).strip()

    def _normalize_name(self, value: Optional[str]) -> str:
        """Normalize database names for matching."""
        return (value or "").strip().casefold()

    def _is_not_found_error(self, exc: APIResponseError) -> bool:
        """Return True when the API error is a not-found lookup."""
        return (
            getattr(exc, "code", None) == "object_not_found"
            or "could not find" in str(exc).lower()
        )

    def _is_page_not_database_error(self, exc: APIResponseError) -> bool:
        """Return True when Notion says given ID is a page, not a database."""
        message = str(exc).lower()
        return "is a page, not a database" in message

    def _should_fallback_to_page_lookup(self, exc: APIResponseError) -> bool:
        """Return True when database lookup should retry as page lookup."""
        return self._is_not_found_error(exc) or self._is_page_not_database_error(exc)
