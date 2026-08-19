from __future__ import annotations

from pathlib import Path

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from leo.api import create_app
from leo.presentation.fixtures import build_fixture_repository, write_fixture_artifacts
from leo.presentation.standard_fixtures import build_standard_fixture_repository


def _client(tmp_path: Path) -> TestClient:
    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    return TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_repository=build_standard_fixture_repository(),
        )
    )


def test_standard_routes_are_read_only_and_test_evidence_is_opt_in(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    app = create_app(
        build_fixture_repository(artifacts),
        artifact_root=artifacts,
        standard_repository=build_standard_fixture_repository(),
    )
    routes = [
        route
        for included in app.routes
        for route in getattr(getattr(included, "original_router", None), "routes", ())
        if isinstance(route, APIRoute) and route.path.startswith("/api/v2/")
    ]
    assert len(routes) == 3
    assert all(route.methods == {"GET", "HEAD"} for route in routes)

    client = TestClient(app)
    path = "/api/v2/recordings/T1/standard-subjects"
    assert client.get(path).status_code == 404
    response = client.get(path, params={"include_test": True})
    assert response.status_code == 200
    assert response.json()["eligibility"]["evidence_only"] is True
    assert all(row["ordinary_current"] is False for row in response.json()["rows"])
    assert client.post(path, json={"promote": True}).status_code == 405


def test_three_rows_detail_and_lazy_plot_are_bounded(tmp_path: Path) -> None:
    client = _client(tmp_path)
    common = {"include_test": True}
    listing = client.get(
        "/api/v2/recordings/T1/standard-subjects", params=common
    ).json()
    assert [row["label"] for row in listing["rows"]] == [
        "Paired Radio0 + Radio1",
        "Radio0",
        "Radio1",
    ]
    assert listing["rows"][0]["subject_kind"] == "paired"
    assert listing["rows"][0]["derived"] is True

    detail = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1",
        params=common,
    ).json()
    assert len(detail["receiver_path_expansions"]) == 4
    assert len(detail["views"]) == 6
    assert not any("points" in descriptor for descriptor in detail["views"])
    assert detail["limitations"][0].startswith("Candidate evidence only")

    plot = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/views/cfo_trajectory",
        params={**common, "maximum_points": 7},
    ).json()
    assert plot["returned_point_count"] == 7
    assert plot["source_point_count"] == 16
    assert plot["truncated"] is True
    assert plot["time_domain"] == detail["time_domain"]
    assert plot["horizontal_axis"]["axis_id"] == "time"
    assert plot["vertical_axis"]["axis_id"] == "frequency_hz"
    full_plot = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/views/cfo_trajectory",
        params={**common, "maximum_points": 2048},
    ).json()
    assert plot["horizontal_axis"] == full_plot["horizontal_axis"]
    assert plot["vertical_axis"] == full_plot["vertical_axis"]
    assert client.head(
        "/api/v2/recordings/T1/standard-subjects/radio:radio0/views/glrt64",
        params=common,
    ).status_code == 200
    assert client.get(
        "/api/v2/recordings/T1/standard-subjects/radio:radio0/views/glrt64",
        params={**common, "maximum_points": 2049},
    ).status_code == 422


def test_unconfigured_standard_projection_fails_fast_without_touching_v1(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    client = TestClient(
        create_app(build_fixture_repository(artifacts), artifact_root=artifacts)
    )
    assert client.get("/api/v1/status").status_code == 200
    response = client.get("/api/v2/recordings/T1/standard-subjects")
    assert response.status_code == 503
    assert response.json()["detail"] == "Standard-v2 presentation projection is not configured"
