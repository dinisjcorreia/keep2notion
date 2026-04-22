"""API Gateway - FastAPI application."""

import logging
import sys
import os
from contextlib import asynccontextmanager
from typing import Optional
from uuid import uuid4, UUID
from datetime import datetime

from fastapi import FastAPI, Request, status, HTTPException, Header, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx

# Add shared module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))
from shared.db_operations import DatabaseOperations

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

# Global instances
db_ops: Optional[DatabaseOperations] = None
sync_client: Optional[httpx.AsyncClient] = None


def get_sync_service_url() -> str:
    """Get Sync Service URL from environment."""
    return os.getenv("SYNC_SERVICE_URL", "http://localhost:8005")


def get_api_keys() -> set:
    """
    Get valid API keys from environment.
    
    In production, this should be replaced with a proper authentication system
    (e.g., OAuth 2.0, JWT tokens, database-backed API keys).
    
    For now, we support a comma-separated list of API keys in the API_KEYS environment variable.
    If not set, we use a default key for development.
    """
    api_keys_str = os.getenv("API_KEYS", "dev-api-key-12345")
    return set(key.strip() for key in api_keys_str.split(",") if key.strip())


# Load valid API keys at startup
VALID_API_KEYS = get_api_keys()


async def verify_api_key(x_api_key: Optional[str] = Header(None, description="API key for authentication")):
    """
    Verify API key from request header.
    
    This dependency validates that the request includes a valid API key in the X-API-Key header.
    
    Args:
        x_api_key: API key from X-API-Key header
        
    Raises:
        HTTPException: 401 if API key is missing or invalid
        
    Returns:
        str: The validated API key
    """
    if not x_api_key:
        logger.warning("Request missing API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Please provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    if x_api_key not in VALID_API_KEYS:
        logger.warning(f"Invalid API key attempted: {x_api_key[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    return x_api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global db_ops, sync_client
    
    logger.info("API Gateway starting up...")
    
    # Initialize database operations
    db_ops = DatabaseOperations()
    logger.info("Database connection initialized")
    
    # Initialize HTTP client for Sync Service
    sync_client = httpx.AsyncClient(
        base_url=get_sync_service_url(),
        timeout=300.0  # 5 minutes for long-running operations
    )
    logger.info(f"HTTP client initialized - Sync Service: {get_sync_service_url()}")
    
    yield
    
    # Cleanup
    await sync_client.aclose()
    logger.info("API Gateway shutting down...")


# Create FastAPI application
app = FastAPI(
    title="API Gateway",
    description="REST API for Google Keep to Notion Sync",
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
    """
    Global error handling middleware.
    
    This middleware catches all unhandled exceptions and returns appropriate
    HTTP status codes with descriptive error messages.
    
    Error codes:
    - 400: Bad Request (validation errors, invalid input)
    - 401: Unauthorized (missing or invalid authentication)
    - 404: Not Found (resource doesn't exist)
    - 500: Internal Server Error (unexpected errors)
    - 502: Bad Gateway (upstream service errors)
    - 503: Service Unavailable (service is down)
    - 504: Gateway Timeout (upstream service timeout)
    """
    try:
        response = await call_next(request)
        return response
    except HTTPException:
        # Re-raise HTTPExceptions to be handled by FastAPI
        raise
    except ValueError as exc:
        # Validation errors
        logger.warning(f"Validation error: {exc}")
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Bad Request",
                "detail": str(exc),
                "type": "validation_error"
            }
        )
    except Exception as exc:
        # Unexpected errors
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal Server Error",
                "detail": "An unexpected error occurred. Please try again later.",
                "type": "internal_error"
            }
        )


# Health check endpoint
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "api_gateway",
        "version": "0.1.0"
    }


class HealthCheckResponse(BaseModel):
    """Response model for health check."""
    status: str = Field(..., description="Overall health status (healthy or degraded)")
    services: dict = Field(..., description="Status of individual services")


