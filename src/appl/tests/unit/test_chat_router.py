import pytest
from flask import Flask

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


@pytest.fixture
def service():
    return FakeChatService()


@pytest.fixture
def client(service):
    app = Flask(__name__)
    app.register_blueprint(ChatRouter(service).get_bp())
    return app.test_client()


def test_chat_returns_answer_text(client, service):
    body = {"session_id": "s", "user_message": "hi", "league_id": "1"}
    response = client.post("/chat", json=body)
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "the answer"
    assert service.requests == [body]


def test_invalid_request_is_400(client, service):
    service.error = ValueError("session_id and user_message are required")
    response = client.post("/chat", json={"session_id": "s"})
    assert response.status_code == 400
    assert "required" in response.get_json()["error"]


def test_non_json_body_is_400(client):
    assert client.post("/chat", data="nope", content_type="text/plain").status_code == 400


def test_llm_failure_is_502(client, service):
    service.error = LLMError("down")
    response = client.post("/chat", json={"session_id": "s", "user_message": "hi"})
    assert response.status_code == 502
    assert response.get_json()["error"]
