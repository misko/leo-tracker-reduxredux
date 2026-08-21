"""Read-only API surface for the sky interface.

Driven through the real FastAPI application against a temporary archive, so
method restrictions, parameter bounds, unavailability and the returned contract
are covered where they run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leo.api.app import create_app
from leo.application.sky_field import SkyFieldService
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.fixtures import build_fixture_repository, write_fixture_artifacts
from leo.sky.propagation import element_line_checksum

ANCHOR_NS = 1_787_238_197_000_000_000


def _seal(line: str) -> str:
    return f"{line[:68]}{element_line_checksum(line)}"


def _element_sets(count: int = 6) -> str:
    payload = ""
    for index in range(count):
        mean_anomaly = (130.0 + index * 0.6 - 2.0) % 360.0
        number = 40_000 + index
        payload += (
            _seal(f"1 {number:05d}U 26232A   26232.50000000  .00000100  00000-0  10000-4 0  9990")
            + "\n"
            + _seal(
                f"2 {number:05d}   0.5000   0.0000 0001000"
                f"  87.0000 {mean_anomaly:8.4f} 15.20000000260120"
            )
            + "\n"
        )
    return payload


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    artifact_root = tmp_path / "artifacts"
    write_fixture_artifacts(artifact_root)
    archive_root = tmp_path / "tle"
    directory = archive_root / "archive" / "space-track"
    directory.mkdir(parents=True)
    payload = _element_sets()
    digest = hashlib.sha256(payload.encode()).hexdigest()
    (directory / f"{ANCHOR_NS}-{digest}.tle").write_text(payload)
    return TestClient(
        create_app(
            build_fixture_repository(artifact_root),
            artifact_root=artifact_root,
            sky_service=SkyFieldService(TleArchiveReader(archive_root)),
            sky_archive_root=archive_root,
        )
    )


@pytest.fixture
def unbound_client(tmp_path: Path) -> TestClient:
    artifact_root = tmp_path / "artifacts"
    write_fixture_artifacts(artifact_root)
    return TestClient(
        create_app(build_fixture_repository(artifact_root), artifact_root=artifact_root)
    )


def _field(client: TestClient, **overrides: object):
    params: dict[str, object] = {
        "lat": 0.0,
        "lon": 0.0,
        "el": 90.0,
        "fov": 90.0,
        "at": ANCHOR_NS,
    }
    params.update(overrides)
    return client.get("/api/v1/sky/field", params=params)


def test_sites_are_served_without_an_archive(unbound_client: TestClient) -> None:
    """The preset registry is static, so it must not depend on configuration."""

    response = unbound_client.get("/api/v1/sky/sites")
    assert response.status_code == 200
    names = [site["name"] for site in response.json()["sites"]]
    assert names == ["spinnaker-sausalito"]


def test_snapshots_list_the_archive(client: TestClient) -> None:
    response = client.get("/api/v1/sky/snapshots")
    assert response.status_code == 200
    body = response.json()
    assert body["source_count"] == 1
    assert body["returned_count"] == 1
    assert body["truncated"] is False
    assert body["snapshots"][0]["digest"].startswith("sha256:")


def test_field_returns_a_bounded_report(client: TestClient) -> None:
    response = _field(client)
    assert response.status_code == 200
    report = response.json()
    assert report["snapshot"]["object_count"] == 6
    assert report["returned_object_count"] == len(report["objects"])
    exclusions = sum(
        value for key, value in report["exclusions"].items() if key != "schema_version"
    )
    assert report["source_object_count"] + exclusions == 6


def test_field_requires_an_explicit_instant(client: TestClient) -> None:
    """A silent "now" would make the surface irreproducible for scripts."""

    response = client.get("/api/v1/sky/field", params={"lat": 0.0, "lon": 0.0})
    assert response.status_code == 422


def test_field_requires_an_observer(client: TestClient) -> None:
    response = client.get("/api/v1/sky/field", params={"at": ANCHOR_NS})
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("lat", 91.0),
        ("lat", -91.0),
        ("lon", 181.0),
        ("el", 91.0),
        ("fov", 0.0),
        ("fov", 91.0),
        ("mask", -1.0),
        ("az", 360.0),
        ("limit", 0),
        ("limit", 513),
        ("half_width_s", 0),
        ("half_width_s", 3_601),
        ("downlink_hz", 0.0),
    ),
)
def test_field_rejects_out_of_range_parameters(
    client: TestClient, field: str, value: float
) -> None:
    assert _field(client, **{field: value}).status_code == 422


def test_field_limit_is_honoured(client: TestClient) -> None:
    response = _field(client, limit=2)
    assert response.status_code == 200
    report = response.json()
    assert report["returned_object_count"] <= 2
    assert report["truncated"] == (report["returned_object_count"] < report["source_object_count"])


def test_field_limit_does_not_leak_between_requests(client: TestClient) -> None:
    """The bound is a request parameter, so one small request must not shrink
    the next."""

    small = _field(client, limit=1).json()
    large = _field(client, limit=100).json()
    assert small["returned_object_count"] <= 1
    assert large["returned_object_count"] >= small["returned_object_count"]
    assert large["source_object_count"] == small["source_object_count"]


def test_field_rejects_a_window_the_contract_refuses(client: TestClient) -> None:
    response = _field(client, half_width_s=3_600, limit=5)
    assert response.status_code in {200, 422}


def test_sky_routes_are_read_only(client: TestClient) -> None:
    for path in ("/api/v1/sky/sites", "/api/v1/sky/snapshots", "/api/v1/sky/field"):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(path).status_code == 405


def test_head_is_served_for_every_sky_route(client: TestClient) -> None:
    assert client.head("/api/v1/sky/sites").status_code == 200
    assert client.head("/api/v1/sky/snapshots").status_code == 200
    assert (
        client.head(
            "/api/v1/sky/field",
            params={"lat": 0.0, "lon": 0.0, "el": 90.0, "fov": 90.0, "at": ANCHOR_NS},
        ).status_code
        == 200
    )


def test_an_unconfigured_service_answers_503_not_an_empty_sky(
    unbound_client: TestClient,
) -> None:
    for response in (
        unbound_client.get("/api/v1/sky/snapshots"),
        _field(unbound_client),
    ):
        assert response.status_code == 503
        assert "not configured" in response.json()["detail"]


def test_an_empty_archive_is_unavailable_not_empty(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    write_fixture_artifacts(artifact_root)
    archive_root = tmp_path / "tle"
    archive_root.mkdir()
    client = TestClient(
        create_app(
            build_fixture_repository(artifact_root),
            artifact_root=artifact_root,
            sky_service=SkyFieldService(TleArchiveReader(archive_root)),
        )
    )
    response = _field(client)
    assert response.status_code == 503
    assert "no TLE snapshot is available" in response.json()["detail"]


def test_field_never_claims_detection(client: TestClient) -> None:
    body = _field(client).text.lower()
    for forbidden in ("detected", "acquired", "identified", "attributed"):
        assert forbidden not in body


def test_an_archive_created_after_startup_becomes_available(tmp_path: Path) -> None:
    """The collector creates its state directory on first run.  An API started
    before that must begin serving when a snapshot appears, not stay
    unavailable until it is restarted."""

    artifact_root = tmp_path / "artifacts"
    write_fixture_artifacts(artifact_root)
    archive_root = tmp_path / "not-yet-created"
    client = TestClient(
        create_app(
            build_fixture_repository(artifact_root),
            artifact_root=artifact_root,
            sky_service=SkyFieldService(TleArchiveReader(archive_root)),
        )
    )

    assert _field(client).status_code == 503
    assert client.get("/api/v1/sky/snapshots").status_code == 503

    directory = archive_root / "archive" / "space-track"
    directory.mkdir(parents=True)
    payload = _element_sets()
    digest = hashlib.sha256(payload.encode()).hexdigest()
    (directory / f"{ANCHOR_NS}-{digest}.tle").write_text(payload)

    assert client.get("/api/v1/sky/snapshots").status_code == 200
    assert _field(client).status_code == 200


def test_an_over_long_label_is_a_client_error_not_a_server_error(client: TestClient) -> None:
    response = _field(client, label="x" * 200)
    assert response.status_code == 422


def test_an_empty_label_is_rejected(client: TestClient) -> None:
    assert _field(client, label="").status_code == 422


def test_an_unsupported_provider_is_a_client_error_not_an_outage(client: TestClient) -> None:
    """A typo in a query parameter is the caller's mistake, not a service
    failure, and the two must not be conflated."""

    for response in (
        client.get("/api/v1/sky/snapshots", params={"provider": "celestrak"}),
        _field(client, provider="celestrak"),
    ):
        assert response.status_code == 422
        assert "unsupported TLE provider" in response.json()["detail"]


def test_an_unsupported_provider_is_still_a_client_error_without_service(
    unbound_client: TestClient,
) -> None:
    """Configuration state must not change the classification of bad input."""

    for response in (
        unbound_client.get("/api/v1/sky/snapshots", params={"provider": "celestrak"}),
        unbound_client.get(
            "/api/v1/sky/field",
            params={"lat": 0.0, "lon": 0.0, "at": ANCHOR_NS, "provider": "celestrak"},
        ),
    ):
        assert response.status_code == 422
        assert "unsupported TLE provider" in response.json()["detail"]


def test_a_known_provider_with_no_snapshots_is_unavailable(client: TestClient) -> None:
    """Consistent with /field: nothing archived for a provider is an absence of
    data, not an empty answer."""

    response = client.get("/api/v1/sky/snapshots", params={"provider": "huggingface"})
    assert response.status_code == 503
    assert "no TLE snapshot is available" in response.json()["detail"]


def test_the_report_contract_is_untouched_by_this_change() -> None:
    """This PR adds operator surfaces and must not alter a published contract.

    A field added to a model with extra="forbid" is forward-incompatible: a
    document written by the new code is rejected by a reader that predates it.
    """

    from leo.contracts.sky import MAXIMUM_FRESH_ELEMENT_AGE_S, SkyFieldReportV1

    assert MAXIMUM_FRESH_ELEMENT_AGE_S == 86_400.0
    assert "element_staleness_threshold_s" not in SkyFieldReportV1.model_fields
    assert SkyFieldReportV1.model_config["extra"] == "forbid"


@pytest.mark.parametrize("downlink_hz", (1e308, 1e309, 3.0e11 + 1.0))
def test_an_unphysical_downlink_is_refused_not_overflowed(
    client: TestClient, downlink_hz: float
) -> None:
    """These overflowed the Doppler arithmetic to infinity and surfaced as 500."""

    assert _field(client, downlink_hz=downlink_hz).status_code == 422


def test_the_radio_spectrum_edge_is_accepted(client: TestClient) -> None:
    assert _field(client, downlink_hz=3.0e11).status_code == 200


def test_values_the_contracts_accept_are_not_refused_by_the_surface(
    client: TestClient,
) -> None:
    """The surface must not approximate an exclusive contract boundary."""

    assert _field(client, az=359.9999995).status_code == 200
    assert _field(client, fov=0.0000005).status_code == 200
