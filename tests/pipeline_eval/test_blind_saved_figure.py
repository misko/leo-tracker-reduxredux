import pytest

from reports.ALGO08.v3.blind_saved_figure import combined_blind, combined_development, observations, read_receipt


def test_three_pairs_preserve_enrollment_and_keep_withheld_position_missing():
    dev, first, second = observations()
    assert [r["cohort"] for r in (dev, first, second)] == ["development", "blind", "blind"]
    assert [r["case"] for r in (dev, first, second)] == ["DS30-0255", "DS30-0419", "DS30-0289"]
    assert dev["c0"][0] == dev["c0"][1]
    assert first["fitted_c"][1] < first["fitted_c"][0]
    assert all(second[arm][0] is None and second[arm][1] > 0 for arm in ("c0", "fitted_c"))
    assert second["elapsed_s"][0] < second["elapsed_s"][1]


def test_revised_solver_keeps_development_separate_and_admission_outside_worker_clocks():
    dev = combined_development()
    assert dev["case"] == "DS30-0289" and dev["c0"][0] is None
    assert dev["fitted_c"][1] == pytest.approx(1.291987, abs=1e-6)
    trial = read_receipt("ds30-0163-combined.json.gz",
                         "9c28657f1dd8a8f31b2f564522d47b42e9b83347f9f816e75c435022f6398801")
    blind = combined_blind(trial)
    assert blind["case"] == "DS30-0163" and blind["cohort"] == "blind"
    assert blind["elapsed_s"] == pytest.approx([20.766805, 11.865799], abs=1e-6)
    assert blind["c0"][1] < blind["c0"][0]
