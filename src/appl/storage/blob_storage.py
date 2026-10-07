import hashlib
import json
import logging
import os
import random
import time
from typing import Any, Callable, Optional, Protocol

logger = logging.getLogger(__name__)


class BlobStorage(Protocol):
    def upload_json_with_retries(
        self, data: Any, blob_name: str, max_retries: int = 4
    ) -> bool: ...


class NullBlobStorage:
    """No archive copy of the synced league data (the AI index is the source of truth)."""

    def upload_json_with_retries(self, data: Any, blob_name: str, max_retries: int = 4) -> bool:
        return True


class GcsBlobStorage:
    """Google Cloud Storage backup of synced JSON. Skips the upload when content is unchanged."""

    def __init__(self, bucket, prefix: str = "", sleep: Callable[[float], None] = time.sleep):
        self.bucket = bucket
        self.prefix = prefix
        self._sleep = sleep

    def _path(self, blob_name: str) -> str:
        return f"{self.prefix}/{blob_name}" if self.prefix else blob_name

    def _existing_sha(self, blob) -> Optional[str]:
        try:
            blob.reload()
        except Exception:
            return None
        return (blob.metadata or {}).get("content_sha256")

    def upload_json_with_retries(self, data: Any, blob_name: str, max_retries: int = 4) -> bool:
        try:
            payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        except Exception as e:
            logger.error("Failed to serialize JSON for '%s': %s", blob_name, e)
            return False

        sha = hashlib.sha256(payload).hexdigest()
        blob = self.bucket.blob(self._path(blob_name))
        if self._existing_sha(blob) == sha:
            logger.info("Skipping upload for '%s' (content unchanged)", blob_name)
            return True

        blob.metadata = {"content_sha256": sha}
        backoff = 0.5
        for attempt in range(1, max_retries + 1):
            try:
                blob.upload_from_string(payload, content_type="application/json")
                return True
            except Exception as e:
                logger.warning("Upload attempt %d failed for '%s': %s", attempt, blob_name, e)
                if attempt < max_retries:
                    self._sleep(backoff + random.uniform(0, 0.2))
                    backoff = min(backoff * 2, 8)
        logger.error("Exhausted retries uploading '%s'", blob_name)
        return False


def _default_bucket(name: str):
    from google.cloud import storage

    return storage.Client().bucket(name)


def _default_azure(container: str):
    from ..repository.azure.azure_blob_storage import AzureBlobStorage

    return AzureBlobStorage(container_name=container)


def build_blob_storage(
    container: str,
    bucket_factory: Callable[[str], Any] = _default_bucket,
    azure_factory: Callable[[str], Any] = _default_azure,
) -> BlobStorage:
    """BLOB_STORAGE=gcs|azure|none. If unset: gcs when GCS_BUCKET is set, azure when
    AZURE_STORAGE_CONNECTION_STRING is set, otherwise none."""
    choice = (os.environ.get("BLOB_STORAGE") or "").strip().lower()
    if not choice:
        if os.environ.get("GCS_BUCKET"):
            choice = "gcs"
        elif os.environ.get("AZURE_STORAGE_CONNECTION_STRING"):
            choice = "azure"
        else:
            choice = "none"

    if choice == "none":
        return NullBlobStorage()
    if choice == "gcs":
        bucket_name = os.environ.get("GCS_BUCKET")
        if not bucket_name:
            raise ValueError("BLOB_STORAGE=gcs requires GCS_BUCKET")
        return GcsBlobStorage(bucket_factory(bucket_name), prefix=container)
    if choice == "azure":
        return azure_factory(container)
    raise ValueError(f"Unknown BLOB_STORAGE '{choice}' (use gcs, azure or none)")
