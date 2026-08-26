from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from leo.contracts.digests import canonical_digest
from leo.contracts.recording import RecordingManifestV3
from leo.domain.profiles import load_profile_revision
from leo.pipeline.standard_native import (
    STANDARD_NATIVE_PROFILE_REVISION_DIGESTS,
    STANDARD_NATIVE_STAGE_KEYS,
    compile_standard_native_run_plan,
)

_ROOT = Path(__file__).parents[2]
_RELEASE = "1" * 40


@dataclass(frozen=True)
class _Value:
    value: str


@dataclass(frozen=True)
class _Settings:
    receiver_ids: tuple[int, ...]
    sample_rate_hz: int
    bandwidth_hz: int
    center_frequency_hz: int


class _Timing:
    def model_dump(self, *, mode: str) -> dict[str, object]:
        assert mode == "json"
        return {"schema_version": 1, "first": 1, "last": 2}


def _manifest(
    profile_name: str,
    *,
    radio_count: int = 2,
    requested_centers_hz: tuple[int, ...] | None = None,
) -> RecordingManifestV3:
    revision = load_profile_revision(_ROOT / "profiles" / f"{profile_name}.yaml")
    rate = revision.profile.sample_rate_hz
    logical_count = rate * 60
    centers = requested_centers_hz or (revision.profile.center_frequency_hz,) * radio_count
    assert len(centers) == radio_count
    streams = tuple(
        SimpleNamespace(
            stream_id=f"stream-{index}",
            radio=SimpleNamespace(
                radio_id=f"radio-{index}",
                serial=f"serial-{index}",
                uri=f"ip:radio-{index}",
                transport=_Value("ethernet"),
            ),
            applied_settings=_Settings(
                (0, 1),
                rate,
                revision.profile.bandwidth_hz,
                centers[index],
            ),
            requested_settings=_Settings(
                (0, 1),
                rate,
                revision.profile.bandwidth_hz,
                centers[index],
            ),
            requested_sample_count=logical_count,
            logical_sample_count=logical_count,
            observed_sample_count=logical_count,
            timing=_Timing(),
            state=_Value("complete"),
        )
        for index in range(radio_count)
    )
    return RecordingManifestV3.model_construct(
        session_id="native-session",
        streams=streams,
        tags=revision.profile.tags,
        capture_plan=SimpleNamespace(
            profile_revision=revision,
            resolved_sample_count=logical_count,
        ),
    )


@pytest.mark.parametrize(
    "profile_name",
    tuple(STANDARD_NATIVE_PROFILE_REVISION_DIGESTS),
)
def test_native_topology_accepts_only_reviewed_profile_capabilities(profile_name: str) -> None:
    manifest = _manifest(profile_name)
    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=canonical_digest({"manifest": profile_name}),
        pipeline_release_id=_RELEASE,
    )

    assert len(plan.jobs) == 12
    assert len(plan.edges) == 14
    assert {job.stage_key for job in plan.jobs} == set(STANDARD_NATIVE_STAGE_KEYS)
    assert sum(job.stage_key == "path-standard-native" for job in plan.jobs) == 4
    assert all(
        job.iq_access.value == "none"
        for job in plan.jobs
        if job.stage_key != "path-standard-native"
    )


def test_native_topology_is_disjoint_from_frozen_standard_stage_ids() -> None:
    plan = compile_standard_native_run_plan(
        _manifest("starlink-ch4-lower-3m-60s-device-axis-v3"),
        manifest_digest=canonical_digest({"manifest": "native"}),
        pipeline_release_id=_RELEASE,
    )

    assert not {
        "path-standard",
        "path-alternate-tracks",
        "radio-scientific-report",
        "paired-scientific-report",
        "paired-presentation",
    }.intersection(job.stage_key for job in plan.jobs)


def test_native_topology_accepts_two_radio_random_tuning_centers() -> None:
    manifest = _manifest(
        "starlink-ch4-lower-5m-60s-device-axis-v3",
        requested_centers_hz=(10_700_000_000, 11_200_000_000),
    )

    plan = compile_standard_native_run_plan(
        manifest,
        manifest_digest=canonical_digest({"manifest": "random-centers"}),
        pipeline_release_id=_RELEASE,
    )

    assert len(plan.jobs) == 12


def test_native_topology_rejects_applied_center_retarget() -> None:
    manifest = _manifest(
        "starlink-ch4-lower-3m-60s-device-axis-v3",
        requested_centers_hz=(10_700_000_000, 11_200_000_000),
    )
    stream = manifest.streams[1]
    retargeted = SimpleNamespace(
        **{
            **vars(stream),
            "applied_settings": _Settings(
                receiver_ids=(0, 1),
                sample_rate_hz=3_000_000,
                bandwidth_hz=stream.requested_settings.bandwidth_hz,
                center_frequency_hz=stream.requested_settings.center_frequency_hz + 1,
            ),
        }
    )
    foreign = manifest.model_copy(update={"streams": (manifest.streams[0], retargeted)})

    with pytest.raises(ValueError, match="stream geometry"):
        compile_standard_native_run_plan(
            foreign,
            manifest_digest=canonical_digest({"manifest": "retargeted"}),
            pipeline_release_id=_RELEASE,
        )


def test_native_topology_rejects_profile_revision_substitution() -> None:
    manifest = _manifest("starlink-ch4-lower-5m-60s-device-axis-v3")
    revision = manifest.capture_plan.profile_revision.model_copy(
        update={"revision_digest": canonical_digest({"foreign": "profile"})}
    )
    foreign = manifest.model_copy(
        update={"capture_plan": SimpleNamespace(profile_revision=revision)}
    )

    with pytest.raises(ValueError, match="profile identity"):
        compile_standard_native_run_plan(
            foreign,
            manifest_digest=canonical_digest({"manifest": "foreign"}),
            pipeline_release_id=_RELEASE,
        )


def test_native_topology_rejects_non_v3_recording() -> None:
    with pytest.raises(ValueError, match="V3 device-axis"):
        compile_standard_native_run_plan(
            SimpleNamespace(session_id="old", streams=()),  # type: ignore[arg-type]
            manifest_digest=canonical_digest({"manifest": "old"}),
            pipeline_release_id=_RELEASE,
        )
