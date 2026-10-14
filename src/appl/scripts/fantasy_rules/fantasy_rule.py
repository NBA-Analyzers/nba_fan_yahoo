#!/usr/bin/env python3
"""
Fantasy Rules Upload Script

This script handles uploading Yahoo Fantasy Basketball rules into the retrieval index (Firestore vectors)
for use with AI assistants in fantasy basketball analysis.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add the parent directory to the path so we can import our modules
# sys.path.append(str(Path(__file__).parent.parent.parent))

from appl.scripts.player_stats import player_stats
from appl.config.dependencies import build_retrieval_service
from appl.ai.document_indexer import DocumentIndexer

load_dotenv()


def setup_services() -> DocumentIndexer:
    """Build the document indexer (needs EMBEDDING_MODEL's provider key, e.g. GEMINI_API_KEY,
    and Google credentials / GOOGLE_CLOUD_PROJECT for Firestore)."""
    return DocumentIndexer(build_retrieval_service())


def upload_rules(document_indexer: DocumentIndexer) -> str:
    """
    Update the fantasy rules in the vector store.

    Args:
        document_indexer: The document indexer instance

    Returns:
        String indicating success/failure
    """
    try:
        print("📋 Loading Yahoo Fantasy Basketball rules from PDF...")
        script_dir = Path(__file__).parent
        pdf_path = script_dir / "Yahoo_Fantasy_Basketball_Rules_With_Comparison.pdf"

        vector_store_metadata = document_indexer.update_rules(pdf_path)
        print("✅ Rules successfully updated in vector store!")
        return vector_store_metadata

    except Exception as e:
        error_msg = f"❌ Error updating rules: {str(e)}"
        print(error_msg)
        return error_msg


def upload_general(
    document_indexer: DocumentIndexer, stats_path: Path, season: str
) -> str:
    """
    Upload the consolidated player stats JSON into the vector store.
    """

    try:
        script_dir = Path(__file__).parent
        pdf_path = script_dir / "Yahoo_Fantasy_Basketball_Rules_With_Comparison.pdf"
        
        # Path to schedule file: ../../../data/schedule/NBA_schedule.json
        # script_dir = src/appl/scripts/fantasy_rules
        # script_dir.parent = src/appl/scripts
        # script_dir.parent.parent = src/appl
        schedule_path = script_dir.parent.parent / "data" / "schedule" / "NBA_schedule.json"

        print("📊 Uploading rules PDF + player stats JSON + schedule JSON to rules vector store...")
        vector_store_metadata = document_indexer.update_player_stats(
            str(stats_path), str(pdf_path), str(schedule_path)
        )
        print("✅ Player stats and schedule successfully updated in vector store!")
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
        document_indexer = setup_services()
        print("✅ Services initialized successfully")

        # Update rules + Player Stats
        season = "2025-26"
        print("\n♻️ Regenerating consolidated player stats JSON...")
        stats_path = player_stats.generate_consolidated_player_stats(season)

        print("\n📊 Uploading consolidated player stats JSON...")
        stats_result = upload_general(document_indexer, stats_path, season)
        print(f"Player stats update result: {stats_result}")

        print("\n🎉 Script completed successfully!")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ Script failed with error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
