import json
from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import full_iq_four as study


def test_join_requires_identical_recording_input_region_catalogue_and_reports_radio_separately():
    stock = dict(
        id="A",
        mode="matched-tile",
        tile={"center": [5, 1]},
        catalog_sha256="catalog",
        native_sha256="ordinary",
        method="whole_cavity",
        result=dict(
            status="ok",
            arms={arm: dict(latlon=[5, 1], rf_rms_hz=32.25) for arm in ("c0", "fitted_c")},
        ),
    )
    candidate = dict(deepcopy(stock), method="whole_fractional", origin_native_sha256="ordinary")
    assert study.matched(candidate, stock, "whole_cavity")
    for changed in (
        dict(origin_native_sha256="other"),
        dict(tile={}),
        dict(catalog_sha256="other"),
    ):
        with pytest.raises(ValueError):
            study.matched(dict(candidate, **changed), stock, "whole_cavity")
    candidate["result"]["arms"]["fitted_c"]["rf_rms_hz"] += 1
    assert not study.matched(candidate, stock, "whole_cavity")


def test_pooled_rows_reproduce_all_four_archived_pairs(tmp_path):
    study.publish(tmp_path)
    evidence = json.loads((tmp_path / "comparison.json").read_bytes())
    assert set(evidence) == {"DS26-0036", "DS26-0237", "DS29-0082", "DS29-0174"}
    assert all(r["exact_arms"] for r in evidence.values())
    assert set(r["control_boundary"] for r in evidence.values()) == {
        "whole_cavity",
        "held_stock_factor_cavity",
    }
