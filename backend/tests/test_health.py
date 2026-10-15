from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_answers_get():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_answers_head_for_uptime_monitors():
    response = client.head("/health")
    assert response.status_code == 200
    assert response.content == b""
