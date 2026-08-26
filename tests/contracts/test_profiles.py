from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from leo.contracts.profile import (
    CapturePlanV2,
    CaptureProfileRevisionV1,
    CaptureProfileRevisionV2,
    CaptureProfileV1,
)
from leo.contracts.recording import DEVICE_AXIS_STORAGE_POLICY_V1
from leo.contracts.states import (
    ContinuityPolicy,
    PeerFailurePolicy,
    SourceType,
    SynchronizationMode,
)
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


def test_v2_profile_persists_verified_buffer_and_queue_policy() -> None:
    path = Path(__file__).parents[2] / "profiles" / "hardware-canary-2p5m-1s-continuity-v2.yaml"
    revision = load_profile_revision(path)
    assert isinstance(revision, CaptureProfileRevisionV2)

    plan = compile_capture_plan(revision, ["pluto-a"], source_type=SourceType.LIVE)

    assert isinstance(plan, CapturePlanV2)
    assert plan.profile_revision.profile.kernel_buffers == 8
    assert plan.profile_revision.profile.refill_queue_capacity == 32
    assert plan.profile_revision.profile.require_device_metadata is True
    assert plan.resolved_sample_count == 2_500_000


@pytest.mark.parametrize(
    ("filename", "sample_rate_hz", "resolved_sample_count", "continuity_policy", "tags"),
    (
        (
            "hardware-canary-3m-60s-contiguous-v2.yaml",
            3_000_000,
            180_000_000,
            ContinuityPolicy.REQUIRE_CONTIGUOUS,
            ("CANARY", "LIVE", "QUALIFICATION"),
        ),
        (
            "starlink-ch4-lower-3m-60s-capture-v2.yaml",
            3_000_000,
            180_000_000,
            ContinuityPolicy.ALLOW_SEGMENTS,
            ("CAPTURE_ONLY", "LIVE", "RANDOM_TUNING"),
        ),
        (
            "starlink-ch4-lower-5m-60s-segmented-v2.yaml",
            5_000_000,
            300_000_000,
            ContinuityPolicy.ALLOW_SEGMENTS,
            ("CAPTURE_ONLY", "EXPERIMENTAL", "LIVE", "RANDOM_TUNING"),
        ),
    ),
)
def test_sample_rate_mode_profile_has_explicit_capture_geometry(
    filename: str,
    sample_rate_hz: int,
    resolved_sample_count: int,
    continuity_policy: ContinuityPolicy,
    tags: tuple[str, ...],
) -> None:
    path = Path(__file__).parents[2] / "profiles" / filename
    revision = load_profile_revision(path)
    assert isinstance(revision, CaptureProfileRevisionV2)

    profile = revision.profile
    plan = compile_capture_plan(revision, ["pluto-a", "pluto-b"])

    assert isinstance(plan, CapturePlanV2)
    assert profile.name == path.stem
    assert profile.sample_rate_hz == sample_rate_hz
    assert profile.bandwidth_hz == 2_500_000
    assert profile.receivers == (0, 1)
    assert profile.refill_samples == 262_144
    assert profile.kernel_buffers == 8
    assert profile.refill_queue_capacity == 32
    assert profile.require_device_metadata is True
    assert profile.continuity_policy is continuity_policy
    assert profile.tags == tags
    assert plan.resolved_sample_count == resolved_sample_count


def test_sample_rate_mode_profiles_have_unique_immutable_revisions() -> None:
    root = Path(__file__).parents[2] / "profiles"
    paths = (
        root / "hardware-canary-3m-60s-contiguous-v2.yaml",
        root / "starlink-ch4-lower-3m-60s-capture-v2.yaml",
        root / "starlink-ch4-lower-5m-60s-segmented-v2.yaml",
    )

    revisions = tuple(load_profile_revision(path) for path in paths)

    assert all(isinstance(revision, CaptureProfileRevisionV2) for revision in revisions)
    assert len({revision.revision_digest for revision in revisions}) == len(paths)


@pytest.mark.parametrize(
    ("rate_name", "sample_rate_hz", "resolved_sample_count", "experimental"),
    (
        ("2p5m", 2_500_000, 150_000_000, False),
        ("3m", 3_000_000, 180_000_000, False),
        ("5m", 5_000_000, 300_000_000, True),
    ),
)
def test_device_axis_profiles_are_fail_closed_native_rate_candidates(
    rate_name: str,
    sample_rate_hz: int,
    resolved_sample_count: int,
    experimental: bool,
) -> None:
    path = (
        Path(__file__).parents[2]
        / "profiles"
        / f"starlink-ch4-lower-{rate_name}-60s-device-axis-v3.yaml"
    )
    revision = load_profile_revision(path)
    assert isinstance(revision, CaptureProfileRevisionV2)

    profile = revision.profile
    plan = compile_capture_plan(revision, ["pluto-a", "pluto-b"])

    assert isinstance(plan, CapturePlanV2)
    assert profile.name == path.stem
    assert profile.sample_rate_hz == sample_rate_hz
    assert profile.bandwidth_hz == 2_500_000
    assert profile.continuity_policy is ContinuityPolicy.ALLOW_SEGMENTS
    assert profile.peer_failure_policy is PeerFailurePolicy.FAIL_SESSION
    assert profile.storage_policy == DEVICE_AXIS_STORAGE_POLICY_V1
    assert profile.require_device_metadata is True
    assert {"CAPTURE_ONLY", "DEVICE_AXIS_ZERO_FILL", "STANDARD_NATIVE"}.issubset(profile.tags)
    assert ("EXPERIMENTAL" in profile.tags) is experimental
    assert plan.resolved_sample_count == resolved_sample_count


