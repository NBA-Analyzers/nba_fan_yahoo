import pytest

from appl.identity import MemoryIdentityStore, UnverifiedEmail, resolve_user


def google(sub="g123", email="a@x.com", verified=True):
    return {"uid": "fb-uid", "email": email, "email_verified": verified, "name": "Ann",
            "firebase": {"sign_in_provider": "google.com", "identities": {"google.com": [sub]}}}


def password(uid="fb1", email="a@x.com", verified=True):
    return {"uid": uid, "email": email, "email_verified": verified,
            "firebase": {"sign_in_provider": "password", "identities": {"email": [email]}}}


def test_new_google_user_keeps_google_sub_as_user_id():
    store = MemoryIdentityStore()
    assert resolve_user(store, google())["user_id"] == "g123"


def test_new_email_user_gets_id_derived_from_email():
    store = MemoryIdentityStore()
    user_id = resolve_user(store, password())["user_id"]
    assert user_id.startswith("e_") and user_id != "fb1"


def test_known_identity_returns_same_user():
    store = MemoryIdentityStore()
    first = resolve_user(store, password())["user_id"]
    assert resolve_user(store, password())["user_id"] == first


def test_verified_email_links_to_existing_user():
    store = MemoryIdentityStore()
    legacy = resolve_user(store, google())["user_id"]
    assert resolve_user(store, password())["user_id"] == legacy


def test_legacy_backfilled_google_user_links_by_email():
    store = MemoryIdentityStore()
    store.put_identity("google.com", "old-sub", "old-sub", "a@x.com", True)
    assert resolve_user(store, password())["user_id"] == "old-sub"


def test_different_emails_are_different_users():
    store = MemoryIdentityStore()
    a = resolve_user(store, password("u1", "a@x.com"))["user_id"]
    b = resolve_user(store, password("u2", "b@x.com"))["user_id"]
    assert a != b


def test_unverified_email_rejected():
    store = MemoryIdentityStore()
    with pytest.raises(UnverifiedEmail):
        resolve_user(store, password(verified=False))
    assert not store.identities


def test_email_is_normalised():
    store = MemoryIdentityStore()
    a = resolve_user(store, google(email="A@X.com"))["user_id"]
    assert resolve_user(store, password(email="a@x.COM"))["user_id"] == a


# ---------- sign_in: storage failures ----------
import logging

from flask import Blueprint, Flask

from appl.identity import sign_in
from appl.repository.firestore import AuthService
from appl.router.auth_routes import AuthRouter
from appl.tests.unit.fake_firestore import FakeFirestore


class BrokenStore:
    def __getattr__(self, name):
        def fail(*a, **k):
            raise RuntimeError("firestore unavailable")
        return fail


class FlakyProfileStore(MemoryIdentityStore):
    def upsert_user(self, user_id, profile):
        raise RuntimeError("profile write failed")


def test_profile_write_failure_is_logged_and_does_not_block(caplog):
    with caplog.at_level(logging.ERROR):
        out = sign_in(FlakyProfileStore(), google())
    assert out["user_id"] == "g123"
    assert any(r.exc_info for r in caplog.records)


def test_google_user_signs_in_with_sub_when_store_is_down(caplog):
    with caplog.at_level(logging.ERROR):
        assert sign_in(BrokenStore(), google())["user_id"] == "g123"
    assert any(r.exc_info for r in caplog.records)


def test_email_user_still_signs_in_when_store_is_down_with_the_same_id(caplog):
    healthy = resolve_user(MemoryIdentityStore(), password())["user_id"]
    with caplog.at_level(logging.ERROR):
        assert sign_in(BrokenStore(), password())["user_id"] == healthy
    assert any(r.exc_info for r in caplog.records)


class FakeGoogle:
    def authorize_access_token(self):
        return {"access_token": "t"}

    def get(self, url):
        class R:
            def json(self_inner):
                return {"sub": "g123", "email": "a@x.com", "email_verified": True,
                        "name": "Ann Lee", "given_name": "Ann"}
        return R()


def _callback_app(store):
    app = Flask(__name__)
    app.secret_key = "test"
    app.oauth = type("O", (), {"create_client": lambda self, name: FakeGoogle()})()
    main = Blueprint("main", __name__)
    main.add_url_rule("/dashboard", "dashboard", lambda: "dash")
    app.register_blueprint(main)
    app.register_blueprint(AuthRouter(None, store, AuthService(FakeFirestore())).get_bp())
    return app


def test_google_callback_redirects_and_logs_when_database_write_fails(caplog):
    client = _callback_app(BrokenStore()).test_client()
    with caplog.at_level(logging.ERROR):
        resp = client.get("/auth/google/callback")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/dashboard")
    with client.session_transaction() as s:
        assert s["user_id"] == "g123" and s["profile"]["given_name"] == "Ann"
    assert any(r.exc_info for r in caplog.records)


def test_google_callback_double_login_is_one_user():
    store = MemoryIdentityStore()
    client = _callback_app(store).test_client()
    client.get("/auth/google/callback")
    client.get("/auth/google/callback")
    assert list(store.users) == ["g123"] and len(store.identities) == 1
