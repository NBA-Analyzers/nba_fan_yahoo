import pytest
from flask import Flask

from appl.middleware.auth_decorators import require_login


@pytest.fixture
def client():
    app = Flask(__name__)
    app.secret_key = "test"

    @app.route("/home")
    def homepage():
        return "home"

    app.add_url_rule("/home", endpoint="main.homepage", view_func=homepage)

    @app.route("/private", methods=["GET", "POST"])
    @require_login
    def private():
        return "secret"

    return app.test_client()


def test_a_browser_page_is_redirected_to_the_homepage(client):
    response = client.get("/private", headers={"Accept": "text/html"})
    assert response.status_code == 302


@pytest.mark.parametrize("kwargs", [
    {"headers": {"Accept": "application/json"}},
    {"json": {"x": 1}, "method": "POST"},
])
def test_api_calls_get_401_json_not_a_redirect(client, kwargs):
    method = kwargs.pop("method", "GET")
    response = client.open("/private", method=method, **kwargs)
    assert response.status_code == 401 and response.get_json()["error"]


def test_a_browser_form_post_is_redirected(client):
    assert client.post("/private", data={"x": "1"}).status_code == 302


def test_signed_in_users_pass(client):
    with client.session_transaction() as session:
        session["user_id"] = "u1"
    assert client.get("/private").data == b"secret"
