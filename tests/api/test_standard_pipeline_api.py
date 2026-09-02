from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from leo.api import create_app
from leo.application.standard_presentation import (
    StandardPresentationNotReady,
    _select_waterfall_grid,
)
from leo.presentation.fixtures import build_fixture_repository, write_fixture_artifacts
from leo.presentation.standard_fixtures import build_standard_fixture_repository
from leo.presentation.standard_pipeline import (
    StandardPlotViewV2,
    StandardSourceTypeV2,
    StandardStaleReasonCodeV2,
    StandardStateReasonV2,
    StandardViewKindV2,
    standard_source_extrema_proof_v2,
)


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
    standard = build_standard_fixture_repository()
    app = create_app(
        build_fixture_repository(artifacts),
        artifact_root=artifacts,
        standard_repository=standard,
        research_repository=standard,
    )
    routes = [
        route
        for included in app.routes
        for route in getattr(getattr(included, "original_router", None), "routes", ())
        if isinstance(route, APIRoute) and route.path.startswith("/api/v2/")
    ]
    assert len(routes) == 22
    assert all(route.methods == {"GET", "HEAD"} for route in routes)

    client = TestClient(app)
    path = "/api/v2/recordings/T1/standard-subjects"
    assert client.get(path).status_code == 404
    response = client.get(path, params={"include_test": True})
    assert response.status_code == 200
    assert response.json()["eligibility"]["evidence_only"] is True
    assert response.json()["eligibility"]["capture_committed"] is True
    assert response.json()["eligibility"]["capture_healthy"] is True
    assert all(row["ordinary_current"] is False for row in response.json()["rows"])
    assert {row["state"] for row in response.json()["rows"]} == {"complete"}
    audit = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/replay-audit",
        params={"include_test": True},
    )
    assert audit.status_code == 200
    assert audit.json()["rows"][0] == {
        "receiver_path_id": "radio0:rx0",
        "branch_id": f"sha256:{'2' * 64}",
        "alias_index": 0,
        "tier": "automatic",
        "automatic_correction_eligible": True,
        "geometry_display_eligible": True,
        "evaluated_probe_count": 304,
        "evaluated_block_count": 9,
        "block_coverage_ratio": 1.0,
        "median_block_corrected_margin": 0.005088,
        "harmful_block_count": 2,
        "maximum_consecutive_harmful_blocks": 1,
        "reasons": [
            "geometry and replay coverage passed; corrected-margin and harmful-block metrics "
            "are audit-only",
            "harmful-block metrics are audit-only: count=2, run=1",
        ],
        "retained_in_final": True,
    }
    gates = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/track-gates",
        params={"include_test": True},
    )
    assert gates.status_code == 200
    assert gates.json()["stages"][0]["rows"][0]["disposition"] == "passed"
    assert gates.json()["stages"][0]["rows"][0]["gates"] == [
        {
            "gate_key": "absolute-margin",
            "label": "Corrected margin",
            "value": "0.005088",
            "criterion": "audit only; never vetoes V4",
            "verdict": "audit",
        },
        {
            "gate_key": "harmful-blocks",
            "label": "Harmful blocks",
            "value": "2 (run 1)",
            "criterion": "audit only; never vetoes V4",
            "verdict": "audit",
        },
    ]
    assert client.post(path, json={"promote": True}).status_code == 405
    research_path = "/api/v2/recordings/T1/research-subjects"
    assert client.get(research_path).status_code == 404
    research = client.get(research_path, params={"include_test": True})
    assert research.status_code == 200
    assert research.json()["rows"] == response.json()["rows"]


