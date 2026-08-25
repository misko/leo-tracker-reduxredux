from __future__ import annotations

import pytest

from leo.contracts.states import SourceType
from leo.pipeline import (
    FIVE_M_GAP_AWARE_CAPABILITY_V1,
    THREE_M_LOSSLESS_CAPABILITY_V1,
    compile_rate_baseline_run_plan,
    compile_standard_run_plan,
    rate_analysis_capability,
)
from tests.rate_analysis_examples import mixed_five_m_manifest, rate_manifest
from tests.station.manifest_examples import manifest_example_v2

_MANIFEST_DIGEST = "sha256:" + "b" * 64
_RELEASE = "1" * 40


@pytest.mark.parametrize(
    ("sample_rate_hz", "expected_capability"),
    (
        (3_000_000, THREE_M_LOSSLESS_CAPABILITY_V1),
        (5_000_000, FIVE_M_GAP_AWARE_CAPABILITY_V1),
    ),
)
def test_exact_rate_capability_compiles_only_independent_receiver_path_baselines(
    sample_rate_hz: int,
    expected_capability: object,
) -> None:
    manifest = rate_manifest(sample_rate_hz)

    assert rate_analysis_capability(manifest) == expected_capability
    plan = compile_rate_baseline_run_plan(
        manifest,
        manifest_digest=_MANIFEST_DIGEST,
        pipeline_release_id=_RELEASE,
    )

    assert len(plan.jobs) == 4
    assert {job.stage_key for job in plan.jobs} == {"rate-continuity-baseline"}
    assert {job.iq_access.value for job in plan.jobs} == {"receiver_path"}
    assert plan.edges == ()
    assert "CAPTURE_ONLY" in manifest.tags
    with pytest.raises(ValueError, match="separately versioned scientific pipeline"):
        compile_standard_run_plan(
            manifest,
            manifest_digest=_MANIFEST_DIGEST,
            pipeline_release_id=_RELEASE,
        )


def test_ordinary_2p5m_recording_remains_standard_only() -> None:
    manifest = manifest_example_v2(
        radio_count=2,
        applied_receiver_ids=(0, 1),
        source_type=SourceType.LIVE,
    )

    standard = compile_standard_run_plan(
        manifest,
        manifest_digest=_MANIFEST_DIGEST,
        pipeline_release_id=_RELEASE,
    )

    assert "path-standard" in {job.stage_key for job in standard.jobs}
    with pytest.raises(ValueError, match="reviewed rate-analysis capability"):
        compile_rate_baseline_run_plan(
            manifest,
            manifest_digest=_MANIFEST_DIGEST,
            pipeline_release_id=_RELEASE,
        )


def test_rate_capability_rejects_unreviewed_runtime_tags_and_tuning_mismatch() -> None:
    manifest = rate_manifest(3_000_000)
    extra_tag = manifest.model_copy(update={"tags": (*manifest.tags, "operator-note")})
    with pytest.raises(ValueError, match="runtime tag inventory"):
        rate_analysis_capability(extra_tag)

    first = manifest.streams[0]
    wrong_center = first.requested_settings.model_copy(
        update={"center_frequency_hz": first.requested_settings.center_frequency_hz + 1_000}
    )
    wrong_tuning = manifest.model_copy(
        update={
            "streams": (
                first.model_copy(update={"requested_settings": wrong_center}),
                manifest.streams[1],
            )
        }
    )
    with pytest.raises(ValueError, match="requested center disagrees"):
        rate_analysis_capability(wrong_tuning)


def test_5m_capability_excludes_truncation_and_queue_loss_diagnostics() -> None:
    manifest = rate_manifest(5_000_000)
    first = manifest.streams[0]
    truncated_continuity = first.continuity.model_copy(
        update={"device_span_sample_count": first.continuity.device_span_sample_count - 1}
    )
    truncated = manifest.model_copy(
        update={
            "streams": (
                first.model_copy(update={"continuity": truncated_continuity}),
                manifest.streams[1],
            )
        }
    )
    with pytest.raises(ValueError, match="full-span gap-only continuity evidence"):
        rate_analysis_capability(truncated)

    queue_loss = manifest.model_copy(
        update={
            "streams": (
                first.model_copy(
                    update={
                        "continuity": first.continuity.model_copy(
                            update={"enqueue_failure_count": 1}
                        )
                    }
                ),
                manifest.streams[1],
            )
        }
    )
    with pytest.raises(ValueError, match="full-span gap-only continuity evidence"):
        rate_analysis_capability(queue_loss)


def test_rate_capability_requires_exact_metadata_abi_and_buffer_policy() -> None:
    manifest = rate_manifest(3_000_000)
    first = manifest.streams[0]
    for update in (
        {"metadata_abi_version": 2},
        {"kernel_buffers": 16},
        {"queue_capacity_refills": 64},
    ):
        altered = manifest.model_copy(
            update={
                "streams": (
                    first.model_copy(
                        update={"continuity": first.continuity.model_copy(update=update)}
                    ),
                    manifest.streams[1],
                )
            }
        )
        with pytest.raises(ValueError, match="closed device-counter continuity evidence"):
            rate_analysis_capability(altered)


def test_5m_capability_accepts_one_lossless_complete_and_one_gapped_partial_stream() -> None:
    mixed = mixed_five_m_manifest()

    assert rate_analysis_capability(mixed) == FIVE_M_GAP_AWARE_CAPABILITY_V1
