import json

import pytest

from appl.storage.blob_storage import (
    GcsBlobStorage,
    NullBlobStorage,
    build_blob_storage,
)


# ---------- minimal fake of google.cloud.storage ----------
class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket, self.name = bucket, name
        self.metadata = None

    def reload(self):
        from google.api_core.exceptions import NotFound

        if self.name not in self.bucket.objects:
            raise NotFound("missing")
        self.metadata = self.bucket.objects[self.name]["metadata"]

    def upload_from_string(self, payload, content_type=None):
        if self.bucket.fail_times:
            self.bucket.fail_times -= 1
            raise RuntimeError("transient")
        self.bucket.uploads += 1
        self.bucket.objects[self.name] = {
            "payload": payload,
            "metadata": dict(self.metadata or {}),
            "content_type": content_type,
        }


class FakeBucket:
    def __init__(self):
        self.objects, self.uploads, self.fail_times = {}, 0, 0

    def blob(self, name):
        return FakeBlob(self, name)


@pytest.fixture
def bucket():
    return FakeBucket()


@pytest.fixture
def gcs(bucket):
    sleeps = []
    storage = GcsBlobStorage(bucket, prefix="fantasy1", sleep=sleeps.append)
    storage.sleeps = sleeps
    return storage


def test_upload_stores_json_under_prefix(gcs, bucket):
    assert gcs.upload_json_with_retries({"a": 1}, "42/standings.json") is True
    stored = bucket.objects["fantasy1/42/standings.json"]
    assert json.loads(stored["payload"]) == {"a": 1}
    assert stored["content_type"] == "application/json"
    assert "content_sha256" in stored["metadata"]


def test_unchanged_content_is_not_uploaded_again(gcs, bucket):
    gcs.upload_json_with_retries({"a": 1}, "x.json")
    assert gcs.upload_json_with_retries({"a": 1}, "x.json") is True
    assert bucket.uploads == 1


def test_changed_content_is_uploaded_again(gcs, bucket):
    gcs.upload_json_with_retries({"a": 1}, "x.json")
    gcs.upload_json_with_retries({"a": 2}, "x.json")
    assert bucket.uploads == 2


def test_transient_failures_are_retried_with_backoff(gcs, bucket):
    bucket.fail_times = 2
    assert gcs.upload_json_with_retries({"a": 1}, "x.json") is True
    assert len(gcs.sleeps) == 2 and gcs.sleeps[1] > gcs.sleeps[0]


def test_returns_false_after_retries_are_exhausted(gcs, bucket):
    bucket.fail_times = 99
    assert gcs.upload_json_with_retries({"a": 1}, "x.json", max_retries=3) is False


def test_unserializable_data_returns_false(gcs):
    assert gcs.upload_json_with_retries({"a": object()}, "x.json") is False


def test_null_storage_accepts_everything_and_stores_nothing():
    assert NullBlobStorage().upload_json_with_retries({"a": 1}, "x.json") is True


# ---------- factory ----------
def test_defaults_to_null_when_nothing_is_configured(monkeypatch):
    for v in ("BLOB_STORAGE", "GCS_BUCKET", "AZURE_STORAGE_CONNECTION_STRING"):
        monkeypatch.delenv(v, raising=False)
    assert isinstance(build_blob_storage("fantasy1"), NullBlobStorage)


def test_explicit_none(monkeypatch):
    monkeypatch.setenv("BLOB_STORAGE", "none")
    monkeypatch.setenv("GCS_BUCKET", "b")
    assert isinstance(build_blob_storage("c"), NullBlobStorage)


def test_gcs_selected_when_bucket_is_set(monkeypatch):
    monkeypatch.delenv("BLOB_STORAGE", raising=False)
    monkeypatch.delenv("AZURE_STORAGE_CONNECTION_STRING", raising=False)
    monkeypatch.setenv("GCS_BUCKET", "my-bucket")
    made = {}

    def fake_bucket_factory(name):
        made["bucket"] = name
        return FakeBucket()

    storage = build_blob_storage("fantasy1", bucket_factory=fake_bucket_factory)
    assert isinstance(storage, GcsBlobStorage)
    assert made["bucket"] == "my-bucket"
    assert storage.prefix == "fantasy1"


def test_gcs_requested_without_bucket_is_an_error(monkeypatch):
    monkeypatch.setenv("BLOB_STORAGE", "gcs")
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    with pytest.raises(ValueError, match="GCS_BUCKET"):
        build_blob_storage("c")


def test_azure_is_still_supported_when_configured(monkeypatch):
    monkeypatch.delenv("BLOB_STORAGE", raising=False)
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "conn")
    sentinel = object()
    assert build_blob_storage("c", azure_factory=lambda c: sentinel) is sentinel


def test_unknown_backend_is_an_error(monkeypatch):
    monkeypatch.setenv("BLOB_STORAGE", "dropbox")
    with pytest.raises(ValueError, match="dropbox"):
        build_blob_storage("c")