@app.get("/api/v1/health", response_model=HealthCheckResponse, status_code=status.HTTP_200_OK)
async def api_health_check():
    """
    Health check endpoint for API Gateway.
    
    This endpoint:
    1. Checks connectivity to the Sync Service
    2. Checks connectivity to the database
    3. Returns overall status (healthy if all services are up, degraded otherwise)
    
    Returns:
        HealthCheckResponse with overall status and individual service statuses
    """
    logger.info("Health check requested")
    
    services_status = {
        "sync_service": "down",
        "database": "down"
    }
    
    # Check Sync Service connectivity
    try:
        response = await sync_client.get("/health", timeout=5.0)
        if response.status_code == 200:
            services_status["sync_service"] = "up"
            logger.debug("Sync Service is up")
        else:
            logger.warning(f"Sync Service returned non-200 status: {response.status_code}")
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning(f"Sync Service health check failed: {e}")
    
    # Check database connectivity
    try:
        # Try a simple database operation to verify connectivity
        db_ops.get_sync_jobs(limit=1, offset=0)
        services_status["database"] = "up"
        logger.debug("Database is up")
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
    
    # Determine overall status
    overall_status = "healthy" if all(s == "up" for s in services_status.values()) else "degraded"
    
    logger.info(f"Health check completed - status: {overall_status}, services: {services_status}")
    
    return HealthCheckResponse(
        status=overall_status,
        services=services_status
    )


@app.get("/", status_code=status.HTTP_200_OK)
async def root():
    """Root endpoint."""
    return {
        "service": "API Gateway",
        "version": "0.1.0",
        "status": "running"
    }


# Request/Response models for sync endpoints
class SyncStartRequest(BaseModel):
    """Request model for starting a sync job."""
    user_id: str = Field(..., description="User ID to sync notes for")
    full_sync: bool = Field(default=False, description="True for full sync, False for incremental")
    main_database_name: Optional[str] = Field(default=None, description="Fallback Notion database name for notes without tags")


class SyncStartResponse(BaseModel):
    """Response model for sync start."""
    job_id: str = Field(..., description="Unique job ID for tracking")
    status: str = Field(..., description="Initial job status (queued or running)")
    created_at: str = Field(..., description="ISO timestamp when job was created")


class SyncProgressInfo(BaseModel):
    """Progress information for a sync job."""
    total_notes: int = Field(..., description="Total number of notes to sync")
    processed_notes: int = Field(..., description="Number of notes processed successfully")
    failed_notes: int = Field(..., description="Number of notes that failed to sync")


class SyncStatusResponse(BaseModel):
    """Response model for sync status."""
    job_id: str = Field(..., description="Unique job ID")
    status: str = Field(..., description="Current job status (queued, running, completed, failed)")
    progress: SyncProgressInfo = Field(..., description="Detailed progress information")
    created_at: str = Field(..., description="ISO timestamp when job was created")
    completed_at: Optional[str] = Field(None, description="ISO timestamp when job completed (if finished)")
    error_message: Optional[str] = Field(None, description="Error message if job failed")


