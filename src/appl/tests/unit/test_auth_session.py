"""POST /auth/session: Firebase ID token -> our user_id and a server-side session."""
from flask import Blueprint, Flask, render_template

from appl.config.server_session import MemorySessionStore, ServerSessionInterface
from appl.identity import MemoryIdentityStore
from appl.identity.firebase_verify import InvalidToken
from appl.middleware.auth_decorators import require_login
from appl.repository.firestore import AuthService
from appl.router.auth_routes import AuthRouter
from appl.tests.unit.fake_firestore import FakeFirestore
from datetime import timedelta

GOOD = {
    "uid": "fb1", "email": "Ann@X.com", "email_verified": True, "name": "Ann",
    "firebase": {"sign_in_provider": "password", "identities": {"email": ["ann@x.com"]}},
}


def verifier(claims=GOOD):
    def verify(token):
        if token != "good":
            raise InvalidToken("ExpiredIdTokenError")
        return claims
    return verify


def make_client(claims=GOOD, store=None):
    app = Flask(__name__)
    app.secret_key = "test"
    app.session_interface = ServerSessionInterface(MemorySessionStore(), timedelta(days=30))
    main = Blueprint("main", __name__)
    main.add_url_rule("/dashboard", "dashboard", lambda: "dash")
    main.add_url_rule("/", "homepage", lambda: "home")
    main.add_url_rule("/private", "private", require_login(lambda: "secret"))
    app.register_blueprint(main)
    store = store or MemoryIdentityStore()
    app.register_blueprint(AuthRouter(None, store, AuthService(FakeFirestore()),
                                      verifier(claims)).get_bp())
    return app.test_client(), store


def post(client, body, **kw):
    return client.post("/auth/session", json=body, **kw)


def test_valid_token_starts_a_session_for_an_email_user():
    client, store = make_client()
    resp = post(client, {"idToken": "good"})
    assert resp.status_code == 200 and resp.get_json()["redirect"] == "/dashboard"
    with client.session_transaction() as s:
        assert s["user_id"].startswith("e_") and s["profile"]["email"] == "ann@x.com"
    assert client.get("/private").data == b"secret"


def test_invalid_token_is_rejected_and_no_session_starts():
    client, _ = make_client()
    assert post(client, {"idToken": "bad"}).status_code == 401
    assert client.get("/private").status_code == 302


def test_missing_token_and_non_json_are_rejected():
    client, _ = make_client()
    assert post(client, {}).status_code == 400
    assert client.post("/auth/session", data="x").status_code == 400


def test_unverified_email_is_refused():
    client, store = make_client({**GOOD, "email_verified": False})
    assert post(client, {"idToken": "good"}).status_code == 403
    assert not store.identities
    assert client.get("/private").status_code == 302


def test_cross_site_origin_is_refused():
    client, _ = make_client()
    resp = post(client, {"idToken": "good"}, headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403
    ok = post(client, {"idToken": "good"}, headers={"Origin": "http://localhost"})
    assert ok.status_code == 200


def test_google_firebase_login_keeps_the_legacy_google_sub():
    claims = {"uid": "fb-g", "email": "a@x.com", "email_verified": True,
              "firebase": {"sign_in_provider": "google.com", "identities": {"google.com": ["g-999"]}}}
    client, _ = make_client(claims)
    post(client, {"idToken": "good"})
    with client.session_transaction() as s:
        assert s["user_id"] == "g-999"


def test_session_id_changes_at_login():
    client, _ = make_client()
    client.get("/private")  # anonymous, nothing stored
    post(client, {"idToken": "good"})
    first = client.get_cookie("fbh_sid").value
    post(client, {"idToken": "good"})
    assert client.get_cookie("fbh_sid").value != first


def test_logout_ends_the_session():
    client, _ = make_client()
    post(client, {"idToken": "good"})
    client.get("/auth/logout")
    assert client.get("/private").status_code == 302


def test_home_page_shows_widget_only_when_firebase_is_configured():
    app = Flask(__name__, template_folder="../../static")
    app.secret_key = "t"
    with app.test_request_context():
        cfg = {"apiKey": "k", "authDomain": "d.firebaseapp.com", "projectId": "p"}
        with_fb = render_template("pages/home.html", firebase=cfg)
        without = render_template("pages/home.html", firebase=None)
    assert 'id="signin"' in with_fb and "/static/login.js" in with_fb and "d.firebaseapp.com" in with_fb
    assert 'id="signin"' not in without and "/auth/google/login" in without
