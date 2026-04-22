"""Sync Service - FastAPI application."""

import logging
import sys
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, Request, status, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from sqlalchemy import text

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))
from shared.db_operations import DatabaseOperations
from shared.encryption import EncryptionService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Global instances
db_ops: Optional[DatabaseOperations] = None
encryption_service: Optional[EncryptionService] = None
keep_client: Optional[httpx.AsyncClient] = None
notion_client: Optional[httpx.AsyncClient] = None


def get_keep_extractor_url() -> str:
    """Get Keep Extractor service URL from environment."""
    return os.getenv("KEEP_EXTRACTOR_URL", "http://localhost:8003")


def get_notion_writer_url() -> str:
    """Get Notion Writer service URL from environment."""
    return os.getenv("NOTION_WRITER_URL", "http://localhost:8004")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global db_ops, encryption_service, keep_client, notion_client
    
    logger.info("Sync Service starting up...")
    
    # Initialize database operations
    db_ops = DatabaseOperations()
    logger.info("Database connection initialized")
    
    # Initialize encryption service
    encryption_service = EncryptionService()
    logger.info("Encryption service initialized")
    
    # Initialize HTTP clients for microservices
    # Increased timeout to 30 minutes for syncs with many images
    keep_client = httpx.AsyncClient(
        base_url=get_keep_extractor_url(),
        timeout=1800.0  # 30 minutes for long-running operations
    )
    notion_client = httpx.AsyncClient(
        base_url=get_notion_writer_url(),
        timeout=1800.0  # 30 minutes for long-running operations
    )
    logger.info(f"HTTP clients initialized - Keep: {get_keep_extractor_url()}, Notion: {get_notion_writer_url()}")
    
    yield
    
    # Cleanup
    await keep_client.aclose()
    await notion_client.aclose()
    logger.info("Sync Service shutting down...")


