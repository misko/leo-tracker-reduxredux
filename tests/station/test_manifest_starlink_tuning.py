from __future__ import annotations

import pytest

from leo.contracts.profile import CaptureProfileRevisionV1
from leo.contracts.standard_pipeline import resolve_manifest_starlink_tuning
from leo.contracts.states import SourceType, StarlinkEdge
from leo.domain.profiles import compile_capture_plan

from .manifest_examples import manifest_example


def _manifest_with_profile(channel: str | None, edge: StarlinkEdge | None):
    manifest = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    profile = manifest.capture_plan.profile_revision.profile.model_copy(
        update={"starlink_channel": channel, "starlink_edge": edge}
    )
    plan = compile_capture_plan(
        CaptureProfileRevisionV1.from_profile(profile),
        manifest.capture_plan.radio_ids,
        source_type=SourceType.TEST,
    )
    return manifest.model_copy(update={"capture_plan": plan})


def test_per_stream_tags_override_stale_profile_without_frequency_inference() -> None:
    manifest = _manifest_with_profile("ch4", StarlinkEdge.LOWER).model_copy(
        update={
            "tags": (
                "TEST",
                "tuning:stream-0:ch1:upper",
                "tuning:stream-1:ch8:lower",
            )
        }
    )

    resolved = resolve_manifest_starlink_tuning(manifest)

    assert (resolved["stream-0"].channel, resolved["stream-0"].edge) == (
        1,
        StarlinkEdge.UPPER,
    )
    assert (resolved["stream-1"].channel, resolved["stream-1"].edge) == (
        8,
        StarlinkEdge.LOWER,
    )
    assert {item.evidence_source for item in resolved.values()} == {
        "per_stream_manifest_tag"
    }


@pytest.mark.parametrize(
    "tags",
    (
        ("TEST", "tuning:stream-0:ch1:upper"),
        ("TEST", "tuning:stream-0:ch1:upper", "tuning:stream-2:ch2:lower"),
        (
            "TEST",
            "tuning:stream-0:ch1:upper",
            "tuning:stream-0:ch2:lower",
            "tuning:stream-1:ch3:upper",
        ),
        ("TEST", "tuning:stream-0:ch9:upper", "tuning:stream-1:ch2:lower"),
    ),
)
def test_rejects_partial_foreign_duplicate_or_invalid_per_stream_tags(
    tags: tuple[str, ...],
) -> None:
    manifest = _manifest_with_profile("ch4", StarlinkEdge.LOWER).model_copy(
        update={"tags": tuple(sorted(tags))}
    )
    with pytest.raises(ValueError, match="Starlink tuning tag|cover every"):
        resolve_manifest_starlink_tuning(manifest)


def test_explicit_profile_is_fallback_only_when_no_per_stream_tags_exist() -> None:
    manifest = _manifest_with_profile("ch8", StarlinkEdge.UPPER)

    resolved = resolve_manifest_starlink_tuning(manifest)

    assert set(resolved) == {"stream-0", "stream-1"}
    assert {
        (item.channel, item.edge, item.evidence_source) for item in resolved.values()
    } == {(8, StarlinkEdge.UPPER, "capture_profile")}


def test_missing_profile_and_per_stream_tuning_evidence_is_rejected() -> None:
    manifest = manifest_example(radio_count=2, applied_receiver_ids=(0, 1))
    with pytest.raises(ValueError, match="explicit profile"):
        resolve_manifest_starlink_tuning(manifest)


@pytest.mark.parametrize(
    "malformed_tag",
    (
        "tuning",
        "tuning:stream",
        "tuning:stream-0",
        "tuning:stream-0:ch1",
        "tuning:stream-0:ch1:upper:extra",
        "tuning:stream0:ch1:upper",
        "tuning-stream-0-ch1-upper",
        "tuning:unknown:ch1:upper",
    ),
)
def test_tuning_like_malformed_tag_never_silently_falls_back_to_profile(
    malformed_tag: str,
) -> None:
    manifest = _manifest_with_profile("ch4", StarlinkEdge.LOWER).model_copy(
        update={"tags": tuple(sorted(("TEST", malformed_tag)))}
    )

    with pytest.raises(ValueError, match="Starlink tuning tag"):
        resolve_manifest_starlink_tuning(manifest)
