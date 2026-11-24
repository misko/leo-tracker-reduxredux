from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import ds30_0163_combined as driver
from reports.ALGO08.v3 import ds30_0173_combined as held


def test_rank_five_keeps_its_frozen_pair_and_order():
    result = held.assigned()
    assert (result["case"], result["rank"], result["roster_size"]) == ("DS30-0173", 5, 87)
    assert result["archived_pair_sha256"] == held.PAIR_PIN
    assert result["order"] == ["routed", "installed"]
    assert 0 < result["estimated_worker_ceiling_s"] < 120


@pytest.mark.parametrize("failure", (None, "routed", "installed"))
def test_two_isolated_entry_probes_gate_the_pair(monkeypatch, failure):
    probes = {"routed": ["candidate-import"], "installed": ["stock-import"]}
    stdout = {
        "routed": '{"early_leo_import": false, "worker_available": true, "guarded_worker_available": true}',
        "installed": "usage: program {installed,routed} job job_sha256 output",
    }
    commands = []

    def launch(argv, **kwargs):
        commands.append(argv)
        mode = next(mode for mode, command in probes.items() if command == argv)
        return SimpleNamespace(returncode=int(mode == failure), stdout=stdout[mode], stderr="")

    monkeypatch.setattr(driver.subprocess, "run", launch)
    checks, passed = driver.check_entries(probes, {})
    assert commands == list(probes.values())
    assert passed == (failure is None)
    assert {mode: row["exit_code"] for mode, row in checks.items()} == {
        mode: int(mode == failure) for mode in probes}


def test_combined_pool_counts_withhold_time_and_preserves_unpaired_geography():
    def row(case, installed, routed, charge, order, decision):
        clocks = dict(installed=installed, routed=routed)
        setup = dict(combined_setup=charge, failed_start=0.)
        return dict(case=case,
                    admission=dict(sources={"science": "same"}, actual_worker_order=order),
                    time={name: clocks for name in ("elapsed_s", "cpu_s")},
                    paid_setup_and_time={name: setup for name in ("elapsed_s", "cpu_s")},
                    jobs=dict(installed={"decision": decision}, routed={"decision": "complete"}),
                    candidate_minus_installed_horizontal_m={
                        "c0": -7 if decision == "complete" else None,
                        "fitted_c": -4 if decision == "complete" else None,
                    })

    a = row("DS30-0163", 20., 10., 2., ["installed", "routed"], "complete")
    b = row("DS30-0173", 5., 10., 1., ["routed", "installed"], "withheld")
    pool = held.independent_pool(a, b)
    assert pool["fixes"] == {"installed": 1, "routed": 2}
    assert pool["withholds"] == {"installed": 1, "routed": 0}
    assert pool["clock_pairs"] == 2 and pool["comparable_position_pairs"] == {"c0": 1, "fitted_c": 1}
    assert pool["measured_worker_order"][a["case"]] == ["installed", "routed"]
    timing = pool["timing"]["elapsed_s"]
    assert timing["worker"]["summed_speedup"] == pytest.approx(25 / 20)
    assert timing["worker"]["reciprocal_median_ratio"] == pytest.approx(1 / ((.5 + 2.) / 2))
    assert timing["admission_charged"]["summed_speedup"] == pytest.approx(28 / 23)
    b["admission"]["sources"] = {"science": "different"}
    with pytest.raises(ValueError, match="source"):
        held.independent_pool(a, b)
