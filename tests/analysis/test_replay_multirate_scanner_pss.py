import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from tools.replay_multirate_scanner_pss import (
    VISIT_POLICY,
    aggregate,
    cache_matches,
    retained_indexes_by_target,
    select,
    timing_metrics,
)


def test_legacy_or_foreign_manifest_cache_is_not_reused(tmp_path):
    path = tmp_path / "session-example.json"
    job = dict(session_id="example", manifest_sha256="sha256:" + "a" * 64)
    path.write_text(json.dumps(dict(session_id="example", rows=[], tracking=[])))
    assert not cache_matches(path, job)
    with pytest.raises(ValueError, match="legacy PSS"):
        aggregate(tmp_path, 1)
    path.write_text(
        json.dumps(
            dict(
                session_id="example",
                visit_policy=VISIT_POLICY,
                source_manifest_sha256=job["manifest_sha256"],
            )
        )
    )
    assert cache_matches(path, job)
    assert not cache_matches(path, {**job, "manifest_sha256": "sha256:" + "b" * 64})


def test_retained_positions_are_not_sparse_firmware_visit_ids():
    visits = [
        SimpleNamespace(event=SimpleNamespace(visit_index=v, target_index=t))
        for v, t in [(0, 3), (2, 7), (5, 3), (6, 7)]
    ]
    groups = retained_indexes_by_target(visits)
    assert groups == {3: [0, 2], 7: [1, 3]}
    assert [visits[i].event.visit_index for i in groups[3]] == [0, 5]


@dataclass(frozen=True)
class Window:
    frame_index: int
    frame_phase_samples: float


def test_selection_is_order_independent():
    digest = "sha256:" + "a" * 64
    assert select([2, 4, 8, 16], digest) == select([16, 8, 4, 2], digest)


def test_alternating_timing_metric_recovers_linear_phase():
    rate = 10_000_000
    windows = [Window(i, (100e-9 + i * 2e-9) * rate) for i in range(12)]
    result = timing_metrics(windows, rate)
    assert result["timing_windows"] == 12
    assert result["linear_fit_rms_ns"] < 1e-9
    assert result["alternating_validation_rms_ns"] < 1e-9


def test_timing_metric_refuses_short_mode():
    result = timing_metrics([Window(i, 0) for i in range(7)], 10_000_000)
    assert result["timing_windows"] == 7
    assert result["alternating_validation_rms_ns"] is None