# Create FastAPI application
app = FastAPI(
    title="Sync Service",
    description="Orchestrates synchronization between Google Keep and Notion",
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
    # Check database connectivity
    db_healthy = False
    try:
        with db_ops.get_session() as session:
            session.execute(text("SELECT 1"))
        db_healthy = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
    
    # Check Keep Extractor connectivity
    keep_healthy = False
    try:
        response = await keep_client.get("/health")
        keep_healthy = response.status_code == 200
    except Exception as e:
        logger.error(f"Keep Extractor health check failed: {e}")
    
    # Check Notion Writer connectivity
    notion_healthy = False
    try:
        response = await notion_client.get("/health")
        notion_healthy = response.status_code == 200
    except Exception as e:
        logger.error(f"Notion Writer health check failed: {e}")
    
    overall_status = "healthy" if (db_healthy and keep_healthy and notion_healthy) else "degraded"
    
    return {
        "status": overall_status,
        "service": "sync_service",
        "version": "0.1.0",
        "dependencies": {
            "database": "up" if db_healthy else "down",
            "keep_extractor": "up" if keep_healthy else "down",
            "notion_writer": "up" if notion_healthy else "down"
        }
    }


@app.get("/", status_code=status.HTTP_200_OK)
async def root():
    """Root endpoint."""
    return {
        "service": "Sync Service",
        "version": "0.1.0",
        "status": "running"
    }


# Request/Response models
class SyncExecuteRequest(BaseModel):
    """Request model for sync execution."""
    user_id: str
    full_sync: bool = False
    job_id: Optional[str] = None  # Optional - will be generated if not provided
    main_database_name: Optional[str] = None


class SyncExecuteResponse(BaseModel):
    """Response model for sync execution."""
    job_id: str
    status: str
    summary: Optional[dict] = None
    error: Optional[str] = None


@app.post("/internal/sync/execute", response_model=SyncExecuteResponse, status_code=status.HTTP_200_OK)
async def execute_sync(request: SyncExecuteRequest, background_tasks: BackgroundTasks):
    """
    Execute a synchronization job asynchronously.
    
    This endpoint initiates a sync job and returns immediately with the job_id.
    The actual sync runs in the background. Use the /internal/sync/status/{job_id}
    endpoint to check progress.
    
    This endpoint orchestrates the entire sync workflow:
    1. Loads user credentials from database
    2. Queries sync state to determine notes needing sync
    3. Calls Keep Extractor to fetch notes (full or incremental)
    4. For each note, checks if it exists in Notion
    5. Calls Notion Writer to create or update pages
    6. Updates sync state after each successful write
    7. Tracks progress and handles errors gracefully
    
    Args:
        request: SyncExecuteRequest with user_id, full_sync flag, and optional job_id
        background_tasks: FastAPI background tasks
        
    Returns:
        SyncExecuteResponse with job_id and queued status (returns immediately)
    """
    from services.sync_service.orchestrator import SyncOrchestrator
    import uuid
    
    # Generate job_id if not provided
    if request.job_id:
        try:
            job_id = UUID(request.job_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid job_id format"
            )
    else:
        job_id = uuid.uuid4()
    
    logger.info(f"Received sync execute request for job {job_id}, user {request.user_id}")

    # Ensure the sync job exists for callers that hit the internal endpoint directly
    # (for example the Django admin interface). The public API gateway already creates
    # the row first, so we only insert when missing.
    existing_job = db_ops.get_sync_job(job_id)
    if not existing_job:
        db_ops.create_sync_job(
            job_id=job_id,
            user_id=request.user_id,
            full_sync=request.full_sync
        )
    
    # Create orchestrator
    orchestrator = SyncOrchestrator(
        keep_client=keep_client,
        notion_client=notion_client,
        db_ops=db_ops,
        encryption_service=encryption_service
    )
    
    # Add sync to background tasks - this returns immediately
    background_tasks.add_task(
        orchestrator.execute_sync,
        job_id=job_id,
        user_id=request.user_id,
        full_sync=request.full_sync,
        main_database_name=request.main_database_name
    )
    
    # Return immediately with job_id
    return SyncExecuteResponse(
        job_id=str(job_id),
        status="queued",
        summary={"message": "Sync job queued successfully"}
    )


class SyncStatusResponse(BaseModel):
    """Response model for sync status."""
    job_id: str
    status: str
    progress: dict
    created_at: str
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


@app.get("/internal/sync/status/{job_id}", response_model=SyncStatusResponse, status_code=status.HTTP_200_OK)
async def get_sync_status(job_id: str):
    """
    Get the status of a sync job.
    
    Queries the database for job status and progress information.
    
    Args:
        job_id: The sync job ID to query
        
    Returns:
        SyncStatusResponse with current job state
        
    Raises:
        HTTPException: If job_id is invalid or job not found
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id format"
        )
    
    logger.info(f"Querying status for job {job_id}")
    
    # Query database for job
    sync_job = db_ops.get_sync_job(job_uuid)
    
    if not sync_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sync job {job_id} not found"
        )
    
    # Build response
    return SyncStatusResponse(
        job_id=str(sync_job.job_id),
        status=sync_job.status,
        progress={
            "total_notes": sync_job.total_notes,
            "processed_notes": sync_job.processed_notes,
            "failed_notes": sync_job.failed_notes
        },
        created_at=sync_job.created_at.isoformat(),
        completed_at=sync_job.completed_at.isoformat() if sync_job.completed_at else None,
        error_message=sync_job.error_message
    )


class AbortSyncResponse(BaseModel):
    """Response model for abort sync."""
    job_id: str
    status: str
    message: str


@app.post("/internal/sync/abort/{job_id}", response_model=AbortSyncResponse, status_code=status.HTTP_200_OK)
async def abort_sync(job_id: str):
    """
    Abort a running sync job.
    
    Marks the job as 'cancelled' in the database. Note: This does not stop
    the actual sync process if it's already running, but prevents further
    processing and marks it as cancelled for the user.
    
    Args:
        job_id: The sync job ID to abort
        
    Returns:
        AbortSyncResponse with confirmation
        
    Raises:
        HTTPException: If job_id is invalid, job not found, or job cannot be aborted
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id format"
        )
    
    logger.info(f"Aborting sync job {job_id}")
    
    # Query database for job
    sync_job = db_ops.get_sync_job(job_uuid)
    
    if not sync_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sync job {job_id} not found"
        )
    
    # Check if job can be aborted
    if sync_job.status in ['completed', 'failed', 'cancelled']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot abort job with status '{sync_job.status}'"
        )
    
    # Update job status to cancelled
    db_ops.update_sync_job(
        job_uuid,
        status='cancelled',
        error_message='Job cancelled by user',
        completed_at=datetime.utcnow()
    )
    
    db_ops.add_sync_log(
        job_uuid,
        'WARNING',
        'Sync job cancelled by user'
    )
    
    logger.info(f"Sync job {job_id} has been cancelled")
    
    return AbortSyncResponse(
        job_id=job_id,
        status='cancelled',
        message='Sync job has been cancelled'
    )


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("SYNC_SERVICE_PORT", 8005))
    uvicorn.run(app, host="0.0.0.0", port=port)
