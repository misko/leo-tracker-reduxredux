"""Shared publications do not masquerade as legacy position results."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.shared_fast_scan import shared_fast_scan_router


class Reader:
    def page(self, limit=100):
        return {"items": [{"state": "unavailable"}][:limit]}

    def detail(self, job_id):
        if job_id == "0" * 32:
            raise FileNotFoundError
        if job_id == "1" * 32:
            raise ValueError("private diagnostic path")
        return {"job_id": job_id, "state": "complete", "model_version": "shared-v1"}


def client(reader=None):
    app = FastAPI()
    app.include_router(shared_fast_scan_router(reader))
    return TestClient(app)


def test_shared_results_are_separate_bounded_and_read_only():
    api = client(Reader())
    prefix = "/api/v1/fast-scan-shared-model"
    assert api.get(prefix).json()["items"] == [{"state": "unavailable"}]
    assert api.get(prefix + "/" + "a" * 32).json()["model_version"] == "shared-v1"
    assert api.get(prefix + "?limit=101").status_code == 422
    assert api.get(prefix + "/invalid").status_code == 422
    assert api.post(prefix).status_code == 405
    assert api.get(prefix + "/" + "0" * 32).status_code == 404
    response = api.get(prefix + "/" + "1" * 32)
    assert response.status_code == 409
    assert "private diagnostic" not in response.text


def test_disabled_reader_is_empty_without_creating_results():
    api = client()
    prefix = "/api/v1/fast-scan-shared-model"
    assert api.get(prefix).json() == {"items": []}
    assert api.get(prefix + "/" + "a" * 32).status_code == 404