def test_persisted_dealiased_and_final_pngs_are_served_without_rendering(
    tmp_path: Path,
) -> None:
    class Repository:
        def __init__(self) -> None:
            self.delegate = build_standard_fixture_repository()
            self.requests: list[tuple[str, str, str]] = []

        def __getattr__(self, name: str):
            return getattr(self.delegate, name)

        def subject_named_png_artifact(
            self, session_id: str, subject_id: str, artifact_name: str
        ) -> bytes | None:
            self.requests.append((session_id, subject_id, artifact_name))
            return b"\x89PNG\r\n\x1a\n" + artifact_name.encode()

    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    repository = Repository()
    client = TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_repository=repository,  # type: ignore[arg-type]
        )
    )
    base = "/api/v2/recordings/T1/standard-subjects/path:radio0:rx0/artifacts"

    for name in (
        "cfo-raw",
        "cfo-dealiased",
        "cfo-final",
        "cfo-alternate",
        "trajectory-accounting",
        "pilot-doppler",
        "pilot-carrier-tracking",
        "pilot-segment-rates",
        "full-capture-glrt20ms",
        "glrt-epoch-timing",
        "glrt-epoch-rate",
    ):
        response = client.get(f"{base}/{name}.png")
        assert response.status_code == 200
        assert response.content == b"\x89PNG\r\n\x1a\n" + name.encode()
        assert response.headers["x-leo-png-cache"] == "artifact"
        assert "immutable" in response.headers["cache-control"]
    paired_response = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/artifacts/"
        "pss-glrt-frame-comparison.png"
    )
    assert paired_response.status_code == 200
    assert paired_response.content == b"\x89PNG\r\n\x1a\npss-glrt-frame-comparison"
    assert repository.requests == [
        ("T1", "path:radio0:rx0", "cfo-raw"),
        ("T1", "path:radio0:rx0", "cfo-dealiased"),
        ("T1", "path:radio0:rx0", "cfo-final"),
        ("T1", "path:radio0:rx0", "cfo-alternate"),
        ("T1", "path:radio0:rx0", "trajectory-accounting"),
        ("T1", "path:radio0:rx0", "pilot-doppler"),
        ("T1", "path:radio0:rx0", "pilot-carrier-tracking"),
        ("T1", "path:radio0:rx0", "pilot-segment-rates"),
        ("T1", "path:radio0:rx0", "full-capture-glrt20ms"),
        ("T1", "path:radio0:rx0", "glrt-epoch-timing"),
        ("T1", "path:radio0:rx0", "glrt-epoch-rate"),
        ("T1", "pair:radio0:radio1", "pss-glrt-frame-comparison"),
    ]
    assert client.get(f"{base}/unknown.png").status_code == 422


def test_paired_hough_gallery_can_use_child_pngs_without_a_paired_artifact(
    tmp_path: Path,
) -> None:
    class Repository:
        def __init__(self) -> None:
            self.delegate = build_standard_fixture_repository()

        def __getattr__(self, name: str):
            return getattr(self.delegate, name)

        def subject_named_png_artifact(
            self, session_id: str, subject_id: str, artifact_name: str
        ) -> bytes | None:
            if (
                session_id == "T1"
                and subject_id.startswith("path:")
                and artifact_name == "cfo-alternate"
            ):
                return b"\x89PNG\r\n\x1a\n" + subject_id.encode()
            return None

    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    client = TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_repository=Repository(),  # type: ignore[arg-type]
        )
    )

    detail = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1",
        params={"include_test": True},
    )
    assert detail.status_code == 200
    child_ids = [item["subject_id"] for item in detail.json()["receiver_path_expansions"]]
    assert child_ids == [
        "path:radio0:rx0",
        "path:radio0:rx1",
        "path:radio1:rx0",
        "path:radio1:rx1",
    ]
    for child_id in child_ids:
        response = client.get(
            f"/api/v2/recordings/T1/standard-subjects/{child_id}/artifacts/cfo-alternate.png"
        )
        assert response.status_code == 200
        assert response.content == b"\x89PNG\r\n\x1a\n" + child_id.encode()
    paired = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/artifacts/cfo-alternate.png"
    )
    assert paired.status_code == 404


