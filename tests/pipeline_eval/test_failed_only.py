import json

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.qualification import failed_only_benchmark as route


def outcome(status, reason=None, elapsed=1):
    point = [37.86, -122.49] if status == "ok" else None
    return dict(
        status=status,
        reason=reason,
        boundary="fixture",
        metrics={"candidate_s": elapsed},
        arms={arm: dict(latlon=point) for arm in cli.ARMS},
    )


PREVIOUS = (
    "Traceback (most recent call last):\n"
    '  File "/frozen/src/leo/analysis/localization_v3/orbit_modes.py", line 44, in previous_bank\n'
    "    assert good.all()\nAssertionError"
)


@pytest.mark.parametrize(
    "reason,trace,cause",
    [
        (route.GRID, None, "orbit_grid_domain"),
        (route.FAMILY, None, "family_excluded_calibration"),
        ("AssertionError", PREVIOUS, "previous_orbit_assertion"),
        (
            "AssertionError",
            PREVIOUS.replace("\nAssertionError", "\n           ^^^^^^^^^^\nAssertionError"),
            "previous_orbit_assertion",
        ),
        ("AssertionError", PREVIOUS.replace("previous_bank", "another_check"), None),
        ("AssertionError", None, None),
        (route.GRID + " in another operation", None, None),
    ],
)
def test_narrow_legacy_failure_receipt(reason, trace, cause):
    row = dict(result=outcome("unavailable", reason), failure_trace=trace)
    assert route.retry_cause(row, True) == cause
    assert route.retry_cause(row, False) is None
    row["result"]["metrics"]["candidate_s"] = 0
    assert route.retry_cause(row, True) is None


@pytest.mark.parametrize(
    "status,reason",
    [
        ("ok", None),
        ("withheld", "scientific gate"),
        ("timed_out", "worker elapsed"),
        ("unavailable", "missing request"),
        ("failed", "AssertionError"),
    ],
)
def test_terminal_stock_result_is_reused_unchanged(tmp_path, monkeypatch, status, reason):
    stock = outcome(status, reason)
    calls = []

    def run(method, case, base, cap, *_others, supervised):
        assert supervised and cap == 195
        calls.append((method, case))
        return dict(result=stock, worker_wall_s=1.1)

    monkeypatch.setattr(cli, "run_one", run)
    monkeypatch.setattr(cli, "implementation_digest", lambda *a: "sealed")
    case = dict(id="roof", binding={"id": "roof"}, compact={"id": "roof"})
    row = route.run(route.METHOD, case, tmp_path, 360, None)
    assert calls == [(route.PROBE, case["compact"])]
    assert row["result"] is stock and row["routing"]["cause"] is None


def test_both_workers_receive_identical_requests_and_repair_withhold_survives(
    tmp_path, monkeypatch
):
    repairs = outcome("withheld", "repair found insufficient paired support")
    repairs["arms"]["c0"]["forced_latlon"] = [37.84, -122.49]
    original = outcome("unavailable", route.FAMILY)
    packet = {"id": "roof", "native_path": "native", "request_path": "bound"}
    calls = []

    def run(method, case, base, cap, *_others, supervised):
        assert supervised and case is packet and cap == 15
        calls.append(method)
        return dict(result=original if method == route.PROBE else repairs, worker_wall_s=1.1)

    monkeypatch.setattr(cli, "run_one", run)
    monkeypatch.setattr(cli, "implementation_digest", lambda *a: "sealed")
    case = dict(id="roof", binding={"id": "roof"}, compact=packet)
    row = route.run(route.METHOD, case, tmp_path, 15, 2)
    assert calls == [route.PROBE, route.REPAIR]
    assert row["result"] is repairs
    assert row["routing"]["attempts"]["stock"]["result"] == original


def test_standard_missing_native_roster_is_scored_without_launching(tmp_path, monkeypatch):
    def unused(*_a, **_kw):
        pytest.fail("the absent input must not start a worker")

    monkeypatch.setattr(cli, "run_one", unused)
    monkeypatch.setattr(cli, "public_cases", unused)
    assert (
        cli.main(
            [
                "run",
                "--variant",
                route.METHOD,
                "--panel",
                "ds26-all159",
                "--case",
                "DS26-0172",
                "--out",
                str(tmp_path),
                "--timeout",
                "5",
            ]
        )
        == 0
    )
    row = json.loads(next(tmp_path.rglob("predictions.jsonl")).read_bytes())
    assert row["result"]["status"] == "unavailable"
    assert row["result"]["reason"] == "no_native_run"
    assert row["routing"]["attempts"] == {}
