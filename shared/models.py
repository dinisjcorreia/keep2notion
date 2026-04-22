"""Shared data models for the Google Keep to Notion sync application."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class ImageAttachment:
    """Represents an image attachment from Google Keep.

    Note: `s3_url` is a legacy field name that now stores any public image URL.
    """
    id: str
    s3_url: str
    filename: str


@dataclass
class KeepNote:
    """Represents a note from Google Keep."""
    id: str
    title: str
    content: str
    created_at: datetime
    modified_at: datetime
    labels: List[str]
    images: List[ImageAttachment]


@dataclass
class SyncJobRequest:
    """Request to initiate a sync job."""
    user_id: str
    full_sync: bool


@dataclass
class SyncJobStatus:
    """Status of a sync job."""
    job_id: str
    status: str  # queued, running, completed, failed
    progress: dict
    created_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]


@dataclass
class SyncStateRecord:
    """Record of sync state for a note."""
    user_id: str
    keep_note_id: str
    notion_page_id: str
    last_synced_at: datetime
    keep_modified_at: datetime
