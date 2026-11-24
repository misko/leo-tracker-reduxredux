from reports.ALGO08.v3.blind_saved_figure import observations


def test_three_pairs_preserve_enrollment_and_keep_withheld_position_missing():
    dev, first, second = observations()
    assert [r["cohort"] for r in (dev, first, second)] == ["development", "blind", "blind"]
    assert [r["case"] for r in (dev, first, second)] == ["DS30-0255", "DS30-0419", "DS30-0289"]
    assert dev["c0"][0] == dev["c0"][1]
    assert first["fitted_c"][1] < first["fitted_c"][0]
    assert all(second[arm][0] is None and second[arm][1] > 0 for arm in ("c0", "fitted_c"))
    assert second["elapsed_s"][0] < second["elapsed_s"][1]
