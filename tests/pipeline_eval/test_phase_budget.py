import fcntl
import gzip
import sys
from collections import Counter
from types import ModuleType, SimpleNamespace

import pytest

from tools.pipeline_eval.__main__ import encoded, save_json
from tools.pipeline_eval.qualification import phase_budget as trial
from tools.pipeline_eval.qualification import phase_history_audit as history
from tools.pipeline_eval.variants import v5_two_refresh as variant


def test_duplicate_lane_cannot_start_a_second_timed_worker(tmp_path, monkeypatch):
    monkeypatch.setattr(trial.os, "sched_getaffinity", lambda _: {22, 23})
    calls = []
    monkeypatch.setattr(trial, "measure_lane", lambda _, lane, cpu: calls.append((lane, cpu)))
    with (tmp_path / "lane-0.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        with pytest.raises(BlockingIOError):
            trial.replay(tmp_path, 0, 22)
        trial.replay(tmp_path, 1, 23)
    trial.replay(tmp_path, 0, 22)
    assert calls == [(1, 23), (0, 22)]


def test_caps_only_outer_rounds_and_tracks_successful_calls():
    observed = []
    counts = Counter()

    def fit(arm, *, rounds, iterations):
        observed.append((arm, rounds, iterations))
        return arm

    limited = variant.limit_rounds(fit, "initial", counts)
    assert limited("c0", iterations=48) == "c0"
    assert limited("fitted_c", rounds=1, iterations=17) == "fitted_c"
    for invalid in (False, 0, -1, 2.5):
        with pytest.raises(ValueError):
            limited("c0", rounds=invalid, iterations=48)
    assert observed == [("c0", 2, 48), ("fitted_c", 1, 17)]
    assert counts == {"initial_calls": 2, "initial_rounds": 3}


def test_policy_restores_every_original_function_after_worker_failure(monkeypatch):
    def fit(*, rounds=5):
        return rounds

    fake = ModuleType("leo.analysis.localization_v3")
    specs = {
        "position": ["refreshed"],
        "conservative_recovery": ["fit_position", "repaired_fit"],
        "history_policy": ["refit", "linear_refit"],
    }
    targets = []
    for name, functions in specs.items():
        module = SimpleNamespace(**dict.fromkeys(functions, fit))
        setattr(fake, name, module)
        targets.extend((module, name) for name in functions)
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    with pytest.raises(RuntimeError, match="downstream"), variant.early_phase_policy() as counts:
        assert all(getattr(m, k)() == 2 for m, k in targets)
        assert all(
            counts[k + "_calls"] == 1
            for k in ("initial", "conservative", "salvage", "curved_family", "linear_family")
        )
        raise RuntimeError("downstream")
    assert all(getattr(m, k) is fit for m, k in targets)


def sealed_fixture(path, mismatched=False):
    files = {}
    for m, method in enumerate(trial.METHODS):
        records = []
        for i, ident in enumerate(trial.TIMING_IDS):
            records.append(
                dict(
                    id=ident,
                    method=method,
                    cpu=i,
                    order=(i + m) % 2,
                    source_sha256={},
                    input_sha256=ident,
                    native_sha256=ident,
                    catalog_sha256=ident,
                    worker_wall_s=2 + m,
                    worker_cpu_s=1 + m,
                    result=dict(status="withheld", boundary="test", metrics={}, reason="weak"),
                )
            )
        if mismatched and m == 1:
            records[0]["catalog_sha256"] = "other-snapshot"
        file = path / (method + ".jsonl.gz")
        file.write_bytes(gzip.compress(b"".join(encoded(r) + b"\n" for r in records)))
        files[file.name] = trial.digest(file)
    save_json(path / "receipt.json", dict(files=files, cases=trial.TIMING_IDS, source={}))


@pytest.mark.parametrize("corruption", ["bytes", "catalog"])
def test_checks_pairs_and_bytes_before_opening_truth(tmp_path, monkeypatch, corruption):
    sealed_fixture(tmp_path, mismatched=corruption == "catalog")
    if corruption == "bytes":
        (tmp_path / (trial.METHODS[0] + ".jsonl.gz")).write_bytes(b"bad predictions")
    monkeypatch.setattr(trial, "references", lambda *_: pytest.fail("opened truth before seal"))
    with pytest.raises(ValueError, match="sealed roster|same input"):
        trial.score(tmp_path)


def test_withheld_or_failed_cases_cannot_pass_distribution_gate():
    rows = [
        dict(
            dataset="DS26",
            arm="c0",
            method=trial.METHODS[0],
            position_error_km=error,
            v5_error_km=old,
            conditional_rms_hz=rms,
        )
        for error, old, rms in [(0.5, 1.0, 0.0), (None, 10.0, None)]
    ]
    source = {
        "a": dict(result=dict(status="ok"), worker_wall_s=2, worker_cpu_s=1.5),
        "b": dict(result=dict(status="failed"), worker_wall_s=10, worker_cpu_s=8),
    }
    summary = trial.summarize(rows, dict.fromkeys(trial.METHODS, source))
    group = summary["groups"][0]
    assert group["scheduled"] == 2 and group["error_km"]["n"] == 1
    assert group["paired_v5"]["at_most_10pct_worse"] == 1
    assert not group["meets_10pct_distribution_gate"]
    assert group["conditional_rms_hz"]["p50"] == 0
    assert summary["scheduled_pairs"] == 2
    assert summary["paired_timing"]["worker_wall_s"]["stock_over_candidate"]["n"] == 1


def test_phase_history_reselects_both_arms_from_only_zero_calibration():
    def branch(base, scores):
        return {
            arm: [
                dict(score=score if arm == "c0" else -score, xy=(base + i, 1), rms=1, change=0.2)
                for i, score in enumerate(scores)
            ]
            for arm in trial.ARMS
        }

    histories = [branch(10, [3, 1, 4, 5, 7]), branch(50, [9, 5, 1, 0, 0])]
    for row in history.compare(histories, 1):
        assert (row["two_winner"], row["five_winner"]) == (0, 1)
        assert row["shift_on_two_winner_km"] == 3
        assert row["selected_initial_shift_km"] == 43
    with pytest.raises(ValueError, match="five-fit branch"):
        history.compare(histories, 0)
    histories[1]["fitted_c"].pop()
    with pytest.raises(ValueError, match="five original"):
        history.compare(histories, 1)
