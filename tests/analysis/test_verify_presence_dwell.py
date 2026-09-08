from copy import deepcopy

import pytest

from tools.verify_presence_dwell import verify


def fixture():
    spec = {"rate_hz": 2500000, "edge": "upper", "counter": str(10**16 + 37)}
    rows = [
        {
            "rate_hz": 2500000,
            "edge": 1,
            "counter": spec["counter"],
            "bins": 2048,
            "mode": mode,
            "iteration": iteration,
            "rank": {
                "order": list(range(6)),
                "scores": [0.1] * 6,
                "projected_epoch_samples": [0] * 6,
                "total_cpu_ms": 1,
                "total_wall_ms": 1,
            },
            "confirmation_count": 6,
            "confirmation_window_mask": 63,
            "confirmations": [
                {"candidate_count": 0, "candidates": [], "total_cpu_ms": 1, "total_wall_ms": 1}
                for _ in range(6)
            ],
            "nuisances": [
                {
                    "enabled": 1,
                    "applied": 0,
                    "frequency_hz": 0,
                    "spectral_fraction": 0,
                    "fitted_power_fraction": 0,
                }
                for _ in range(6)
            ],
            "prefix_cpu_ms": list(range(2, 8)),
            "prefix_wall_ms": list(range(2, 8)),
            "total_cpu_ms": 7,
            "total_wall_ms": 7,
        }
        for mode in ("blind", "seeded")
        for iteration in range(3)
    ]
    return [spec], rows


def test_every_dwell_and_confirmation_is_accounted():
    spec, rows = fixture()
    result = verify(rows, rows[::-1], spec)
    assert result["verified_dwell_executions"] == 6
    assert result["verified_confirmation_windows"] == 36


def multires_fixture():
    spec, rows = fixture()
    for row in rows:
        row["bins"], row["timing_bins"] = 512, 2048
        row["timing_proposals"] = [
            {"epoch": 17, "score": 0.1, "total_cpu_ms": 1, "total_wall_ms": 1} for _ in range(6)
        ]
        for suffix in ("cpu_ms", "wall_ms"):
            row[f"prefix_{suffix}"] = list(range(3, 15, 2))
            row[f"total_{suffix}"] = 13
    return spec, rows


def test_multires_numerical_inventory_and_timings():
    spec, rows = multires_fixture()
    assert verify(rows, rows[::-1], spec, multires=True)["multires"]


@pytest.mark.parametrize(
    "damage", [None, "missing", "negative", "nan", "excess", "string", "boolean"]
)
def test_optional_stage_timings_are_complete_finite_and_accounted(damage):
    spec, rows = fixture()
    arm = deepcopy(rows)
    c = arm[0]["confirmations"][0]
    c.update(conversion_cpu_ms=0.1, coarse_cpu_ms=0.2, fine_cpu_ms=0.3, fractional_cpu_ms=0.4)
    if damage == "missing":
        del c["fine_cpu_ms"]
    elif damage == "negative":
        c["fine_cpu_ms"] = -0.1
    elif damage == "nan":
        c["fine_cpu_ms"] = float("nan")
    elif damage == "excess":
        c["fine_cpu_ms"] = 2
    elif damage == "string":
        c["fine_cpu_ms"] = "0.1"
    elif damage == "boolean":
        c["fine_cpu_ms"] = True
    if damage:
        with pytest.raises(ValueError):
            verify(rows, arm, spec)
    else:
        assert verify(rows, arm, spec)["verified_dwell_executions"] == 6


@pytest.mark.parametrize("damage", ["missing", "epoch", "score", "nan", "prefix", "grid"])
def test_multires_rejects_bad_or_unaccounted_high_resolution_results(damage):
    spec, rows = multires_fixture()
    arm = deepcopy(rows)
    if damage == "missing":
        arm[0]["timing_proposals"].pop()
    elif damage == "epoch":
        arm[0]["timing_proposals"][0]["epoch"] += 1
    elif damage == "score":
        arm[0]["timing_proposals"][0]["score"] += 0.01
    elif damage == "nan":
        arm[0]["timing_proposals"][0]["total_cpu_ms"] = float("nan")
    elif damage == "prefix":
        arm[0]["prefix_cpu_ms"][0] = 2
    else:
        arm[0]["timing_bins"] = 4096
    with pytest.raises(ValueError):
        verify(rows, arm, spec, multires=True)


@pytest.mark.parametrize(
    "damage",
    ["missing", "duplicate", "counter", "order", "count", "mask", "prefix", "nan", "nuisance"],
)
def test_bad_accounting_or_numerical_output_is_rejected(damage):
    spec, rows = fixture()
    arm = deepcopy(rows)
    if damage == "missing":
        arm.pop()
    elif damage == "duplicate":
        arm.append(arm[0])
    elif damage == "counter":
        arm[0]["counter"] = float(arm[0]["counter"])
    elif damage == "order":
        arm[0]["rank"]["order"] = [1, 0, 2, 3, 4, 5]
    elif damage == "count":
        arm[0]["confirmations"][0]["candidate_count"] = 1
    elif damage == "mask":
        arm[0]["confirmation_window_mask"] = 31
    elif damage == "prefix":
        arm[0]["prefix_cpu_ms"][0] = 1
    elif damage == "nan":
        arm[0]["total_cpu_ms"] = float("nan")
    else:
        arm[0]["nuisances"][0]["applied"] = 1
    with pytest.raises(ValueError):
        verify(rows, arm, spec)