@app.post("/api/v1/sync/start", response_model=SyncStartResponse, status_code=status.HTTP_201_CREATED)
async def start_sync(request: SyncStartRequest, api_key: str = Depends(verify_api_key)):
    """
    Initiate a synchronization job.
    
    This endpoint:
    1. Validates authentication (requires X-API-Key header)
    2. Validates the request body (user_id, full_sync)
    3. Creates a new sync job in the database
    4. Forwards the request to the Sync Service
    5. Returns the job_id and initial status
    
    Args:
        request: SyncStartRequest with user_id and full_sync flag
        api_key: Validated API key from header (injected by dependency)
        
    Returns:
        SyncStartResponse with job_id, status, and created_at timestamp
        
    Raises:
        HTTPException: 
            - 400: Invalid request (empty user_id)
            - 401: Missing or invalid API key
            - 500: Database error
            - 502: Sync Service error
            - 503: Sync Service unavailable
    """
    logger.info(f"Received sync start request for user {request.user_id}, full_sync={request.full_sync}")
    
    # Validate user_id is not empty
    if not request.user_id or not request.user_id.strip():
        logger.warning("Sync start request with empty user_id")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_id is required and cannot be empty"
        )
    
    # Generate job ID
    job_id = uuid4()
    created_at = datetime.utcnow()
    
    # Create sync job in database
    try:
        sync_job = db_ops.create_sync_job(
            job_id=job_id,
            user_id=request.user_id,
            full_sync=request.full_sync
        )
        logger.info(f"Created sync job {job_id} for user {request.user_id}")
    except Exception as e:
        logger.error(f"Failed to create sync job: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create sync job in database: {str(e)}"
        )
    
    # Forward request to Sync Service
    try:
        response = await sync_client.post(
            "/internal/sync/execute",
            json={
                "job_id": str(job_id),
                "user_id": request.user_id,
                "full_sync": request.full_sync,
                "main_database_name": request.main_database_name
            },
            timeout=5.0  # Short timeout for initial request
        )
        
        if response.status_code != 200:
            logger.error(f"Sync Service returned error: {response.status_code} - {response.text}")
            # Update job status to failed
            db_ops.update_sync_job(
                job_id=job_id,
                status="failed",
                error_message=f"Sync Service error: {response.text}"
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Sync Service returned error (status {response.status_code}). Please try again later."
            )
        
        logger.info(f"Successfully forwarded sync request to Sync Service for job {job_id}")
        
    except httpx.TimeoutException:
        # Timeout is acceptable - sync is running in background
        logger.info(f"Sync Service request timed out (expected for long-running sync) - job {job_id}")
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to Sync Service: {e}", exc_info=True)
        # Update job status to failed
        db_ops.update_sync_job(
            job_id=job_id,
            status="failed",
            error_message=f"Failed to connect to Sync Service: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sync Service is currently unavailable. Please try again later."
        )
    
    # Return response with job details
    return SyncStartResponse(
        job_id=str(job_id),
        status=sync_job.status,
        created_at=created_at.isoformat()
    )


@app.get("/api/v1/sync/jobs/{job_id}", response_model=SyncStatusResponse, status_code=status.HTTP_200_OK)
async def get_sync_job_status(job_id: str, api_key: str = Depends(verify_api_key)):
    """
    Get the status of a sync job.
    
    This endpoint:
    1. Validates authentication (requires X-API-Key header)
    2. Validates the job_id format
    3. Queries the Sync Service for current job status
    4. Returns detailed progress information including:
       - Current status (queued, running, completed, failed)
       - Progress metrics (total, processed, failed notes)
       - Timestamps (created, completed)
       - Error message if failed
    
    Args:
        job_id: The sync job ID to query (UUID format)
        api_key: Validated API key from header (injected by dependency)
        
    Returns:
        SyncStatusResponse with current job state and progress
        
    Raises:
        HTTPException:
            - 400: Invalid job_id format
            - 401: Missing or invalid API key
            - 404: Job not found
            - 502: Sync Service error
            - 503: Sync Service unavailable
            - 504: Sync Service timeout
    """
    logger.info(f"Received status request for job {job_id}")
    
    # Validate job_id format
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        logger.warning(f"Invalid job_id format: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid job_id format: '{job_id}'. Must be a valid UUID (e.g., '123e4567-e89b-12d3-a456-426614174000')."
        )
    
    # Query Sync Service for job status
    try:
        response = await sync_client.get(
            f"/internal/sync/status/{job_id}",
            timeout=10.0
        )
        
        if response.status_code == 404:
            logger.warning(f"Sync job {job_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sync job '{job_id}' not found. Please verify the job_id is correct."
            )
        
        if response.status_code != 200:
            logger.error(f"Sync Service returned error: {response.status_code} - {response.text}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Sync Service returned error (status {response.status_code}). Please try again later."
            )
        
        # Parse response from Sync Service
        sync_data = response.json()
        
        logger.info(f"Successfully retrieved status for job {job_id}: {sync_data['status']}")
        
        # Return formatted response
        return SyncStatusResponse(
            job_id=sync_data["job_id"],
            status=sync_data["status"],
            progress=SyncProgressInfo(
                total_notes=sync_data["progress"]["total_notes"],
                processed_notes=sync_data["progress"]["processed_notes"],
                failed_notes=sync_data["progress"]["failed_notes"]
            ),
            created_at=sync_data["created_at"],
            completed_at=sync_data.get("completed_at"),
            error_message=sync_data.get("error_message")
        )
        
    except httpx.TimeoutException:
        logger.error(f"Timeout querying Sync Service for job {job_id}")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Request to Sync Service timed out. Please try again."
        )
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to Sync Service: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Sync Service is currently unavailable. Please try again later."
        )


