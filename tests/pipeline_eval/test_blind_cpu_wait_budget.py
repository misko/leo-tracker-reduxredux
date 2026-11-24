import pytest

from reports.ALGO08.v3.blind_cpu_wait_budget import compare, study, wait_limit


def row(cpu, waited=20, minimum_wait=1, elapsed=100):
    return {"modeled_cpu_s": cpu, "stock_wait_s": waited, "saved_wait_s": minimum_wait,
            "stock_elapsed_s": elapsed}


def test_impossible_and_unlimited_wait():
    assert wait_limit([row(50)]) is None
    assert wait_limit([row(29)]) == 1
    assert compare([row(39)], 0)["summed_speedup"] == 2.5


def test_summed_gate_binds_before_median():
    rows = [row(15), row(40), row(80)]
    assert wait_limit(rows) == pytest.approx(0.25)
    assert compare(rows, 0.25)["paired_median_speedup"] > 2


def test_median_gate_can_bind_first():
    rows = [row(1), row(40), row(40)]
    assert wait_limit(rows) == pytest.approx(0.5)
    assert compare(rows, 0.5)["summed_speedup"] > 2


def test_sealed_first_member_prediction_includes_native_and_other_work():
    sample = study()["first_member_model_check"]
    assert sample["native_calls"] == {"full": 16, "short_primary": 94}
    assert sample["measured_acquisition_cpu_s"] == pytest.approx(0.235505, abs=1e-6)
    for row in sample["predictions"].values():
        assert row["total_cpu_s"] == pytest.approx(row["native_cpu_s"] + row["other_acquisition_cpu_s"])
    errors = [row["relative_error"] for row in sample["predictions"].values()]
    assert min(errors) == pytest.approx(-0.0268, abs=0.0001)
    assert max(errors) == pytest.approx(0.1386, abs=0.0001)
