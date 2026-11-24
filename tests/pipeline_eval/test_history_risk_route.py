from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from history_risk_route import checked_census, choose_once, select
from history_risk_route_panel import aggregate, reduction


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


def test_three_case_reduction_distinguishes_median_and_summed_speedup():
    result = reduction([12, 20, 40], [6, 10, 40])
    assert result["median_paired_ratio"] == 2
    assert result["summed_ratio"] == pytest.approx(72/56)
    with pytest.raises(ValueError):
        reduction([12, 20, 40], [6, 10])


def test_four_case_extension_keeps_the_original_three_and_charges_admission():
    def publication(case):
        return dict(case="DS30-"+case, archive_stock_clock={"elapsed_s": 9, "cpu_s": 8},
                    clock={"elapsed_s": 4, "cpu_s": 3})

    admission = {"preflight": {"elapsed_ns": 2_000_000_000, "cpu_ns": 1_000_000_000}}
    earlier = {"enrolled": {case: dict(result=publication(case), source_stage=admission)
                            for case in ("0160", "0316", "0374")}}
    panel = aggregate(earlier, publication("0402"), admission, "pin", case="0402")
    assert list(panel["enrolled"]) == ["0160", "0316", "0374", "0402"]
    assert panel["totals"]["elapsed_s"]["child"]["summed_ratio"] == 2.25
    assert panel["totals"]["elapsed_s"]["preflight_charged"]["summed_ratio"] == 1.5
    assert panel["totals"]["cpu_s"]["preflight_charged"]["summed_ratio"] == 2
    with pytest.raises(ValueError):
        aggregate(earlier, publication("0374"), admission, "pin", case="0402")


def test_pair_reuses_original_installed_command_and_rejects_a_different_mode(monkeypatch, tmp_path):
    import history_risk_0402_pair as pair

    source = tmp_path/"source"
    root = tmp_path/"request"
    release = tmp_path/"release"
    source.mkdir()
    root.mkdir()
    monkeypatch.setattr(pair, "SOURCE", source)
    monkeypatch.setattr(pair, "SOURCES", {})
    monkeypatch.setattr(pair.route, "pinned", lambda path, _: json.loads(path.read_bytes()))
    (root/"admission.json").write_text('{"source_sha256": {}}')
    cmd = [str(x) for x in (release/"venv/bin/python", "-IB", source/"prospective_0402_solver.py",
                            "worker", root/"request.json", "stock", root/"stock")]
    clock = root/"stock-clock.json"
    clock.write_text(json.dumps(dict(command=cmd, timing={"exit_code": 0})))
    actual, _ = pair.previous_stock_command(root, release)
    assert actual == cmd[:-1]
    cmd[-2] = "cumulative"
    clock.write_text(json.dumps(dict(command=cmd, timing={"exit_code": 0})))
    with pytest.raises(ValueError):
        pair.previous_stock_command(root, release)


def test_held_input_view_rejects_a_changed_cutoff_or_causal_manifest():
    from history_risk_0169_input import ENROLLMENT_SHA256, request_view

    shared = dict(case="DS30-0169", recording="recording", session="session", issued=19, admitted=17)
    archive = {"snapshots_sha256": "signed", "snapshots": 1, "bytes": 3}
    request = shared | dict(enrollment_sha256=ENROLLMENT_SHA256, local_archive=archive,
                            causal_cutoff_utc_ns=30, raw_authority="authority")
    enrollment = shared | dict(cutoff_utc_ns=30, authority="authority", snapshots=1, archive_bytes=3,
                               original_archive={"snapshots_sha256": "signed"})
    assert request_view(request, enrollment)["original_archive"] == {"snapshots_sha256": "signed"}
    with pytest.raises(ValueError):
        request_view(request | {"causal_cutoff_utc_ns": 31}, enrollment)
    with pytest.raises(ValueError):
        request_view(request | {"local_archive": archive | {"snapshots_sha256": "different"}}, enrollment)


def test_five_positive_receipt_keeps_launch_order_and_refuses_a_missing_fix():
    def publication(case):
        clock = {"elapsed_s": 6, "cpu_s": 5}
        return dict(case="DS30-"+case, archive_stock_clock=clock, clock=clock, named_parity={"complete": True})

    admission = {"preflight": {"elapsed_ns": 0, "cpu_ns": 0}}
    order = ("0160", "0316", "0374", "0402")
    earlier = {"enrolled": {case: dict(result=publication(case), source_stage=admission) for case in order}}
    held = publication("0169")
    proof = aggregate(earlier, held, admission, "pin", case="0169")
    assert proof["case_order"] == [*order, "0169"]
    assert len(proof["enrolled"]) == 5
    with pytest.raises(ValueError):
        aggregate(earlier, held | {"named_parity": {"complete": False}}, admission, "pin", case="0169")
