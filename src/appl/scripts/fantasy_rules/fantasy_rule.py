#!/usr/bin/env python3
"""
Fantasy Rules Upload Script

This script handles uploading Yahoo Fantasy Basketball rules to OpenAI vector stores
for use with AI assistants in fantasy basketball analysis.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any
from openai import OpenAI
from dotenv import load_dotenv

# Add the parent directory to the path so we can import our modules
# sys.path.append(str(Path(__file__).parent.parent.parent))

from appl.service.openai_file_manager import OpenaiFileManager
from appl.service.vector_store_manager import VectorStoreManager
from appl.repository.supaBase.repositories.vector_metadata_repository import VectorStoreMetadataRepository

load_dotenv()

def setup_services() -> tuple[OpenaiFileManager, VectorStoreManager]:
    """
    Initialize the required services for file management and vector stores.
    
    Returns:
        Tuple of (OpenaiFileManager, VectorStoreManager)
    """
    # Load environment variables
    
    # Initialize OpenAI client
    openai_api_key = os.getenv('OPENAI_API_KEY')
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    openai_client = OpenAI(api_key=openai_api_key)
    
    # Initialize repositories and services
    vector_store_repo = VectorStoreMetadataRepository()
    vector_store_manager = VectorStoreManager(vector_store_repo, openai_client)
    openai_file_manager = OpenaiFileManager(vector_store_manager, openai_client)
    
    return openai_file_manager, vector_store_manager


def upload_rules(openai_file_manager: OpenaiFileManager, vector_store_manager: VectorStoreManager) -> str:
    """
    Update the fantasy rules in the vector store.
    
    Args:
        openai_file_manager: The file manager instance
        
    Returns:
        String indicating success/failure
    """
    try:
        print("📋 Loading Yahoo Fantasy Basketball rules from PDF...")
        script_dir = Path(__file__).parent
        pdf_path = script_dir / "Yahoo_Fantasy_Basketball_Rules_With_Comparison.pdf"

        vector_store_metadata = openai_file_manager.update_rules(pdf_path)
        # openai_file.id
        print("✅ Rules successfully updated in vector store!")
        return vector_store_metadata
        
    except Exception as e:
        error_msg = f"❌ Error updating rules: {str(e)}"
        print(error_msg)
        return error_msg




def main():
    """
    Main function to run the fantasy rules upload script.
    """
    print("🚀 Starting Fantasy Rules Upload Script")
    print("=" * 50)
    
    try:
        # Setup services
        print("🔧 Setting up services...")
        openai_file_manager, vector_store_manager = setup_services()
        print("✅ Services initialized successfully")
        
        
        # Update rules
        print("\n📋 Uploading Fantasy Rules from PDF...")
        rules_result = upload_rules(openai_file_manager, vector_store_manager)
        print(f"Rules update result: {rules_result}")
        
        print("\n🎉 Script completed successfully!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Script failed with error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()