from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path

import pytest

from leo.analysis.standard.alternate_tracks import (
    build_alternate_cfo_tracks,
    build_ranked_residual_hough_cfo_tracks,
    build_residual_hough_cfo_tracks,
    default_alternate_cfo_config,
    default_alternate_cfo_display_config,
    default_alternate_cfo_hough_v1_config,
    render_alternate_cfo_tracks_png,
)
from leo.analysis.standard.codecs import decode_standard_product
from leo.analysis.standard.products import (
    ALTERNATE_CFO_TRACK_BANK_PRODUCT,
    ALTERNATE_CFO_TRACK_BANK_V1_PRODUCT,
)
from leo.contracts.alternate_cfo_tracks import RankedCandidateResidualHoughConfigV3
from leo.contracts.digests import canonical_digest

_FROZEN = Path("corpus/goldens/trial-132-standard-v3-one-second-frozen.json")


def _pilot() -> dict:
    frozen = json.loads(_FROZEN.read_bytes())
    return frozen["documents"]["standard.pilot-scan"]


def test_alternate_bank_is_strict_bounded_and_upstream_digest_bound() -> None:
    pilot = _pilot()
    config = default_alternate_cfo_config()
    first = build_residual_hough_cfo_tracks(
        pilot, pilot_digest=canonical_digest(pilot), config=config
    )
    normalized = decode_standard_product(
        ALTERNATE_CFO_TRACK_BANK_PRODUCT, first.model_dump(mode="json")
    )
    assert normalized == first.model_dump(mode="json")
    assert first.returned_track_count <= 8
    assert first.initial_track_count <= 16
    assert first.detected_track_count <= 128
    assert first.source_point_count <= 25_000
    assert all(track.status == "research_only" for track in first.tracks)

    malformed = deepcopy(normalized)
    malformed["tracks"][0]["undeclared"] = True
    with pytest.raises(ValueError):
        decode_standard_product(ALTERNATE_CFO_TRACK_BANK_PRODUCT, malformed)
    digest_drift = deepcopy(normalized)
    digest_drift["configuration"]["minimum_split_gain"] += 1
    with pytest.raises(ValueError, match="configuration digest"):
        decode_standard_product(ALTERNATE_CFO_TRACK_BANK_PRODUCT, digest_drift)

    substituted = deepcopy(pilot)
    substituted["detections"][0]["candidates"][0]["scores"][0]["margin"] += 0.001
    second = build_residual_hough_cfo_tracks(
        substituted, pilot_digest=canonical_digest(substituted), config=config
    )
    assert second.pilot_scan_content_digest != first.pilot_scan_content_digest
    assert canonical_digest(second.model_dump(mode="json")) != canonical_digest(normalized)


def test_display_policy_uses_contract_ceiling_without_expanding_science_policy() -> None:
    science = default_alternate_cfo_config()
    display = default_alternate_cfo_display_config()

    assert science.initial_hough.maximum_published_tracks == 8
    assert display.initial_hough.maximum_published_tracks == 16
    assert (
        display.initial_hough.maximum_published_tracks
        == display.initial_hough.maximum_detected_tracks
    )
    assert display.model_copy(update={"initial_hough": science.initial_hough}) == science


def test_alternate_png_bytes_are_deterministic_and_bounded() -> None:
    pilot = _pilot()
    bank = build_residual_hough_cfo_tracks(
        pilot,
        pilot_digest=canonical_digest(pilot),
        config=default_alternate_cfo_config(),
    )
    first = render_alternate_cfo_tracks_png(pilot, bank)
    second = render_alternate_cfo_tracks_png(pilot, bank)
    assert first == second
    assert first.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(first) < 4 * 1024 * 1024


def test_alternate_input_inventory_fails_closed_above_bound() -> None:
    pilot = _pilot()
    config = default_alternate_cfo_config().model_copy(update={"maximum_input_points": 1})
    with pytest.raises(ValueError, match="inventory exceeds"):
        build_residual_hough_cfo_tracks(pilot, pilot_digest=canonical_digest(pilot), config=config)


def test_ranked_v3_preserves_dense_source_and_discloses_bounded_selection() -> None:
    pilot = _pilot()
    config = RankedCandidateResidualHoughConfigV3(
        segmentation=default_alternate_cfo_config(),
        maximum_candidates_per_probe=1,
    )

    bank = build_ranked_residual_hough_cfo_tracks(
        pilot,
        pilot_digest=canonical_digest(pilot),
        config=config,
    )

    assert bank.schema_version == 3
    assert bank.selected_point_count <= bank.source_point_count
    assert bank.omitted_point_count == bank.source_point_count - bank.selected_point_count
    assert bank.configuration.selection_rule == "lowest-rank-prefix-per-independent-probe"


def test_v1_bank_remains_decodable_without_becoming_the_current_product() -> None:
    pilot = _pilot()
    bank = build_alternate_cfo_tracks(
        pilot,
        pilot_digest=canonical_digest(pilot),
        config=default_alternate_cfo_hough_v1_config(),
    )
    decoded = decode_standard_product(
        ALTERNATE_CFO_TRACK_BANK_V1_PRODUCT, bank.model_dump(mode="json")
    )
    assert decoded["algorithm_version"] == "alternate-cfo-hough-v1"
    assert ALTERNATE_CFO_TRACK_BANK_PRODUCT.schema_version == 2


def test_residual_hough_keeps_two_simultaneous_linear_components() -> None:
    detections = []
    for index in range(24):
        time_s = index * 0.1
        frequencies = (
            1_000.0 * time_s + 12.0 * math.sin(index),
            -1_200.0 * time_s + 50_000.0 + 10.0 * math.cos(index),
        )
        detections.append(
            {
                "sample_start": index * 250_000,
                "time_s": time_s,
                "candidates": [
                    {
                        "rank": rank,
                        "scores": [
                            {
                                "method": "glrt64",
                                "tracking_cfo_hz": frequency,
                                "exact_score": 1.0,
                                "control_score": 0.1,
                                "margin": 0.9,
                            }
                        ],
                    }
                    for rank, frequency in enumerate(frequencies, start=1)
                ],
            }
        )
    pilot = {"detections": detections}
    bank = build_residual_hough_cfo_tracks(
        pilot,
        pilot_digest=canonical_digest(pilot),
        config=default_alternate_cfo_config(),
    )

    assert bank.initial_track_count == 2
    assert bank.returned_track_count == 2
    assert all(track.acceleration_hz_per_s2 == 0.0 for track in bank.tracks)
    assert bank.tracks[0].start_s < bank.tracks[1].end_s
    assert bank.tracks[1].start_s < bank.tracks[0].end_s
    assert sorted(round(track.slope_hz_per_s, -1) for track in bank.tracks) == [-1_200, 1_000]
