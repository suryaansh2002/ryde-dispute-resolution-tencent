"""POST /cases/{id}/evidence — DB and object storage monkeypatched, no network."""

import pytest
from fastapi.testclient import TestClient

import app.api.evidence as evidence_api
from app.main import app


class FakeConn:
    async def close(self):
        pass


def _async(value):
    async def fn(*args, **kwargs):
        return value
    return fn


@pytest.fixture
def client(monkeypatch):
    uploads = []

    def fake_upload(key, data, content_type):
        uploads.append((key, data, content_type))
        return "sha256:fake"

    monkeypatch.setattr(evidence_api, "get_connection", _async(FakeConn()))
    monkeypatch.setattr(evidence_api, "get_case_row", _async({"id": "CASE-0001"}))
    monkeypatch.setattr(evidence_api, "insert_evidence", _async("EV-0001"))
    monkeypatch.setattr(evidence_api, "upload_object", fake_upload)
    c = TestClient(app)
    c.uploads = uploads
    return c


def test_upload_stores_object_and_returns_evidence_id(client):
    resp = client.post(
        "/cases/CASE-0001/evidence", data={"kind": "photo"},
        files={"file": ("spill.png", b"bytes", "image/png")},
    )
    assert resp.status_code == 201
    assert resp.json() == {
        "evidence_id": "EV-0001", "object_key": "evidence/CASE-0001/spill.png",
        "hash": "sha256:fake",
    }
    assert client.uploads == [("evidence/CASE-0001/spill.png", b"bytes", "image/png")]


def test_unknown_case_is_404(client, monkeypatch):
    monkeypatch.setattr(evidence_api, "get_case_row", _async(None))
    resp = client.post(
        "/cases/CASE-9999/evidence", data={"kind": "photo"},
        files={"file": ("x.png", b"x", "image/png")},
    )
    assert resp.status_code == 404
    assert client.uploads == []


def test_oversized_upload_is_rejected(client, monkeypatch):
    monkeypatch.setattr(evidence_api, "_MAX_UPLOAD_BYTES", 4)
    resp = client.post(
        "/cases/CASE-0001/evidence", data={"kind": "photo"},
        files={"file": ("big.png", b"too many bytes", "image/png")},
    )
    assert resp.status_code == 413
    assert client.uploads == []