class SyncJobSummary(BaseModel):
    """Summary model for a sync job in history."""
    job_id: str = Field(..., description="Unique job ID")
    user_id: str = Field(..., description="User ID who initiated the sync")
    status: str = Field(..., description="Job status (queued, running, completed, failed)")
    full_sync: bool = Field(..., description="Whether this was a full sync")
    total_notes: int = Field(..., description="Total number of notes")
    processed_notes: int = Field(..., description="Number of notes processed")
    failed_notes: int = Field(..., description="Number of notes that failed")
    created_at: str = Field(..., description="ISO timestamp when job was created")
    completed_at: Optional[str] = Field(None, description="ISO timestamp when job completed")
    error_message: Optional[str] = Field(None, description="Error message if job failed")


class SyncHistoryResponse(BaseModel):
    """Response model for sync history."""
    jobs: list[SyncJobSummary] = Field(..., description="List of sync jobs")
    total: int = Field(..., description="Total number of jobs matching the filter")
    limit: int = Field(..., description="Maximum number of jobs returned")
    offset: int = Field(..., description="Number of jobs skipped")


@app.get("/api/v1/sync/history", response_model=SyncHistoryResponse, status_code=status.HTTP_200_OK)
async def get_sync_history(
    user_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    api_key: str = Depends(verify_api_key)
):
    """
    Get sync job history with pagination.
    
    This endpoint:
    1. Validates authentication (requires X-API-Key header)
    2. Queries the database for sync jobs with optional user filtering
    3. Supports pagination with limit and offset parameters
    4. Returns a list of sync jobs with summary information
    5. Includes total count for pagination
    
    Args:
        user_id: Optional user ID to filter jobs (if not provided, returns all jobs)
        limit: Maximum number of jobs to return (default: 50, max: 100)
        offset: Number of jobs to skip for pagination (default: 0)
        api_key: Validated API key from header (injected by dependency)
        
    Returns:
        SyncHistoryResponse with list of jobs, total count, limit, and offset
        
    Raises:
        HTTPException:
            - 400: Invalid pagination parameters
            - 401: Missing or invalid API key
            - 500: Database error
    """
    logger.info(f"Received sync history request - user_id={user_id}, limit={limit}, offset={offset}")
    
    # Validate pagination parameters
    if limit < 1 or limit > 100:
        logger.warning(f"Invalid limit parameter: {limit}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid limit: {limit}. Must be between 1 and 100."
        )
    
    if offset < 0:
        logger.warning(f"Invalid offset parameter: {offset}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid offset: {offset}. Must be non-negative (>= 0)."
        )
    
    # Query database for sync jobs
    try:
        jobs, total_count = db_ops.get_sync_jobs(
            user_id=user_id,
            limit=limit,
            offset=offset
        )
        
        logger.info(f"Retrieved {len(jobs)} sync jobs (total: {total_count})")
        
        # Convert to response model
        job_summaries = []
        for job in jobs:
            job_summaries.append(SyncJobSummary(
                job_id=str(job.job_id),
                user_id=job.user_id,
                status=job.status,
                full_sync=job.full_sync,
                total_notes=job.total_notes,
                processed_notes=job.processed_notes,
                failed_notes=job.failed_notes,
                created_at=job.created_at.isoformat(),
                completed_at=job.completed_at.isoformat() if job.completed_at else None,
                error_message=job.error_message
            ))
        
        return SyncHistoryResponse(
            jobs=job_summaries,
            total=total_count,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Failed to retrieve sync history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve sync history from database. Please try again later."
        )


if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("API_GATEWAY_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
