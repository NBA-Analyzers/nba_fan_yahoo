"""Named JSON datasets (player pools, stats report, schedule) that outlive one process.

On Cloud Run the disk is wiped with every new instance, so datasets go to GCS
(DATASET_BUCKET, falling back to GCS_BUCKET); locally they are files under appl/data/datasets.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional, Protocol

from ...storage.blob_storage import GcsBlobStorage

logger = logging.getLogger(__name__)

LOCAL_DIR = Path(__file__).resolve().parents[2] / "data" / "datasets"
GCS_PREFIX = "datasets"


class DatasetStore(Protocol):
    def put(self, name: str, data: Any) -> None: ...

    def get(self, name: str) -> Optional[Any]: ...


class LocalDatasetStore:
    def __init__(self, root: Path = LOCAL_DIR):
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        return self.root / f"{name}.json"

    def put(self, name: str, data: Any) -> None:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, path)

    def get(self, name: str) -> Optional[Any]:
        path = self._path(name)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


class GcsDatasetStore:
    """Writes go through GcsBlobStorage (retries, skip when the content hash is unchanged)."""

    def __init__(self, bucket, prefix: str = GCS_PREFIX):
        self.bucket = bucket
        self.prefix = prefix
        self._writer = GcsBlobStorage(bucket, prefix=prefix)

    def put(self, name: str, data: Any) -> None:
        if not self._writer.upload_json_with_retries(data, f"{name}.json"):
            raise RuntimeError(f"Couldn't store dataset {name}")

    def get(self, name: str) -> Optional[Any]:
        blob = self.bucket.blob(f"{self.prefix}/{name}.json")
        try:
            return json.loads(blob.download_as_text())
        except Exception as e:
            if type(e).__name__ != "NotFound":
                logger.warning("dataset %s unreadable: %s", name, type(e).__name__)
            return None


def build_dataset_store() -> DatasetStore:
    bucket_name = os.environ.get("DATASET_BUCKET") or os.environ.get("GCS_BUCKET")
    if not bucket_name:
        return LocalDatasetStore()
    from google.cloud import storage

    return GcsDatasetStore(storage.Client().bucket(bucket_name))
