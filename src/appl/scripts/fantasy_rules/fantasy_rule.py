#!/usr/bin/env python3
"""
Fantasy Rules Upload Script

This script handles uploading Yahoo Fantasy Basketball rules to OpenAI vector stores
for use with AI assistants in fantasy basketball analysis.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Add the parent directory to the path so we can import our modules
# sys.path.append(str(Path(__file__).parent.parent.parent))

from appl.fantasy_integrations import player_stats
from appl.service.openai_file_manager import OpenaiFileManager
from appl.service.vector_store_manager import VectorStoreManager
from appl.repository.supaBase.repositories.vector_metadata_repository import (
    VectorStoreMetadataRepository,
)

load_dotenv()


def setup_services() -> tuple[OpenaiFileManager, VectorStoreManager]:
    """
    Initialize the required services for file management and vector stores.

    Returns:
        Tuple of (OpenaiFileManager, VectorStoreManager)
    """
    # Load environment variables

    # Initialize OpenAI client
    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    openai_client = OpenAI(api_key=openai_api_key)

    # Initialize repositories and services
    vector_store_repo = VectorStoreMetadataRepository()
    vector_store_manager = VectorStoreManager(vector_store_repo, openai_client)
    openai_file_manager = OpenaiFileManager(vector_store_manager, openai_client)

    return openai_file_manager, vector_store_manager


def upload_rules(
    openai_file_manager: OpenaiFileManager, vector_store_manager: VectorStoreManager
) -> str:
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


def upload_player_stats(
    openai_file_manager: OpenaiFileManager, stats_path: Path, season: str
) -> str:
    """
    Upload the consolidated player stats JSON into the vector store.
    """

    try:
        script_dir = Path(__file__).parent
        pdf_path = script_dir / "Yahoo_Fantasy_Basketball_Rules_With_Comparison.pdf"

        print("📊 Uploading rules PDF + player stats JSON to rules vector store...")
        vector_store_metadata = openai_file_manager.update_player_stats(
            str(stats_path), str(pdf_path)
        )
        print("✅ Player stats successfully updated in vector store!")
        return vector_store_metadata

    except Exception as e:
        error_msg = f"❌ Error updating player stats: {str(e)}"
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

        season = "2025-26"
        print("\n♻️ Regenerating consolidated player stats JSON...")
        stats_path = player_stats.generate_consolidated_player_stats(season)

        print("\n📊 Uploading consolidated player stats JSON...")
        stats_result = upload_player_stats(openai_file_manager, stats_path, season)
        print(f"Player stats update result: {stats_result}")

        print("\n🎉 Script completed successfully!")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ Script failed with error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
