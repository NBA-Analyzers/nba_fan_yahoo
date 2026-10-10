import pytest
from flask import Flask

from appl.router.document_router import DocumentRouter
from appl.tests.unit.test_chat_router import FakeAccess


class FakeIndexer:
    def __init__(self):
        self.calls = []

    def update_league_files(self, league_id, files):
        self.calls.append((league_id, files))
        return f"league_{league_id}"


@pytest.fixture
def indexer():
    return FakeIndexer()


@pytest.fixture
def access():
    return FakeAccess()


@pytest.fixture
def client(indexer, access):
    app = Flask(__name__)
    app.register_blueprint(DocumentRouter(indexer, access).get_bp())
    return app.test_client()


def test_anonymous_callers_cannot_replace_a_league_index(client, indexer, access):
    access.user = None
    r = client.post("/42/update_files", json={"roster": {}})
    assert r.status_code == 401
    assert indexer.calls == []


def test_someone_elses_league_is_forbidden(client, indexer):
    r = client.post("/99/update_files", json={"roster": {}})
    assert r.status_code == 403
    assert indexer.calls == []


def test_empty_or_non_object_body_is_rejected(client, indexer):
    assert client.post("/42/update_files", json=[]).status_code == 400
    assert client.post("/42/update_files", data="nope").status_code == 400
    assert indexer.calls == []


def test_owner_reindexes_and_gets_the_collection_id(client, indexer):
    r = client.post("/42/update_files", json={"roster": {"a": 1}})
    assert r.status_code == 200
    assert r.get_json() == {"collection_id": "league_42"}
    assert indexer.calls == [("42", {"roster": {"a": 1}})]
