from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.states import SourceType, SynchronizationMode
from leo.domain.profiles import (
    ProfileDocumentError,
    compile_capture_plan,
    compile_profile_mapping,
    load_profile_revision,
)


def _profile_document() -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "research-2p5m",
        "center_frequency_hz": 1_709_687_500,
        "rf_center_frequency_hz": 11_459_687_500,
        "lnb_lo_hz": 9_750_000_000,
        "starlink_channel": "ch4",
        "starlink_edge": "lower",
        "sample_rate_hz": 2_500_000,
        "bandwidth_hz": 2_500_000,
        "receivers": [0, 1],
        "gain_mode": "manual",
        "gains": [
            {"schema_version": 1, "receiver_id": 0, "gain_db": 30.0},
            {"schema_version": 1, "receiver_id": 1, "gain_db": 31.0},
        ],
        "duration_seconds": "60",
        "refill_samples": 262_144,
        "settle_seconds": "0.5",
        "prime_refills": 1,
        "continuity_policy": "require_contiguous",
        "synchronization_mode": "best_effort",
        "storage_policy": "zstd-128m-v1",
        "tags": ["LIVE"],
    }


def test_profile_revision_is_normalized_content_addressed_and_frozen() -> None:
    first = compile_profile_mapping(_profile_document())
    reordered = dict(reversed(tuple(_profile_document().items())))
    second = compile_profile_mapping(reordered)

    assert first == second
    assert first.revision_digest.startswith("sha256:")
    with pytest.raises(ValidationError, match="frozen"):
        first.profile.sample_rate_hz = 5_000_000  # type: ignore[misc]


def test_profile_digest_changes_with_effective_content() -> None:
    first = compile_profile_mapping(_profile_document())
    changed = _profile_document()
    changed["sample_rate_hz"] = 5_000_000
    second = compile_profile_mapping(changed)

    assert first.revision_digest != second.revision_digest


def test_revision_rejects_a_digest_that_does_not_match() -> None:
    profile = CaptureProfileV1.model_validate(_profile_document())
    with pytest.raises(ValidationError, match="digest does not match"):
        CaptureProfileRevisionV1(
            revision_digest="sha256:" + "0" * 64,
            profile=profile,
        )


def test_plan_resolves_duration_and_downgrades_single_radio_sync_honestly() -> None:
    revision = compile_profile_mapping(_profile_document())
    single = compile_capture_plan(revision, ["pluto-a"], source_type=SourceType.TEST)
    paired = compile_capture_plan(revision, ["pluto-a", "pluto-b"])

    assert single.resolved_sample_count == 150_000_000
    assert single.requested_synchronization_mode is SynchronizationMode.BEST_EFFORT
    assert single.effective_synchronization_mode is SynchronizationMode.NONE
    assert single.source_type is SourceType.TEST
    assert paired.effective_synchronization_mode is SynchronizationMode.BEST_EFFORT
    assert single.plan_digest != paired.plan_digest


def test_profile_contract_rejects_ambiguous_or_noncanonical_fields() -> None:
    document = _profile_document()
    document["sample_count"] = 12
    with pytest.raises(ValidationError, match="exactly one"):
        compile_profile_mapping(document)

    document = _profile_document()
    document["receivers"] = [1, 0]
    with pytest.raises(ValidationError, match="unique and sorted"):
        compile_profile_mapping(document)

    document = _profile_document()
    document["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs"):
        compile_profile_mapping(document)


def test_yaml_loader_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        "schema_version: 1\nname: one\nname: two\n",
        encoding="utf-8",
    )
    with pytest.raises(ProfileDocumentError, match="duplicate key"):
        load_profile_revision(path)


def test_repository_profile_compiles() -> None:
    path = Path(__file__).parents[2] / "profiles" / "starlink-ch4-lower-2p5m-60s.yaml"
    revision = load_profile_revision(path)

    assert revision.profile.sample_rate_hz == 2_500_000
    assert revision.profile.receivers == (0, 1)
