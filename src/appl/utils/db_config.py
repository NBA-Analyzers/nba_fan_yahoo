# utils/db_config.py
"""
Database configuration for agent services.
Handles import path resolution for accessing supaBase services.
"""

import sys
import os
from datetime import datetime

# Add parent directory to path to import supaBase
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # agent directory
grandparent_dir = os.path.dirname(parent_dir)  # appl directory

if grandparent_dir not in sys.path:
    sys.path.insert(0, grandparent_dir)

# Now we can import from supaBase
from repository.supaBase.services.file_services import FileService
from repository.supaBase.models.file_metadata import FileMetadata as DBFileMetadata
from repository.supaBase.models.vector_metadata import VectorMetadata as DBVectorMetadata
from repository.supaBase.exceptions.custom_exceptions import (
    ValidationError,
    NotFoundError,
    DuplicateError,
)


def get_file_service() -> FileService:
    """Get FileService instance for database operations"""
    return FileService()
