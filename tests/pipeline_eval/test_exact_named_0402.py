from copy import deepcopy

import pytest

from reports.ALGO08.v3.exact_named_0402 import extend_panel, request_view


def test_archive_alias_does_not_replace_signed_offer_cutoff_or_authority():
    old = dict(local_archive=dict(root="/dev/shm/tle", snapshots_sha256="digest", bytes=100),
               original_archive=dict(root="/signed/original", snapshots_sha256="digest"),
               causal_cutoff_utc_ns=12345, offer_sha256="offer")
    unmodified = deepcopy(old)
    view = request_view(old)
    assert old == unmodified
    assert view["local_archive"] == old["local_archive"] | {"snapshots": 48}
    assert all(view[name] == old[name] for name in ("original_archive", "causal_cutoff_utc_ns", "offer_sha256"))
    old["local_archive"]["snapshots_sha256"] = "different"
    with pytest.raises(ValueError, match="original signed causal inventory"):
        request_view(old)


def measured(stock, candidate):
    return dict(clocks=dict(named=dict(elapsed_s=stock, cpu_s=stock), candidate=dict(elapsed_s=candidate, cpu_s=candidate)),
                speedup=dict(elapsed_s=stock/candidate, cpu_s=stock/candidate),
                geography={}, parity=dict(complete=True, owners=True, c0=True, fitted_c=True))


def test_panel_accepts_exact_fourth_case_and_keeps_paid_gate_separate():
    previous = dict(target=1.6, per_case={"DS30-0160": measured(8, 5), "DS30-0316": measured(6, 5),
                                         "DS30-0374": measured(6, 5)})
    new = measured(20, 10) | dict(case="DS30-0402", exact=True, ports={"gates": {"constrained_calls": 1}})
    panel = extend_panel(previous, new, "current")
    assert len(previous["per_case"]) == 3 and panel["recordings"] == panel["exact_cases"] == 4
    wall = panel["saved"]["elapsed_s"]
    assert wall["total_ratio"] == pytest.approx(40/25) and wall["median_ratio"] == pytest.approx(1.4)
    assert wall["total_target_met"] and not wall["median_target_met"]
    assert panel["new_gate_work"] == {"constrained_calls": 1}
    new["parity"]["fitted_c"] = False
    with pytest.raises(ValueError, match="exact parity"):
        extend_panel(previous, new, "current")
