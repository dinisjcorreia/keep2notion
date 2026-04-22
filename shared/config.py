"""Shared configuration utilities."""

import os
from typing import Optional


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """Get environment variable with optional default and required validation."""
    value = os.getenv(key, default)
    if required and not value:
        raise ValueError(f"Required environment variable {key} is not set")
    return value


def get_database_url() -> str:
    """Get PostgreSQL database URL from environment."""
    return get_env(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/keep_notion_sync",
        required=False
    )


def get_supabase_storage_config() -> dict:
    """Get Supabase Storage configuration from environment."""
    return {
        "url": get_env("SUPABASE_URL", required=True),
        "service_role_key": get_env("SUPABASE_SERVICE_ROLE_KEY", required=True),
        "bucket": get_env("SUPABASE_STORAGE_BUCKET", required=True),
    }
