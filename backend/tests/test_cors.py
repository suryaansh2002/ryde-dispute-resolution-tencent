from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.main import cors_origins

VERCEL = "https://ryde-dispute-resolution-tencent.vercel.app"


def test_trailing_slash_and_spaces_are_dropped():
    assert cors_origins(f"{VERCEL}/ , http://localhost:5173") == [VERCEL, "http://localhost:5173"]


def test_wildcard_and_empty_entries():
    assert cors_origins("*") == ["*"]
    assert cors_origins(" , ") == []


def _client(origins: str) -> TestClient:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware, allow_origins=cors_origins(origins), allow_methods=["*"],
        allow_headers=["*"],
    )
    app.get("/ping")(lambda: {"ok": True})
    return TestClient(app)


def test_pasted_url_with_slash_still_allows_the_frontend():
    client = _client(f"{VERCEL}/")
    response = client.get("/ping", headers={"Origin": VERCEL})
    assert response.headers["access-control-allow-origin"] == VERCEL


def test_other_origins_are_not_allowed():
    client = _client(VERCEL)
    response = client.get("/ping", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers
