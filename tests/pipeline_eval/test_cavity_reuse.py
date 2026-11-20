import csv
from types import SimpleNamespace

import numpy as np
import pytest

from leo.sky import propagation
from tools.pipeline_eval.qualification import cavity_reuse_results as results
from tools.pipeline_eval.variants.cavity_reuse_columns import (
    Columns,
    prepare_with_checksum_reuse,
    receipt,
)


def test_initial_columns_match_complete_immutable_projection_inputs():
    stencil = object()
    executed = []

    def read(source, columns):
        values = tuple(np.asarray(columns, dtype=float) * k for k in (1, 2, 3))
        source.last = columns.copy(), values
        executed.append(source)
        return values

    def source(*, base=stencil, lat=0.0, **options):
        return SimpleNamespace(
            stencil=base, operation=read, coordinates=(lat, 122.5), options=options, last=None
        )

    cache = Columns(stencil, read)
    columns = np.array([2, 1], dtype=np.intp)
    first = cache.read(source(), columns)
    assert cache.read(source(), columns) is first
    assert cache.stats["hits"] == 1
    assert all(not value.flags.writeable for value in first)
    assert np.array_equal(first[2], np.array([6.0, 3.0]))
    for altered in (source(lat=-0.0), source(altitude_m=1), source(rf_hz=2), source(base=object())):
        assert cache.read(altered, columns) is not first
    assert cache.read(source(), columns[::-1]) is not first
    assert cache.read(source(), columns.astype(np.int16)) is not first
    assert len(executed) == 7
    bounded = Columns(stencil, read, budget=1)
    bounded.read(source(), columns)
    bounded.read(source(), columns)
    assert bounded.stats["hits"] == bounded.stats["stored"] == 0
    assert bounded.stats["bypasses"] == 2


def test_checksum_cache_preserves_element_line_validation_and_restores_on_error(monkeypatch):
    original = propagation.element_line_checksum
    computed = []

    def count(line):
        computed.append(line)
        return original(line)

    monkeypatch.setattr(propagation, "element_line_checksum", count)
    first = "1 25544U 98067A   23073.02771182  .00017654  00000-0  32060-3 0  999"
    second = first[:22] + "1" + first[23:]
    assert len(first) == 68

    def prepare():
        for prefix in (first, first, second):
            for last in ("0", "9"):
                line = prefix + last
                assert propagation.element_line_checksum(line) == original(line)
        raise RuntimeError("incomplete scientific source")

    with pytest.raises(RuntimeError, match="incomplete scientific source"):
        prepare_with_checksum_reuse(prepare, limit=2)
    assert propagation.element_line_checksum is count
    assert computed == [first, second]
    assert receipt() == dict(hits=4, misses=2, entries=2, max_entries=2)


def test_parity_counts_an_error_in_native_calls_or_frequency_independently():
    import copy

    stock = {
        "wall_s": 10.0,
        "measurements": {"finish": {"cgroup_cpu_s": 7.0, "cgroup_peak": 10, "peak_rss_kib": 8}},
        "result": {
            "status": "ok",
            "arms": {"c0": {"latlon": [1, 2], "rf_rms_hz": 42.0}},
            "metrics": {
                "initial_branches": 3,
                "compact_projections": 8,
                "stage_s": {"native_preparation": 2, "initial": 4},
            },
        },
    }
    candidate = copy.deepcopy(stock)
    candidate["mode"] = "columns"
    candidate["result"]["metrics"].update(compact_projections=5, reuse_trace={"hits": 3})
    assert results.parity(stock, candidate)["exact"]
    candidate["result"]["metrics"]["reuse_trace"]["hits"] = 2
    assert results.parity(stock, candidate)["science_equal"]
    assert not results.parity(stock, candidate)["exact"]
    candidate["result"]["arms"]["c0"]["rf_rms_hz"] = 42.01
    assert not results.parity(stock, candidate)["science_equal"]


@pytest.mark.parametrize(
    ("cohort", "expected", "nrows"),
    (
        (".", {"DS26-0036", "DS29-0082"}, 12),
        ("holdout", {"DS26-0112", "DS29-0127"}, 8),
    ),
)
def test_published_reuse_trial_rescores_without_runtime_inputs(tmp_path, cohort, expected, nrows):
    source = results.REPORT / cohort
    comparison = results.score(source, tmp_path)
    assert set(comparison) == expected
    assert all(value["exact"] for methods in comparison.values() for value in methods.values())
    for filename in ("scores.csv", "resources.csv", "comparison.json"):
        assert (tmp_path / filename).read_bytes() == (source / filename).read_bytes()
    rows = list(csv.DictReader((tmp_path / "scores.csv").read_text().splitlines()))
    assert len(rows) == nrows
    assert {row["arm"] for row in rows} == {"c0", "fitted_c"}
    assert all(float(row["shift_from_stock_m"]) == 0.0 for row in rows)