def test_digest_verified_investigation_png_is_served_and_tamper_fails(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    directory = artifacts / "investigations" / "T1"
    directory.mkdir(parents=True)
    png = b"\x89PNG\r\n\x1a\nreviewed-upper-edge"
    image = directory / "radio1-rx0-wide.png"
    image.write_bytes(png)
    manifest = {
        "schema_version": 1,
        "session_id": "T1",
        "title": "Original vs widened upper-edge CFO search",
        "status": "exploratory",
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "images": [
            {
                "image_id": "radio1-rx0-wide",
                "subject_id": "path:radio1:rx0",
                "label": "Widened upper-edge search",
                "analysis_variant": "wide-fine-upper-edge",
                "relative_path": image.name,
                "byte_size": len(png),
                "digest": f"sha256:{hashlib.sha256(png).hexdigest()}",
            }
        ],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    client = TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_repository=build_standard_fixture_repository(),
        )
    )

    gallery = client.get("/api/v2/recordings/T1/standard-investigations")
    assert gallery.status_code == 200
    assert gallery.json()["images"][0]["subject_id"] == "path:radio1:rx0"
    response = client.get("/api/v2/recordings/T1/standard-investigations/radio1-rx0-wide.png")
    assert response.status_code == 200
    assert response.content == png
    assert response.headers["x-leo-png-cache"] == "investigation-artifact"

    image.write_bytes(b"\x89PNG\r\n\x1a\ntampered")
    assert (
        client.get("/api/v2/recordings/T1/standard-investigations/radio1-rx0-wide.png").status_code
        == 503
    )


def test_absent_optional_investigation_is_an_empty_response_not_a_failed_resource(
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    client = TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_repository=build_standard_fixture_repository(),
        )
    )

    response = client.get("/api/v2/recordings/T1/standard-investigations")
    assert response.status_code == 204
    assert response.content == b""


def test_in_progress_standard_presentation_is_a_conflict_not_an_outage(
    tmp_path: Path,
) -> None:
    class NotReadyRepository:
        def subject_hierarchy(self, session_id: str):
            raise StandardPresentationNotReady(
                "Standard analysis is still processing; no sealed image artifacts are available yet"
            )

    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    client = TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_repository=NotReadyRepository(),  # type: ignore[arg-type]
        )
    )

    response = client.get("/api/v2/recordings/in-progress/standard-subjects")
    assert response.status_code == 409
    assert response.json()["detail"].startswith("Standard analysis is still processing")


def test_three_rows_detail_and_lazy_plot_are_bounded(tmp_path: Path) -> None:
    client = _client(tmp_path)
    common = {"include_test": True}
    listing = client.get("/api/v2/recordings/T1/standard-subjects", params=common).json()
    assert [row["label"] for row in listing["rows"]] == [
        "Paired Radio0 + Radio1",
        "Radio0",
        "Radio1",
    ]
    assert listing["rows"][0]["subject_kind"] == "paired"
    assert listing["rows"][0]["derived"] is True
    assert [row["expected_path_count"] for row in listing["rows"]] == [4, 2, 2]
    assert [row["completed_path_count"] for row in listing["rows"]] == [4, 2, 2]

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
        params={**common, "maximum_points": 8},
    ).json()
    assert plot["returned_point_count"] == 8
    assert plot["source_point_count"] == 16
    assert plot["truncated"] is True
    assert plot["time_domain"] == detail["time_domain"]
    assert plot["horizontal_axis"]["axis_id"] == "time"
    assert plot["vertical_axis"]["axis_id"] == "frequency_hz"
    assert plot["receiver_path_ids"] == [
        "radio0:rx0",
        "radio0:rx1",
        "radio1:rx0",
        "radio1:rx1",
    ]
    assert {item["receiver_path_id"] for item in plot["cfo_observations"]} <= set(
        plot["receiver_path_ids"]
    )
    four_lane_plot = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/views/cfo_trajectory",
        params={**common, "maximum_points": 4},
    ).json()
    returned_lanes = {
        *[item["receiver_path_id"] for item in four_lane_plot["cfo_observations"]],
        *[item["receiver_path_id"] for item in four_lane_plot["trajectory_curves"]],
    }
    assert four_lane_plot["returned_point_count"] == 4
    assert returned_lanes == set(four_lane_plot["receiver_path_ids"])
    full_plot = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/views/cfo_trajectory",
        params={**common, "maximum_points": 2048},
    ).json()
    assert plot["horizontal_axis"] == full_plot["horizontal_axis"]
    assert plot["vertical_axis"] == full_plot["vertical_axis"]
    assert (
        client.head(
            "/api/v2/recordings/T1/standard-subjects/radio:radio0/views/glrt64",
            params=common,
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/v2/recordings/T1/standard-subjects/radio:radio0/views/glrt64",
            params={**common, "maximum_points": 2049},
        ).status_code
        == 422
    )


