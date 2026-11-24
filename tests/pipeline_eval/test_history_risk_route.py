from hashlib import sha256
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from history_risk_route import checked_census, choose_once, select


def test_dispatch_uses_same_prepared_object_and_keeps_choice_across_attempts():
    calls = []
    prepared, retry = object(), object()

    def check(value):
        calls.append(("check", value))
        return {"prior": {"previous": {"unusable": {}}, "genuine_previous": {"unusable": {"173": {}}}}}

    def named(value):
        calls.append(("named", value))
        return value

    run = choose_once(named, lambda value: pytest.fail("Paid lean inference"), check, {})
    assert run(prepared) is prepared and run(retry) is retry
    assert calls == [("check", prepared), ("named", prepared), ("named", retry)]


def test_missing_invalid_and_clear_censuses():
    assert select(lambda _: {"prior": {}}, None)["reason"] == "probe_unavailable"
    assert select(lambda _: {"prior": {"previous": {}}}, None)["route"] == "named"
    clean = {"prior": {"previous": {"unusable": {}}, "genuine_previous": {"unusable": {}}}}
    assert select(lambda _: clean, None)["route"] == "lean"


def test_checks_all_released_samples_for_errors_and_nonfinite_states():
    text = "authenticated text"
    receipt = dict(catalogue_sha256=sha256(text.encode()).hexdigest(), sources={
        str(x): {"epoch_utc_ns": 23, "collected_utc_ns": 35} for x in (1, 2, 3)})
    sky = dict(metadata={"origin_utc_ns": 42, "cutoff_utc_ns": 41}, bank={"norad": [1, 2, 3]},
               nominal_elements={"1": {}, "2": {}, "3": {}})
    for prior in ("previous", "genuine_previous"):
        sky[prior+"_receipt"] = receipt
        sky[prior+"_tle"] = text

    def ecef(cat, origin, times):
        assert cat.satellite_numbers == [1, 2, 3] and origin == 42
        assert times.tolist() == [0., 150., 300.]
        p, v = np.zeros((3, 3, 3)), np.zeros((3, 3, 3))
        p[1, 2, 2] = np.inf
        return p, v, np.asarray([False, True, True])

    modes = SimpleNamespace(parse_element_sets=lambda observed: SimpleNamespace(satellite_numbers=[1, 2, 3]),
                            ecef_states=ecef)
    result = checked_census({"status": "inputs_prepared", "sky": sky}, modes, 41)
    assert all(set(row["unusable"]) == {"1", "2"} for row in result["prior"].values())
