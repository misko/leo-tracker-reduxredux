from types import SimpleNamespace

import pytest

from leo.analysis.counter_utc_sensitivity import match_counter_utc_sensitivity, utc_offset_grid
from tests.analysis.test_persistent_hop_tle_match import _snapshot_payload, _zero_response_graph


@pytest.mark.parametrize("bound", [0, 1, 20_000_000, 63_333_333, 100_000_000])
def test_offset_grid_includes_endpoints_zero_and_bounds_spacing(bound):
    grid = utc_offset_grid(bound)
    assert grid[0] == -bound and grid[-1] == bound and 0 in grid
    assert max((b - a for a, b in zip(grid, grid[1:], strict=False)), default=0) <= 25_000_000
    with pytest.raises(ValueError):
        utc_offset_grid(100_000_001)


def test_utc_sensitivity_shifts_all_support_together_and_freezes_training_split():
    graph = _zero_response_graph(_snapshot_payload())
    calls = []

    def matcher(shifted, payload, **kwargs):
        offset = (
            shifted.observations[0].support_center_utc_ns
            - graph.observations[0].support_center_utc_ns
        )
        calls.append((offset, kwargs["partition_seed"]))
        for old, new in zip(graph.observations, shifted.observations, strict=True):
            assert old.observation_id == new.observation_id
            assert old.source_sample_start == new.source_sample_start
            assert old.measured_cfo_hz == new.measured_cfo_hz
            assert new.support_start_utc_ns - old.support_start_utc_ns == offset
            assert new.support_end_utc_ns - old.support_end_utc_ns == offset
        return SimpleNamespace(
            leading_catalog_number=1 if offset <= 0 else 2,
            leading_candidate_persisted_on_heldout=True,
            abstention_recommended=False,
            content_digest=shifted.content_digest,
        )

    result = match_counter_utc_sensitivity(
        graph,
        "fixture",
        maximum_error_ns=100_000_000,
        tle_snapshot=None,
        observer_site=None,
        config=SimpleNamespace(selection_protocol_digest="sha256:" + "a" * 64),
        matcher=matcher,
    )
    assert len(calls) == 9 and len({seed for _, seed in calls}) == 1
    assert result.nominal.leading_catalog_number == 1
    assert result.abstention_reasons == ("utc-offset-grid-leader-instability",)
