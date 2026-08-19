from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from leo.pipeline import compile_scope_inventory, compile_standard_run_plan

DIGEST = "sha256:" + "a" * 64
RELEASE = "1" * 40


@dataclass(frozen=True)
class _Value:
    value: str


@dataclass(frozen=True)
class _Settings:
    receiver_ids: tuple[int, ...]
    sample_rate_hz: int = 2_500_000


def _stream(stream_id: str, radio_id: str, receivers: tuple[int, ...]) -> object:
    return SimpleNamespace(
        stream_id=stream_id,
        radio=SimpleNamespace(
            radio_id=radio_id,
            serial=f"serial-{radio_id}",
            uri=f"ip:{radio_id}",
            transport=_Value("ethernet"),
        ),
        applied_settings=_Settings(receivers),
        requested_settings=_Settings(receivers),
        captured_sample_count=100,
        timing=None,
        state=_Value("complete"),
    )


def _manifest(*streams: object) -> object:
    return SimpleNamespace(session_id="T1", streams=streams)


@pytest.mark.parametrize(
    ("radio_count", "receiver_count", "expected_jobs", "expected_edges"),
    ((1, 1, 11, 13), (1, 2, 21, 26), (2, 1, 23, 28), (2, 2, 43, 54)),
)
def test_standard_topology_expands_exact_path_radio_pair_graph(
    radio_count: int,
    receiver_count: int,
    expected_jobs: int,
    expected_edges: int,
) -> None:
    receivers = tuple(range(receiver_count))
    manifest = _manifest(
        *(_stream(f"stream-{index}", f"radio-{index}", receivers) for index in range(radio_count))
    )

    plan = compile_standard_run_plan(
        manifest,  # type: ignore[arg-type]
        manifest_digest=DIGEST,
        pipeline_release_id=RELEASE,
    )

    assert len(plan.jobs) == expected_jobs
    assert len(plan.edges) == expected_edges
    reducers = tuple(job for job in plan.jobs if "scientific-report" in job.stage_key)
    assert all(job.iq_access.value == "none" for job in reducers)
    assert sum(job.stage_key == "path-scientific-report" for job in plan.jobs) == (
        radio_count * receiver_count
    )
    assert sum(job.stage_key == "path-trajectory-feedback" for job in plan.jobs) == (
        radio_count * receiver_count
    )


def test_topology_and_pair_digest_are_invariant_to_manifest_stream_permutation() -> None:
    left = _stream("stream-b", "radio-b", (0, 1))
    right = _stream("stream-a", "radio-a", (0, 1))

    first = compile_scope_inventory(_manifest(left, right))  # type: ignore[arg-type]
    second = compile_scope_inventory(_manifest(right, left))  # type: ignore[arg-type]

    assert first == second
    assert first.paired is not None
    assert tuple(scope.stream_id for scope in first.radios) == ("stream-a", "stream-b")


def test_standard_path_graph_has_exact_frozen_stages_and_report_fan_in() -> None:
    plan = compile_standard_run_plan(
        _manifest(_stream("stream-a", "radio-a", (0,))),  # type: ignore[arg-type]
        manifest_digest=DIGEST,
        pipeline_release_id=RELEASE,
    )
    path_jobs = tuple(job for job in plan.jobs if job.node_id.startswith("path-"))

    assert tuple(job.stage_key for job in path_jobs) == (
        "path-input-bind",
        "path-quality",
        "path-power",
        "path-waterfall",
        "path-probe-schedule",
        "path-pilot-scan",
        "path-trajectory-bank",
        "path-trajectory-feedback",
        "path-scientific-report",
        "path-presentation",
    )
    dependencies = {
        edge.depends_on_job_node_id
        for edge in plan.edges
        if edge.job_node_id == "path-00-stage-08"
    }
    assert dependencies == {
        "path-00-stage-01",
        "path-00-stage-02",
        "path-00-stage-03",
        "path-00-stage-07",
    }


def test_mixed_two_plus_one_topology_has_exact_radio_fan_in() -> None:
    plan = compile_standard_run_plan(
        _manifest(
            _stream("stream-a", "radio-a", (0, 1)),
            _stream("stream-b", "radio-b", (0,)),
        ),  # type: ignore[arg-type]
        manifest_digest=DIGEST,
        pipeline_release_id=RELEASE,
    )
    edges_by_consumer: dict[str, set[str]] = {}
    for edge in plan.edges:
        edges_by_consumer.setdefault(edge.job_node_id, set()).add(
            edge.depends_on_job_node_id
        )

    assert edges_by_consumer["radio-00-reduce"] == {
        "path-00-stage-08",
        "path-01-stage-08",
    }
    assert edges_by_consumer["radio-01-reduce"] == {"path-02-stage-08"}
    assert edges_by_consumer["paired-00-reduce"] == {
        "radio-00-reduce",
        "radio-01-reduce",
    }


def test_topology_rejects_duplicate_radio_identity() -> None:
    manifest = _manifest(
        _stream("stream-a", "radio-a", (0,)),
        _stream("stream-b", "radio-a", (1,)),
    )
    with pytest.raises(ValueError, match="radio identity"):
        compile_scope_inventory(manifest)  # type: ignore[arg-type]
