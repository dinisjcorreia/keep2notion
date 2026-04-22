"""Notion Writer Service - FastAPI application."""

import logging
import sys
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import shared config
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from writer import NotionWriter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def _clean_notion_id(notion_id: str) -> str:
    """
    Clean and extract a Notion page/database ID from various formats.
    
    Handles:
    - Plain UUID: 2fb86a4c5fbf806dbeb6f3f2c1b23d10
    - UUID with dashes: 2fb86a4c-5fbf-806d-beb6-f3f2c1b23d10
    - Notion URL: https://www.notion.so/2fb86a4c5fbf806dbeb6f3f2c1b23d10?v=...
    - URL with dashes: https://www.notion.so/2fb86a4c-5fbf-806d-beb6-f3f2c1b23d10
    
    Args:
        notion_id: Notion page or database ID in any format
        
    Returns:
        Clean Notion ID (32 hex characters without dashes)
        
    Raises:
        ValueError: If database ID is invalid
    """
    import re
    
    # Remove whitespace
    notion_id = notion_id.strip()
    
    # If it's a URL, extract the ID
    if notion_id.startswith('http'):
        # Support both bare IDs and common Notion slug URLs like /Title-<id>?...
        match = re.search(r'([a-f0-9]{32}|[a-f0-9-]{36})(?:\?|$)', notion_id)
        if match:
            notion_id = match.group(1)
        else:
            raise ValueError(f"Could not extract Notion ID from URL: {notion_id}")
    
    # Remove dashes if present
    notion_id = notion_id.replace('-', '')
    
    # Remove query parameters if somehow still present
    if '?' in notion_id:
        notion_id = notion_id.split('?')[0]
    
    # Validate it's a 32-character hex string
    if not re.match(r'^[a-f0-9]{32}$', notion_id):
        raise ValueError(f"Invalid Notion ID format: {notion_id}. Expected 32 hex characters.")
    
    return notion_id


def _clean_database_id(database_id: str) -> str:
    """Backward-compatible database ID cleaner."""
    return _clean_notion_id(database_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    logger.info("Notion Writer Service starting up...")
    yield
    logger.info("Notion Writer Service shutting down...")


# Create FastAPI application
app = FastAPI(
    title="Notion Writer Service",
    description="Service for writing notes and images to Notion",
    version="0.1.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Error handling middleware
@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    """Global error handling middleware."""
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "detail": str(exc)
            }
        )


# Health check endpoint
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "notion_writer",
        "version": "0.1.0"
    }


@app.get("/", status_code=status.HTTP_200_OK)
async def root():
    """Root endpoint."""
    return {
        "service": "Notion Writer Service",
        "version": "0.1.0",
        "status": "running"
    }


# Request/Response models
class ImageAttachment(BaseModel):
    """Image attachment model.

    Note: `s3_url` is a legacy field name that now stores any public image URL.
    """
    id: str
    s3_url: Optional[str] = None
    filename: str


class NoteData(BaseModel):
    """Note data model."""
    title: str
    content: str
    created_at: str
    labels: List[str] = []
    images: List[ImageAttachment] = []


class CreatePageRequest(BaseModel):
    """Request model for creating a Notion page."""
    api_token: str
    database_id: str
    note: NoteData


class CreatePageResponse(BaseModel):
    """Response model for page creation."""
    page_id: str
    url: str


class ResolveDatabaseRequest(BaseModel):
    """Request model for resolving or creating a target Notion database."""
    api_token: str
    root_reference: str
    labels: List[str] = []
    main_database_name: Optional[str] = None


class ResolveDatabaseResponse(BaseModel):
    """Response model for database resolution."""
    database_id: str
    database_name: str
    created: bool = False


class UpdatePageRequest(BaseModel):
    """Request model for updating a Notion page."""
    api_token: str
    note: NoteData


class UpdatePageResponse(BaseModel):
    """Response model for page update."""
    page_id: str
    updated: bool


@app.post("/internal/notion/pages", response_model=CreatePageResponse, status_code=status.HTTP_201_CREATED)
async def create_page(request: CreatePageRequest):
    """
    Create a new Notion page from a Google Keep note.
    
    Args:
        request: CreatePageRequest containing API token, database ID, and note data
    
    Returns:
        CreatePageResponse with page_id and url
    
    Raises:
        HTTPException: If page creation fails
    """
    try:
        # Clean and validate database ID
        database_id = _clean_database_id(request.database_id)
        
        # Initialize Notion writer
        writer = NotionWriter(request.api_token)
        
        # Convert note to dict
        note_dict = request.note.model_dump()
        
        # Create page
        result = await writer.create_page(
            database_id=database_id,
            note=note_dict
        )
        
        return CreatePageResponse(**result)
    
    except Exception as e:
        logger.error(f"Error creating Notion page: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create Notion page: {str(e)}"
        )


@app.post("/internal/notion/databases/resolve", response_model=ResolveDatabaseResponse, status_code=status.HTTP_200_OK)
async def resolve_database(request: ResolveDatabaseRequest):
    """Resolve or create the database that should receive a note."""
    try:
        writer = NotionWriter(request.api_token)
        result = await writer.resolve_target_database(
            root_reference=_clean_notion_id(request.root_reference),
            labels=request.labels,
            main_database_name=request.main_database_name
        )

        return ResolveDatabaseResponse(**result)

    except Exception as e:
        logger.error(f"Error resolving Notion database: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve Notion database: {str(e)}"
        )


@app.patch("/internal/notion/pages/{page_id}", response_model=UpdatePageResponse, status_code=status.HTTP_200_OK)
async def update_page(page_id: str, request: UpdatePageRequest):
    """
    Update an existing Notion page.
    
    Args:
        page_id: Notion page ID to update
        request: UpdatePageRequest containing API token and note data
    
    Returns:
        UpdatePageResponse with page_id and updated status
    
    Raises:
        HTTPException: If page update fails
    """
    try:
        # Initialize Notion writer
        writer = NotionWriter(request.api_token)
        
        # Convert note to dict
        note_dict = request.note.model_dump()
        
        # Update page
        result = await writer.update_page(
            page_id=page_id,
            note=note_dict
        )
        
        return UpdatePageResponse(**result)
    
    except Exception as e:
        logger.error(f"Error updating Notion page {page_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update Notion page: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("NOTION_WRITER_PORT", 8004))
    uvicorn.run(app, host="0.0.0.0", port=port)
