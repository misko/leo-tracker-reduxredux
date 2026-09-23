"""Vertical evidence checks for the blind adaptive TLE-position sidecar."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from leo.analysis.adaptive_tle_position import score_point
from leo.analysis.adaptive_tle_prediction import (
    AdaptiveTrackInput,
    AdaptiveTrackStateBank,
    ReceiverPoint,
    RegionalTrackPredictionEvaluator,
)
from leo.api.adaptive_tle_position import adaptive_tle_position_router
from leo.contracts.adaptive_tle_position import (
    AdaptiveTleAccountingV1,
    AdaptiveTleCandidateV1,
    AdaptiveTlePositionDocumentV1,
    AdaptiveTlePriorResultV1,
    AdaptiveTleRegionV1,
)
from leo.presentation import adaptive_tle_position as presentation
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStore

DIGEST = "sha256:" + "a" * 64


def _candidate() -> AdaptiveTleCandidateV1:
    return AdaptiveTleCandidateV1(
        latitude_deg=38.0,
        longitude_deg=-122.0,
        east_km=12.5,
        north_km=-12.5,
        spacing_km=12.5,
        capped_weighted_rmse_hz=185.0,
        uncapped_weighted_rmse_hz=190.0,
        matched_track_count=34,
        unmatched_track_count=0,
        qualifying_observation_count=720,
    )


def _prior(name: str) -> AdaptiveTlePriorResultV1:
    return AdaptiveTlePriorResultV1(
        name=name,  # type: ignore[arg-type]
        region=AdaptiveTleRegionV1(center_latitude_deg=38.0, center_longitude_deg=-122.0),
        search_complete=False,
        stop_reason="point-budget-reached",
        accounting=AdaptiveTleAccountingV1(
            reconstructed_track_count=34,
            eligible_track_count=34,
            eligible_observation_count=720,
            evaluated_point_count=400,
            finest_evaluated_point_count=216,
            deferred_cell_count=8,
            runtime_ms=12_000,
        ),
        selected=_candidate(),
        finest=_candidate(),
    )


def _document(*, state: str = "diagnostic") -> AdaptiveTlePositionDocumentV1:
    return AdaptiveTlePositionDocumentV1(
        session_id="scan-evidence",
        input_manifest_sha256=DIGEST,
        analysis_manifest_sha256=DIGEST,
        configuration_sha256=DIGEST,
        evidence_sha256=DIGEST,
        state=state,  # type: ignore[arg-type]
        priors=(_prior("sacramento"), _prior("reno")) if state == "diagnostic" else (),
        reasons=() if state == "diagnostic" else ("no-eligible-three-second-tracks",),
        diagnostics={
            "evaluated_points": {
                "sacramento": [
                    {"east_km": 12.5, "north_km": -12.5, "capped_weighted_rmse_hz": 185.0}
                ],
                "reno": [
                    {"east_km": 12.5, "north_km": -12.5, "capped_weighted_rmse_hz": 185.0}
                ],
            }
        } if state == "diagnostic" else {},
    )


def test_renderer_decodes_and_labeled_insufficiency_contains_reason(monkeypatch) -> None:
    image = presentation.render_adaptive_tle_position(_document())
    with Image.open(BytesIO(image)) as decoded:
        decoded.load()
        assert decoded.format == "PNG"
        assert decoded.size == (1560, 720)

    messages: list[str] = []

    class Axis:
        def axis(self, *_args, **_kwargs) -> None:
            pass

        def text(self, *_args, **kwargs) -> None:
            messages.append(kwargs["s"] if "s" in kwargs else _args[2])

    class Figure:
        def __init__(self, *_args, **_kwargs) -> None:
            self.axes = (Axis(), Axis())

        def subplots(self, *_args, **_kwargs):
            return self.axes

        def suptitle(self, *_args, **_kwargs) -> None:
            pass

        def text(self, *_args, **_kwargs) -> None:
            pass

        def savefig(self, stream, **_kwargs) -> None:
            stream.write(b"rendered")

    monkeypatch.setattr(presentation, "Figure", Figure)
    presentation.render_adaptive_tle_position(_document(state="insufficient"))
    assert messages == [
        "State: insufficient\nNo qualified position selection was published.\n"
        "no-eligible-three-second-tracks\nKnown position was not used for inference."
    ]


def test_api_serves_the_rendered_document_and_rejects_tampered_map(tmp_path) -> None:
    document = _document()
    image = presentation.render_adaptive_tle_position(document)
    writer = AdaptiveTlePositionStore(tmp_path, read_only=False)
    manifest = writer.publish(document, image)
    app = FastAPI()
    app.include_router(adaptive_tle_position_router(AdaptiveTlePositionStore(tmp_path)))
    client = TestClient(app)
    status_url = "/api/v1/scanner/tracking/scan-evidence/adaptive-tle-position"
    status = client.get(status_url)
    assert status.status_code == 200
    assert status.json()["manifest"]["document_sha256"] == manifest.document_sha256
    assert status.json()["manifest"]["document"]["input_manifest_sha256"] == DIGEST
    map_url = status_url + "/map.png"
    response = client.get(map_url, params={"sha256": manifest.artifacts[0].sha256})
    assert response.status_code == 200
    assert response.content == image
    assert "sha256:" + sha256(response.content).hexdigest() == manifest.artifacts[0].sha256
    with Image.open(BytesIO(response.content)) as decoded:
        decoded.verify()

    (tmp_path / "scanner-adaptive-tle-position-v1" / "scan-evidence" / "map.png").write_bytes(
        image + b"tamper"
    )
    assert client.get(map_url, params={"sha256": manifest.artifacts[0].sha256}).status_code == 409


def test_horizon_prefilter_retains_an_unmatched_track_in_the_all_track_objective() -> None:
    """A below-horizon track is a capped penalty, never an omitted denominator term."""
    times = np.asarray([0.0, 0.7, 1.5, 2.2, 3.1, 3.8])
    node_indices = np.unique(
        np.concatenate((np.floor(times + 507.0), np.floor(times + 507.0) + 1)).astype(int)
    )
    source = AdaptiveTrackInput(
        track_id="below-horizon",
        observation_ids=tuple(f"obs-{index}" for index in range(len(times))),
        times_s=times,
        measured_hz=np.zeros(len(times)),
        training_mask=np.asarray([True, True, True, False, False, False]),
    )

    def bank(*, exact_z: float, coarse_z: float) -> AdaptiveTrackStateBank:
        exact_position = np.tile(np.asarray([1.0, 0.0, exact_z]), (1, 1, len(times), 1))
        coarse_position = np.tile(
            np.asarray([1.0, 0.0, coarse_z]), (1, len(node_indices), 1)
        )
        return AdaptiveTrackStateBank(
            source=source,
            candidate_ids=np.asarray([42]),
            position_km=exact_position,
            velocity_km_s=np.zeros_like(exact_position),
            coarse_position_km=coarse_position,
            coarse_node_indices=node_indices,
            coarse_candidate_rows=np.asarray([0]),
        )

    def point(_east: float, _north: float) -> ReceiverPoint:
        return ReceiverPoint(ecef_km=np.zeros(3), up=np.asarray([0.0, 0.0, 1.0]))
    all_below = RegionalTrackPredictionEvaluator(
        (bank(exact_z=-0.01, coarse_z=-0.01),), point, taus_s=np.asarray([0.0])
    )
    below_score = score_point(0.0, 0.0, all_below(0.0, 0.0))
    assert below_score.matched_track_count == 0
    assert below_score.unmatched_track_count == 1
    assert below_score.weighted_mse_hz2 == 800.0**2

    # The conservative -0.1° coarse threshold keeps a near-horizon candidate
    # for the exact visibility test rather than silently pruning it.
    near_horizon = RegionalTrackPredictionEvaluator(
        (bank(exact_z=0.01, coarse_z=-0.0005),), point, taus_s=np.asarray([0.0])
    )
    visible = tuple(near_horizon(0.0, 0.0))
    assert len(visible) == 1
    assert visible[0].candidate_ids.tolist() == [42]
    assert visible[0].visible.tolist() == [True]

    zero_candidate = AdaptiveTrackStateBank(
        source=source,
        candidate_ids=np.empty(0, dtype=int),
        position_km=np.empty((0, 1, len(times), 3)),
        velocity_km_s=np.empty((0, 1, len(times), 3)),
        coarse_position_km=np.empty((0, len(node_indices), 3)),
        coarse_node_indices=node_indices,
        coarse_candidate_rows=np.empty(0, dtype=int),
    )
    zero_score = score_point(
        0.0,
        0.0,
        RegionalTrackPredictionEvaluator((zero_candidate,), point, taus_s=np.asarray([0.0]))(
            0.0, 0.0
        ),
    )
    assert zero_score.matched_track_count == 0
    assert zero_score.unmatched_track_count == 1
    assert zero_score.weighted_mse_hz2 == 800.0**2
