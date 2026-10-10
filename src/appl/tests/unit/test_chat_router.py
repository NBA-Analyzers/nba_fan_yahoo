import pytest
from flask import Flask

from appl.ai.access import CurrentUser, SessionAccess
from appl.ai.chat_router import ChatRouter
from appl.ai.litellm_adapters import LLMError


class FakeChatService:
    def __init__(self):
        self.requests = []
        self.error = None

    def chat(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return "the answer"


class FakeAccess:
    def __init__(self, user=CurrentUser(user_id="g1", yahoo_id="y1"), leagues=("42",)):
        self.user, self.leagues, self.error = user, set(leagues), None
        self.checked = []

    def current_user(self):
        return self.user

    def can_access_league(self, user, league_id):
        self.checked.append((user, league_id))
        if self.error:
            raise self.error
        return league_id in self.leagues


@pytest.fixture
def service():
    return FakeChatService()


@pytest.fixture
def access():
    return FakeAccess()


@pytest.fixture
def client(service, access):
    app = Flask(__name__)
    app.register_blueprint(ChatRouter(service, access).get_bp())
    return app.test_client()


def post(client, **body):
    return client.post("/chat", json=body)


# ---------- authentication ----------
def test_anonymous_requests_are_rejected_without_calling_the_service(client, service, access):
    access.user = None
    r = post(client, session_id="s", user_message="hi")
    assert r.status_code == 401
    assert "log" in r.get_json()["error"].lower()
    assert service.requests == []


# ---------- authorization ----------
def test_chat_without_league_is_allowed_for_logged_in_users(client, service):
    r = post(client, session_id="s", user_message="hi")
    assert r.status_code == 200 and r.get_data(as_text=True) == "the answer"
    assert service.requests[0]["league_id"] is None


def test_blank_league_id_is_treated_as_no_league(client, service, access):
    post(client, session_id="s", user_message="hi", league_id="  ")
    assert service.requests[0]["league_id"] is None
    assert access.checked == []


def test_own_league_is_allowed(client, service):
    r = post(client, session_id="s", user_message="hi", league_id="42")
    assert r.status_code == 200
    assert service.requests[0]["league_id"] == "42"


def test_someone_elses_league_is_forbidden_and_service_not_called(client, service):
    r = post(client, session_id="s", user_message="hi", league_id="999")
    assert r.status_code == 403
    assert service.requests == []


def test_access_check_failure_fails_closed(client, service, access):
    access.error = RuntimeError("database down")
    r = post(client, session_id="s", user_message="hi", league_id="42")
    assert r.status_code == 503
    assert service.requests == []


# ---------- per-user chat history ----------
def test_session_ids_are_namespaced_per_user(service, access):
    app = Flask(__name__)
    app.register_blueprint(ChatRouter(service, access).get_bp())
    c = app.test_client()
    post(c, session_id="abc", user_message="hi")
    access.user = CurrentUser(user_id="g2", yahoo_id=None)
    post(c, session_id="abc", user_message="hi")
    assert [r["session_id"] for r in service.requests] == ["g1:abc", "g2:abc"]


# ---------- existing behavior ----------
def test_chat_returns_answer_text(client, service):
    r = post(client, session_id="s", user_message="hi", league_id="42")
    assert (r.status_code, r.get_data(as_text=True)) == (200, "the answer")


def test_invalid_request_is_400(client, service):
    service.error = ValueError("session_id and user_message are required")
    r = post(client, session_id="s")
    assert r.status_code == 400
    assert "required" in r.get_json()["error"]


def test_missing_session_id_is_400_not_a_crash(client, service):
    service.error = ValueError("session_id and user_message are required")
    assert post(client, user_message="hi").status_code == 400


def test_non_json_body_is_400(client):
    assert client.post("/chat", data="nope", content_type="text/plain").status_code == 400


def test_llm_failure_is_502(client, service):
    service.error = LLMError("down")
    r = post(client, session_id="s", user_message="hi")
    assert r.status_code == 502 and r.get_json()["error"]


# ---------- SessionAccess (reads the Flask login session + league table) ----------
class FakeLeagueRepo:
    def __init__(self, rows):
        self.rows = rows

    def league_exist_for_user(self, league_id, yahoo_user_id):
        return (league_id, yahoo_user_id) in self.rows


@pytest.fixture
def flask_app():
    app = Flask(__name__)
    app.secret_key = "t"
    return app


def test_current_user_reads_google_and_yahoo_ids_from_session(flask_app):
    sa = SessionAccess(lambda: FakeLeagueRepo(set()))
    with flask_app.test_request_context():
        from flask import session

        assert sa.current_user() is None
        session["user_id"] = "g-123"
        assert sa.current_user() == CurrentUser("g-123", None)
        session["user"] = "y-9"
        assert sa.current_user() == CurrentUser("g-123", "y-9")


def test_league_access_requires_a_yahoo_login_and_a_matching_row():
    sa = SessionAccess(lambda: FakeLeagueRepo({("42", "y1")}))
    assert sa.can_access_league(CurrentUser("g", "y1"), "42") is True
    assert sa.can_access_league(CurrentUser("g", "y1"), "43") is False
    assert sa.can_access_league(CurrentUser("g", "y2"), "42") is False
    assert sa.can_access_league(CurrentUser("g", None), "42") is False
