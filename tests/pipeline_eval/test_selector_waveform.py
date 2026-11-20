from pathlib import Path

import pytest

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.qualification import selector_waveform as trial
from tools.pipeline_eval.qualification import selector_waveform_results as results
from tools.pipeline_eval.variants.prepared_hotpath_peaks import retained_peaks


def test_replay_replaces_only_the_bound_installed_selector(monkeypatch, tmp_path):
    source = Path(acquisition.__file__)
    lock = dict(producer=str(source.parents[2]), sources={str(source): "digest"})
    original = acquisition._retain_score_map_peaks
    monkeypatch.setattr(trial.BASE, "configure", lambda work: (lock, {}))

    def checked(work, cpu):
        assert work == tmp_path and cpu == 3
        assert acquisition._retain_score_map_peaks is retained_peaks
        raise RuntimeError("worker interrupted")

    monkeypatch.setattr(trial.prepared, "raw", checked)
    with pytest.raises(RuntimeError, match="worker interrupted"):
        trial.raw(tmp_path, 3)
    assert acquisition._retain_score_map_peaks is original
    with pytest.raises(ValueError, match="installed acquisition producer"):
        trial.selector(dict(lock, producer=str(tmp_path)))


def test_timing_compares_only_authentic_visits_and_counts_the_20_ms_boundary():
    previous = [
        dict(visit="1", status="processed", cpu_ms="30", wall_ms="40", folded_calls="2"),
        dict(visit="2", status="invalid_capture", cpu_ms="1", wall_ms="1", folded_calls="0"),
        dict(visit="3", status="processed", cpu_ms="60", wall_ms="50", folded_calls="2"),
    ]
    cache = [
        dict(visit=r["visit"], status=r["status"], calls=r["folded_calls"], coarse_cpu_ns="0")
        for r in previous
    ]
    cache[0]["coarse_cpu_ns"] = "3000000"
    current = [dict(previous[0], cpu_ms=19, wall_ms=20), previous[1]]
    rows = results.paired_timing(previous, cache, current, cache[:2])
    assert [r["visit"] for r in rows] == [1, 2]
    assert rows[0]["prepared_other_cpu_ms"] == 27
    assert rows[0]["selector_other_cpu_ms"] == 16
    stats = results.timing_stats(rows)
    assert stats["prepared"]["wall_ms"]["within_20"] == 0
    assert stats["selector"]["wall_ms"]["within_20"] == 1
    assert stats["selector"]["wall_ms"]["n"] == 1
    assert stats["prepared_minus_selector_cpu_ms"]["p50"] == 11
    with pytest.raises(ValueError, match="duplicate visit"):
        results.paired_timing(previous, cache, current + current, cache[:2])
    with pytest.raises(ValueError, match="cache support"):
        results.paired_timing(previous, cache, current, cache[:1])
    with pytest.raises(ValueError, match="capture validity"):
        results.paired_timing(
            previous, cache, [dict(current[0], status="invalid_capture"), current[1]], cache[:2]
        )
    with pytest.raises(ValueError, match="complete detector CPU"):
        results.paired_timing(
            previous, cache, current, [dict(cache[0], coarse_cpu_ns="20000000"), cache[1]]
        )


def test_position_comparison_uses_both_estimates_and_scores_with_independent_timing():
    result = dict(
        status="ok",
        arms={
            "c0": {"latlon": [37.8, -122.4], "rf_rms_hz": 80.0},
            "fitted_c": {"latlon": [37.8, -122.401], "rf_rms_hz": 79.9},
        },
        metrics=dict(
            c0_frequency_score=30000,
            fitted_c_frequency_score=29999,
            observations=7,
            tracks=2,
            compact_projections=90,
        ),
    )
    endpoint = results.endpoint(result)
    assert endpoint["c0"]["latlon"] == [37.8, -122.4]
    assert endpoint["fitted_c"]["frequency_score"] == 29999
    assert endpoint == results.endpoint(
        dict(result, metrics=dict(result["metrics"], stage_s={"native_preparation": 9.5}))
    )
    assert results.endpoint(dict(result, status="timed_out")) is None
