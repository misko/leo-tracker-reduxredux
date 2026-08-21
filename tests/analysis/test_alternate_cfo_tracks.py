from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from leo.analysis.standard.alternate_tracks import (
    build_alternate_cfo_tracks,
    default_alternate_cfo_config,
    render_alternate_cfo_tracks_png,
)
from leo.analysis.standard.codecs import decode_standard_product
from leo.analysis.standard.products import ALTERNATE_CFO_TRACK_BANK_PRODUCT
from leo.contracts.digests import canonical_digest

_FROZEN = Path("corpus/goldens/trial-132-standard-v3-one-second-frozen.json")


def _pilot() -> dict:
    frozen = json.loads(_FROZEN.read_bytes())
    return frozen["documents"]["standard.pilot-scan"]


def test_alternate_bank_is_strict_bounded_and_upstream_digest_bound() -> None:
    pilot = _pilot()
    config = default_alternate_cfo_config()
    first = build_alternate_cfo_tracks(pilot, pilot_digest=canonical_digest(pilot), config=config)
    normalized = decode_standard_product(
        ALTERNATE_CFO_TRACK_BANK_PRODUCT, first.model_dump(mode="json")
    )
    assert normalized == first.model_dump(mode="json")
    assert first.returned_track_count <= 8
    assert first.detected_track_count <= 16
    assert first.source_point_count <= 25_000
    assert all(track.status == "research_only" for track in first.tracks)

    malformed = deepcopy(normalized)
    malformed["tracks"][0]["undeclared"] = True
    with pytest.raises(ValueError):
        decode_standard_product(ALTERNATE_CFO_TRACK_BANK_PRODUCT, malformed)
    digest_drift = deepcopy(normalized)
    digest_drift["configuration"]["residual_gate_hz"] += 1
    with pytest.raises(ValueError, match="configuration digest"):
        decode_standard_product(ALTERNATE_CFO_TRACK_BANK_PRODUCT, digest_drift)

    substituted = deepcopy(pilot)
    substituted["detections"][0]["candidates"][0]["scores"][0]["margin"] += 0.001
    second = build_alternate_cfo_tracks(
        substituted, pilot_digest=canonical_digest(substituted), config=config
    )
    assert second.pilot_scan_content_digest != first.pilot_scan_content_digest
    assert canonical_digest(second.model_dump(mode="json")) != canonical_digest(normalized)


def test_alternate_png_bytes_are_deterministic_and_bounded() -> None:
    pilot = _pilot()
    bank = build_alternate_cfo_tracks(
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
        build_alternate_cfo_tracks(pilot, pilot_digest=canonical_digest(pilot), config=config)
