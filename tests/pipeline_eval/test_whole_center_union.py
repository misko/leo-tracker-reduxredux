import pytest

from tools.pipeline_eval.qualification import whole_center_union as trial
from tools.pipeline_eval.qualification import whole_center_union_results as results


def lane(hint_added):
    stock = [120, 1000, 2000, 13_332]
    return dict(
        ordinary=stock,
        selected=stock + ([121] if hint_added else []),
        added_epochs=int(hint_added),
        active_epochs=11 + int(hint_added),
        stock_peak_keys=[[120, 20], [13_331, 0]],
        stock_peaks=2,
        extra_peaks=int(hint_added),
        retained_stock=2,
        retained_extra=int(hint_added),
    )


def test_union_retains_all_four_centers_and_coarse_stock_peak_keys():
    extras = [lane(True), lane(False)]
    result = results.check_union_lanes(extras, [121, 1000])
    assert result["actual_fifth_centers"] == 1
    assert result["stock_centers_retained"] == 8
    assert result["added_epochs"] == 1
    assert result["stock_peaks"] == result["retained_stock"] == 4


def test_union_rejects_overwritten_center_and_bad_coarse_inventory():
    replaced = lane(True)
    replaced["selected"] = [120, 1000, 2000, 121]
    with pytest.raises(ValueError, match="displaced"):
        results.check_union_lanes([replaced, lane(False)], [121, None])
    invalid = lane(True)
    invalid["stock_peak_keys"] = [[123, 20], [13_331, 0]]
    with pytest.raises(ValueError, match="peak inventory"):
        results.check_union_lanes([invalid, lane(False)], [121, None])


def test_unavailable_candidate_has_no_inferred_endpoint():
    stock = dict(
        id="DS29-0316",
        tile={"id": "original"},
        mode="matched-tile",
        catalog_sha256="catalog",
        original_request_sha256="request",
        cohort="held",
        paired_capture_sha256="native",
        result={"arms": {"c0": {"latlon": [0, 1]}, "fitted_c": {"latlon": [1, 0]}}},
    )
    row = results.missing(stock, {"reason": "feature gate unavailable"})
    assert row["method"] == trial.METHOD
    assert row["result"]["status"] == "unavailable"
    assert all(r["latlon"] is None for r in row["result"]["arms"].values())
