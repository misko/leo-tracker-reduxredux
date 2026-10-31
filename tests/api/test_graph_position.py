"""The graph endpoint uses an explicit read port and reports disabled selection."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from leo.api.graph_position import graph_position_router


def test_disabled_graph_model_is_explicit():
    app = FastAPI()
    app.include_router(graph_position_router(None))
    assert TestClient(app).get("/api/v2/fast-scans/run/graph-position").json() == dict(
        state="disabled", selected_model=None
    )


def test_selected_graph_port_retains_both_endpoints_and_fallback():
    expected = dict(
        selected_model="algo03-causal-predictive-v1",
        decision="ALGO02_fallback",
        fallback=True,
        baseline=dict(model_version="algo02-causal-family-v1"),
        selected=dict(model_version="algo02-causal-family-v1"),
    )

    class Reader:
        def detail(self, run_id):
            assert run_id == "scan"
            return expected

    app = FastAPI()
    app.include_router(graph_position_router(Reader()))
    response = TestClient(app).get("/api/v2/fast-scans/scan/graph-position")
    assert response.status_code == 200
    assert response.json() == expected


def test_application_composes_graph_reader_without_database_access(tmp_path):
    from leo.api.app import create_app
    from leo.presentation.fixtures import build_fixture_repository

    class Reader:
        def detail(self, run_id):
            return dict(run_id=run_id, selected_model="algo03-causal-predictive-v1")

    app = create_app(
        build_fixture_repository(tmp_path), artifact_root=tmp_path, graph_positions=Reader()
    )
    response = TestClient(app).get("/api/v2/fast-scans/scan/graph-position")
    assert response.status_code == 200
    assert response.json() == dict(run_id="scan", selected_model="algo03-causal-predictive-v1")


def test_v3_selection_preserves_actual_predecessor_model_at_the_existing_endpoint():
    expected = dict(
        selected_model="algo04-causal-numerical-v1",
        decision="ALGO03_fallback",
        fallback=True,
        baseline=dict(model_version="algo02-causal-family-v1"),
        selected=dict(model_version="algo03-causal-predictive-v1"),
    )

    class Reader:
        def detail(self, run_id):
            assert run_id == "scan"
            return expected

    app = FastAPI()
    app.include_router(graph_position_router(Reader()))
    response = TestClient(app).get("/api/v2/fast-scans/scan/graph-position")
    assert response.status_code == 200
    assert response.json() == expected
