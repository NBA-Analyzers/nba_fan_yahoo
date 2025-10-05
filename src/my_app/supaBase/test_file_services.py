# test_file_services.py
"""
Test script for FileService, VectorMetadata, and FileMetadata
Run this from the supaBase directory:
    python -m supaBase.test_file_services
"""

from .services.file_services import FileService
from .models.vector_metadata import VectorMetadata
from .models.file_metadata import FileMetadata
from .exceptions.custom_exceptions import ValidationError, NotFoundError, DuplicateError


def main():
    print("\n" + "=" * 60)
    print("TESTING FILE & VECTOR METADATA SERVICES")
    print("=" * 60 + "\n")

    # Initialize service
    file_service = FileService()

    try:
        # ========== TEST 1: Create Vector Store ==========
        print("TEST 1: Creating vector store...")
        vector_store = VectorMetadata(
            vector_store_id="vs_test_001", openai_vector_id="vs_openai_abc123"
        )
        created_vector = file_service.create_vector_store(vector_store)
        print(f"✅ Vector store created: {created_vector.vector_store_id}")
        print(f"   OpenAI ID: {created_vector.openai_vector_id}")
        print(f"   Created at: {created_vector.created_at}\n")

        # ========== TEST 2: Create File Metadata ==========
        print("TEST 2: Creating file metadata...")
        file_meta = FileMetadata(
            file_id="file_test_001",
            openai_file_id="file_openai_xyz789",
            vector_store_id="vs_test_001",
            file_name="league_data.json",
            league_id="league_12345",
            file_path_BLOB="azure://container/league_data.json",
        )
        created_file = file_service.create_file_metadata(file_meta)
        print(f"✅ File metadata created: {created_file.file_id}")
        print(f"   File name: {created_file.file_name}")
        print(f"   League ID: {created_file.league_id}")
        print(f"   Vector store: {created_file.vector_store_id}\n")

        # ========== TEST 3: Create Multiple Files for Same Vector Store ==========
        print("TEST 3: Creating another file for the same vector store...")
        file_meta2 = FileMetadata(
            file_id="file_test_002",
            openai_file_id="file_openai_def456",
            vector_store_id="vs_test_001",
            file_name="player_stats.csv",
            league_id="league_12345",
            file_path_BLOB="azure://container/player_stats.csv",
        )
        created_file2 = file_service.create_file_metadata(file_meta2)
        print(f"✅ Second file created: {created_file2.file_id}")
        print(f"   File name: {created_file2.file_name}\n")

        # ========== TEST 4: Get Files by Vector Store ==========
        print("TEST 4: Getting all files for vector store 'vs_test_001'...")
        files = file_service.get_files_by_vector_store("vs_test_001")
        print(f"✅ Found {len(files)} files:")
        for f in files:
            print(f"   - {f.file_name} (ID: {f.file_id})")
        print()

        # ========== TEST 5: Get Files by League ==========
        print("TEST 5: Getting all files for league 'league_12345'...")
        league_files = file_service.get_files_by_league("league_12345")
        print(f"✅ Found {len(league_files)} files for league:")
        for f in league_files:
            print(f"   - {f.file_name}")
        print()

        # ========== TEST 6: Update Vector Store Sync ==========
        print("TEST 6: Updating vector store last_synced timestamp...")
        updated_vector = file_service.update_vector_sync("vs_test_001")
        print(f"✅ Vector store synced")
        print(f"   Last synced: {updated_vector.last_synced}\n")

        # ========== TEST 7: Update File Metadata ==========
        print("TEST 7: Updating file metadata...")
        updated_file = file_service.update_file_metadata(
            "file_test_001",
            {"file_path_BLOB": "azure://new-container/updated_league_data.json"},
        )
        print(f"✅ File updated")
        print(f"   New path: {updated_file.file_path_BLOB}\n")

        # ========== TEST 8: Get All Files with Vector Info ==========
        print("TEST 8: Getting all files with vector store information...")
        enriched_files = file_service.get_all_files_with_vector_info(
            league_id="league_12345"
        )
        print(f"✅ Found {len(enriched_files)} enriched files:")
        for item in enriched_files:
            file_info = item["file"]
            vector_info = item["vector_store"]
            print(f"   - File: {file_info['file_name']}")
            print(
                f"     Vector Store: {vector_info['vector_store_id'] if vector_info else 'N/A'}"
            )
            print(
                f"     Last Synced: {vector_info['last_synced'] if vector_info else 'N/A'}"
            )
        print()

        # ========== TEST 9: Create File with Vector Store (Atomic) ==========
        print("TEST 9: Creating file with vector store atomically...")
        new_vector = VectorMetadata(
            vector_store_id="vs_test_002", openai_vector_id="vs_openai_new999"
        )
        new_file = FileMetadata(
            file_id="file_test_003",
            openai_file_id="file_openai_new888",
            vector_store_id="vs_test_002",
            file_name="team_analysis.txt",
            league_id="league_67890",
        )
        created_v, created_f = file_service.create_file_with_vector_store(
            new_vector, new_file
        )
        print(f"✅ Atomic creation successful:")
        print(f"   Vector Store: {created_v.vector_store_id}")
        print(f"   File: {created_f.file_name}\n")

        # ========== TEST 10: Error Handling - FK Violation ==========
        print("TEST 10: Testing FK violation (non-existent vector store)...")
        try:
            invalid_file = FileMetadata(
                file_id="file_invalid",
                openai_file_id="file_invalid_001",
                vector_store_id="vs_does_not_exist",
                file_name="invalid.json",
            )
            file_service.create_file_metadata(invalid_file)
            print("❌ Should have raised ValidationError!")
        except ValidationError as e:
            print(f"✅ Correctly caught FK violation: {e}\n")

        # ========== TEST 11: Error Handling - Duplicate Entry ==========
        print("TEST 11: Testing duplicate file creation...")
        try:
            duplicate_file = FileMetadata(
                file_id="file_test_001",  # Already exists
                openai_file_id="file_duplicate",
                vector_store_id="vs_test_001",
            )
            file_service.create_file_metadata(duplicate_file)
            print("❌ Should have raised DuplicateError!")
        except DuplicateError as e:
            print(f"✅ Correctly caught duplicate: {e}\n")

        # ========== TEST 12: Error Handling - Cannot Delete Vector Store with Files ==========
        print("TEST 12: Testing vector store deletion with existing files...")
        try:
            file_service.delete_vector_store("vs_test_001")
            print("❌ Should have raised ValidationError!")
        except ValidationError as e:
            print(f"✅ Correctly prevented deletion: {e}\n")

        # ========== CLEANUP ==========
        print("CLEANUP: Deleting test data...")
        file_service.delete_file_metadata("file_test_001")
        file_service.delete_file_metadata("file_test_002")
        file_service.delete_file_metadata("file_test_003")
        print("✅ Files deleted")

        file_service.delete_vector_store("vs_test_001")
        file_service.delete_vector_store("vs_test_002")
        print("✅ Vector stores deleted")

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED! ✅")
        print("=" * 60 + "\n")

    except ValidationError as e:
        print(f"❌ Validation error: {e}")
    except NotFoundError as e:
        print(f"❌ Not found error: {e}")
    except DuplicateError as e:
        print(f"❌ Duplicate error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