def test_standard_view_pngs_require_registered_analysis_artifacts(tmp_path: Path) -> None:
    client = _client(tmp_path)
    base = "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/views"
    for name, method in (("GET", client.get), ("HEAD", client.head)):
        response = method(
            f"{base}/waterfall.png",
            params={"include_test": True, "maximum_points": 64},
        )
        assert response.status_code == 503
        if name == "GET":
            assert response.json()["detail"] == "Registered Standard PNG is unavailable"

    excluded = client.get(f"{base}/waterfall.png", params={"maximum_points": 64})
    assert excluded.status_code == 404


def test_waterfall_decimation_preserves_a_rectangular_grid_per_receiver_path() -> None:
    source = [
        (lane, float(time), float(frequency), float(time + frequency))
        for lane in ("radio0:rx0", "radio1:rx0")
        for time in range(8)
        for frequency in range(8)
    ]
    cells = _select_waterfall_grid(source, 32)
    lanes = {cell[0] for cell in cells}
    assert len(cells) == 32
    assert len(lanes) == 2
    for lane in lanes:
        lane_cells = [cell for cell in cells if cell[0] == lane]
        times = {cell[1] for cell in lane_cells}
        frequencies = {cell[2] for cell in lane_cells}
        assert len(times) > 1
        assert len(frequencies) > 1
        assert len(lane_cells) == len(times) * len(frequencies)


def test_api_rejects_plot_lane_inventory_that_differs_from_selected_detail(
    tmp_path: Path,
) -> None:
    fixture = build_standard_fixture_repository()

    class InconsistentRepository:
        def subject_hierarchy(self, session_id: str):
            return fixture.subject_hierarchy(session_id)

        def subject_detail(self, session_id: str, subject_id: str):
            return fixture.subject_detail(session_id, subject_id)

        def subject_view(
            self,
            session_id: str,
            subject_id: str,
            view_kind: StandardViewKindV2,
            *,
            maximum_points: int,
        ):
            view = fixture.subject_view(
                session_id,
                subject_id,
                view_kind,
                maximum_points=8,
            )
            assert view is not None
            return view.model_copy(update={"receiver_path_ids": (view.receiver_path_ids[0],)})

        def verify_source_extrema(
            self,
            session_id: str,
            subject_id: str,
            view_kind: StandardViewKindV2,
            proof,
        ) -> bool:
            return fixture.verify_source_extrema(session_id, subject_id, view_kind, proof)

    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    client = TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_repository=InconsistentRepository(),  # type: ignore[arg-type]
        )
    )
    response = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/views/glrt64",
        params={"include_test": True, "maximum_points": 8},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Standard subject view is inconsistent with selected subject"
    )