@pytest.mark.parametrize(
    "name",
    (
        "starlink-ch4-lower-2p5m-60s-continuity-v2.yaml",
        "starlink-ch4-lower-2p5m-60s-rx1-continuity-v2.yaml",
        "starlink-ch4-lower-2p5m-60s-rx1-centered-continuity-v2.yaml",
    ),
)
def test_live_continuity_profiles_use_dual_rx_metadata_geometry(name: str) -> None:
    revision = load_profile_revision(Path(__file__).parents[2] / "profiles" / name)
    assert isinstance(revision, CaptureProfileRevisionV2)
    profile = revision.profile
    assert profile.receivers == (0, 1)
    assert profile.kernel_buffers == 8
    assert profile.refill_queue_capacity == 32
    assert profile.require_device_metadata is True


def test_repository_ch4_lower_single_rx1_profile_compiles_for_independent_and_pair() -> None:
    path = Path(__file__).parents[2] / "profiles" / "starlink-ch4-lower-2p5m-60s-rx1.yaml"
    revision = load_profile_revision(path)
    profile = revision.profile

    assert profile.center_frequency_hz == 1_709_687_500
    assert profile.rf_center_frequency_hz == 11_459_687_500
    assert profile.lnb_lo_hz == 9_750_000_000
    assert profile.starlink_channel == "ch4"
    assert profile.starlink_edge is not None
    assert profile.starlink_edge.value == "lower"
    assert profile.sample_rate_hz == 2_500_000
    assert profile.bandwidth_hz == 2_500_000
    assert profile.receivers == (1,)
    assert tuple(item.receiver_id for item in profile.gains) == (1,)
    assert tuple(item.gain_db for item in profile.gains) == (40.0,)

    independent = compile_capture_plan(revision, ["radio-a"], source_type=SourceType.LIVE)
    synchronized = compile_capture_plan(
        revision,
        ["radio-a", "radio-b"],
        source_type=SourceType.LIVE,
    )

    assert independent.resolved_sample_count == 150_000_000
    assert independent.requested_synchronization_mode is SynchronizationMode.BEST_EFFORT
    assert independent.effective_synchronization_mode is SynchronizationMode.NONE
    assert synchronized.resolved_sample_count == 150_000_000
    assert synchronized.requested_synchronization_mode is SynchronizationMode.BEST_EFFORT
    assert synchronized.effective_synchronization_mode is SynchronizationMode.BEST_EFFORT
    assert independent.profile_revision == synchronized.profile_revision == revision


def test_repository_centered_rx1_profile_preserves_nominal_revision_and_coverage() -> None:
    root = Path(__file__).parents[2] / "profiles"
    nominal = load_profile_revision(root / "starlink-ch4-lower-2p5m-60s-rx1.yaml")
    centered = load_profile_revision(root / "starlink-ch4-lower-2p5m-60s-rx1-centered-v1.yaml")

    assert nominal.revision_digest == (
        "sha256:7dfcdb9a83794f0a24486558a3f1d3b4bbff1b1ea4c97a94d0828a4490086af0"
    )
    assert centered.profile.name == "starlink-ch4-lower-2p5m-60s-rx1-centered-v1"
    assert centered.revision_digest == (
        "sha256:0f6aa753e16feaba1f76df21f0b620f32ab0b72456cb6034f2b1ea6a60c11e1a"
    )
    assert centered.profile.center_frequency_hz == 1_709_521_250
    assert centered.profile.rf_center_frequency_hz == 11_459_521_250
    assert centered.profile.rf_center_frequency_hz == (
        centered.profile.center_frequency_hz + 9_750_000_000
    )
    assert centered.profile.starlink_channel == "ch4"
    assert centered.profile.starlink_edge is not None
    assert centered.profile.starlink_edge.value == "lower"

    historical_offsets_hz = (-170_442.5, -162_048.5)
    tune_delta_hz = centered.profile.center_frequency_hz - nominal.profile.center_frequency_hz
    residual_centers_hz = tuple(offset - tune_delta_hz for offset in historical_offsets_hz)
    assert residual_centers_hz == (-4_192.5, 4_201.5)
    allowable_uncertainty_hz = tuple(
        centered.profile.sample_rate_hz / 2 - 937_500.0 - 300_000.0 - abs(center)
        for center in residual_centers_hz
    )
    assert allowable_uncertainty_hz == (8_307.5, 8_298.5)
    assert min(allowable_uncertainty_hz) > 500.0
