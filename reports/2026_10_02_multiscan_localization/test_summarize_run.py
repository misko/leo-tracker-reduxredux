import json

from summarize_run import summarize


def test_summary_counts_unresolved_failures_and_missing_units(tmp_path):
    units = [{"unit_id": f"unit-{index}", "size": 1} for index in range(5)]
    (tmp_path / "selection.json").write_text(json.dumps({"datasets": {"DS10": {"units": units}}}))
    for index in range(4):
        folder = tmp_path / "runs" / "test" / f"unit-{index}"
        folder.mkdir(parents=True)
        if index < 2:
            (folder / "evaluation.json").write_text(
                json.dumps(
                    {
                        "unit_id": f"unit-{index}",
                        "success": index == 0,
                        "maximum_reference_error_km": 0.8 if index == 0 else 0.1,
                        "elapsed_s": 1,
                    }
                )
            )
        elif index == 2:
            (folder / "failure.json").write_text("{}")
    result = summarize(tmp_path, "test")
    assert len(result["units"]) == 5
    group = result["groups"][0]
    assert set(group["status_counts"].values()) == {1}
    assert group["converged_sub_km"] == 1
    assert group["converged_error_km_quantiles"]["min"] == 0.8
    assert group["provisional_estimate_count"] == 2
    assert group["provisional_error_km_quantiles"]["min"] == 0.1
    assert group["provisional_error_km_quantiles"]["median"] == 0.45