def test_api_recomputes_source_extrema_against_pre_decimation_data(tmp_path: Path) -> None:
    fixture = build_standard_fixture_repository()

    class ForgedSummaryRepository:
        def subject_hierarchy(self, session_id: str):
            return fixture.subject_hierarchy(session_id)

        def subject_detail(self, session_id: str, subject_id: str):
            return fixture.subject_detail(session_id, subject_id)

        def subject_view(
            self,
            session_id: str,
            subject_id: str,
            view_kind: StandardViewKindV2,
            *,
            maximum_points: int,
        ):
            view = fixture.subject_view(
                session_id,
                subject_id,
                view_kind,
                maximum_points=8,
            )
            assert view is not None
            forged = standard_source_extrema_proof_v2(
                view_kind=view.view_kind,
                receiver_path_ids=view.receiver_path_ids,
                source_artifact_digest=view.source_extrema.source_artifact_digest,
                source_content_digest="f" * 64,
                series=view.series,
            )
            return StandardPlotViewV2.model_validate(
                view.model_copy(
                    update={
                        "source_extrema": forged,
                        "source_point_count": view.returned_point_count,
                        "truncated": False,
                    }
                ).model_dump()
            )

        def verify_source_extrema(
            self,
            session_id: str,
            subject_id: str,
            view_kind: StandardViewKindV2,
            proof,
        ) -> bool:
            return fixture.verify_source_extrema(session_id, subject_id, view_kind, proof)

    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    client = TestClient(
        create_app(
            build_fixture_repository(artifacts),
            artifact_root=artifacts,
            standard_repository=ForgedSummaryRepository(),  # type: ignore[arg-type]
        )
    )
    response = client.get(
        "/api/v2/recordings/T1/standard-subjects/pair:radio0:radio1/views/glrt64",
        params={"include_test": True, "maximum_points": 8},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == ("Standard subject view source-extrema proof is invalid")


def test_api_rejects_crossed_eligibility_and_current_stale_reason_projections(
    tmp_path: Path,
) -> None:
    fixture = build_standard_fixture_repository(source_type=StandardSourceTypeV2.IMPORT)
    hierarchy = fixture.subject_hierarchy("T1")
    assert hierarchy is not None

    class InvalidHierarchyRepository:
        def __init__(self, invalid_hierarchy) -> None:
            self._invalid_hierarchy = invalid_hierarchy

        def subject_hierarchy(self, session_id: str):
            return self._invalid_hierarchy if session_id == "T1" else None

        def subject_detail(self, session_id: str, subject_id: str):
            return fixture.subject_detail(session_id, subject_id)

        def subject_view(
            self,
            session_id: str,
            subject_id: str,
            view_kind: StandardViewKindV2,
            *,
            maximum_points: int,
        ):
            return fixture.subject_view(
                session_id,
                subject_id,
                view_kind,
                maximum_points=maximum_points,
            )

        def verify_source_extrema(
            self,
            session_id: str,
            subject_id: str,
            view_kind: StandardViewKindV2,
            proof,
        ) -> bool:
            return fixture.verify_source_extrema(session_id, subject_id, view_kind, proof)

    def response_for(invalid_hierarchy, name: str):
        artifacts = tmp_path / name
        write_fixture_artifacts(artifacts)
        client = TestClient(
            create_app(
                build_fixture_repository(artifacts),
                artifact_root=artifacts,
                standard_repository=InvalidHierarchyRepository(  # type: ignore[arg-type]
                    invalid_hierarchy
                ),
            )
        )
        return client.get("/api/v2/recordings/T1/standard-subjects")

    crossed_eligibility = hierarchy.eligibility.model_copy(
        update={"reason": "Reviewed TEST corpus is explicit, non-current evidence only"}
    )
    crossed_hierarchy = hierarchy.model_copy(
        update={
            "eligibility": crossed_eligibility,
            "rows": tuple(
                row.model_copy(update={"eligibility": crossed_eligibility})
                for row in hierarchy.rows
            ),
        }
    )
    crossed_response = response_for(crossed_hierarchy, "crossed")
    assert crossed_response.status_code == 503
    assert crossed_response.json()["detail"] == ("Standard subject hierarchy projection is invalid")

    stale_reason = StandardStateReasonV2(
        code=StandardStaleReasonCodeV2.PRODUCT_UNAVAILABLE,
        message="Product is unavailable",
    )
    current_with_stale_reason = hierarchy.rows[0].model_copy(
        update={"state_reasons": (stale_reason,)}
    )
    crossed_state_hierarchy = hierarchy.model_copy(
        update={"rows": (current_with_stale_reason, *hierarchy.rows[1:])}
    )
    state_response = response_for(crossed_state_hierarchy, "state")
    assert state_response.status_code == 503
    assert state_response.json()["detail"] == ("Standard subject hierarchy projection is invalid")


def test_unconfigured_standard_projection_fails_fast_without_touching_v1(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    write_fixture_artifacts(artifacts)
    client = TestClient(create_app(build_fixture_repository(artifacts), artifact_root=artifacts))
    assert client.get("/api/v1/status").status_code == 200
    response = client.get("/api/v2/recordings/T1/standard-subjects")
    assert response.status_code == 503
    assert response.json()["detail"] == "Standard-v2 presentation projection is not configured"
