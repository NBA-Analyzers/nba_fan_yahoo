"""Server-side sessions: the cookie is an opaque id, the data stays on the server."""
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask, jsonify, session

from appl.config.server_session import (COLLECTION, COOKIE_NAME, FirestoreSessionStore,
                                        MemorySessionStore, ServerSessionInterface,
                                        build_session_interface, session_doc_id)
from appl.tests.unit.fake_firestore import FakeFirestore

LIFETIME = timedelta(days=30)


def make_app(store=None, secure=False, lifetime=LIFETIME):
    app = Flask(__name__)
    app.secret_key = "test"
    app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=secure,
                      SESSION_COOKIE_HTTPONLY=True)
    app.session_interface = ServerSessionInterface(MemorySessionStore() if store is None else store, lifetime)

    @app.route("/health")
    def health():
        return "ok"

    @app.route("/touch")
    def touch():
        return jsonify(user=session.get("user_id"))

    @app.route("/login")
    def login():
        session["user_id"] = "u1"
        session["secret_token"] = "SECRET-VALUE"
        return "ok"

    @app.route("/nested")
    def nested():
        session.setdefault("token_store", {})["guid"] = {"access_token": "a1"}
        session.modified = True
        return "ok"

    @app.route("/nested2")
    def nested2():
        session["token_store"]["guid"]["access_token"] = "a2"
        session.modified = True
        return "ok"

    @app.route("/rotate")
    def rotate():
        session.rotate()
        return "ok"

    @app.route("/logout")
    def logout():
        session.clear()
        return "bye"

    return app


def sid_of(client):
    cookie = client.get_cookie(COOKIE_NAME)
    return cookie.value if cookie else None


def test_cookie_is_an_opaque_id_with_no_session_data():
    app = make_app()
    client = app.test_client()
    resp = client.get("/login")
    header = " ".join(resp.headers.getlist("Set-Cookie"))
    assert COOKIE_NAME in header
    for leaked in ("u1", "SECRET-VALUE", "user_id"):
        assert leaked not in header
    assert len(sid_of(client)) >= 40


def test_data_persists_across_requests():
    client = make_app().test_client()
    client.get("/login")
    assert client.get("/touch").get_json() == {"user": "u1"}


def test_nested_modification_persists():
    client = make_app().test_client()
    client.get("/nested")
    client.get("/nested2")
    with client.session_transaction() as s:
        assert s["token_store"]["guid"]["access_token"] == "a2"


def test_anonymous_requests_create_no_record_and_no_cookie():
    store = MemorySessionStore()
    client = make_app(store).test_client()
    resp = client.get("/health")
    assert not resp.headers.getlist("Set-Cookie")
    client.get("/touch")  # reads the session but never writes it
    assert len(store) == 0 and sid_of(client) is None


def test_expired_id_gives_an_empty_session():
    store = MemorySessionStore()
    client = make_app(store, lifetime=timedelta(seconds=-1)).test_client()
    client.get("/login")
    assert client.get("/touch").get_json() == {"user": None}


def test_unknown_id_gives_an_empty_session():
    client = make_app().test_client()
    client.set_cookie(COOKIE_NAME, "forged-id")
    assert client.get("/touch").get_json() == {"user": None}


def test_logout_deletes_the_server_record_and_the_cookie():
    store = MemorySessionStore()
    client = make_app(store).test_client()
    client.get("/login")
    old = sid_of(client)
    resp = client.get("/logout")
    assert len(store) == 0 and sid_of(client) is None
    assert any("Expires=Thu, 01 Jan 1970" in h for h in resp.headers.getlist("Set-Cookie"))
    # pressing Back and reusing the old cookie finds nothing
    client.set_cookie(COOKIE_NAME, old)
    assert client.get("/touch").get_json() == {"user": None}


def test_rotation_issues_a_new_id_and_keeps_the_data():
    store = MemorySessionStore()
    client = make_app(store).test_client()
    client.get("/login")
    old = sid_of(client)
    client.get("/rotate")
    new = sid_of(client)
    assert new and new != old and len(store) == 1
    assert client.get("/touch").get_json() == {"user": "u1"}
    other = make_app(store).test_client()
    other.set_cookie(COOKIE_NAME, old)
    assert other.get("/touch").get_json() == {"user": None}  # the old id is dead


def test_cookie_flags_httponly_lax_and_secure_when_configured():
    resp = make_app(secure=True).test_client().get("/login", base_url="https://localhost")
    header = resp.headers.getlist("Set-Cookie")[0]
    assert "HttpOnly" in header and "SameSite=Lax" in header and "Secure" in header
    plain = make_app(secure=False).test_client().get("/login").headers.getlist("Set-Cookie")[0]
    assert "Secure" not in plain and "HttpOnly" in plain


def test_firestore_backend_stores_hashed_id_expiry_and_data():
    db = FakeFirestore()
    client = make_app(FirestoreSessionStore(db)).test_client()
    client.get("/login")
    sid = sid_of(client)
    docs = db.docs(COLLECTION)
    assert list(docs) == [session_doc_id(sid)] and sid not in list(docs)[0]
    doc = docs[session_doc_id(sid)]
    assert doc["expires_at"] > datetime.now(timezone.utc) + timedelta(days=29)
    assert doc["user_key"] == "u1" and "created_at" in doc
    assert client.get("/touch").get_json() == {"user": "u1"}
    client.get("/logout")
    assert db.docs(COLLECTION) == {}


def test_firestore_backend_ignores_expired_documents():
    db = FakeFirestore()
    store = FirestoreSessionStore(db)
    store.save("sid1", {"user_id": "u1"}, datetime.now(timezone.utc) - timedelta(minutes=1), None)
    assert store.load("sid1", datetime.now(timezone.utc)) is None


def test_build_defaults_to_memory_without_cloud_run(monkeypatch):
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("SESSION_STORE", raising=False)
    assert isinstance(build_session_interface().store, MemorySessionStore)
    monkeypatch.setenv("K_SERVICE", "svc")
    assert isinstance(build_session_interface(firestore_client=FakeFirestore()).store,
                      FirestoreSessionStore)


def test_session_lifetime_comes_from_env(monkeypatch):
    monkeypatch.setenv("SESSION_LIFETIME_DAYS", "7")
    assert build_session_interface("memory").lifetime == timedelta(days=7)
