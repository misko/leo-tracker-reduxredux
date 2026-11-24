import json

from reports.ALGO08.v3 import history_risk_0004 as trial


def test_cold_candidate_reuses_the_exact_adapter_without_future_portable_artifact(tmp_path, monkeypatch):
    import exact_named_route

    original = trial.prior.CASE
    monkeypatch.setattr(exact_named_route, "resident_path", lambda path: path)
    monkeypatch.setattr(trial.prior, "source_pins", lambda: {"driver": "test"})
    req = dict(case=trial.CASE, original_pair_sha256=trial.PAIR_PIN, native_sha256=trial.NATIVE_PIN,
               causal_cutoff_utc_ns=trial.CUTOFF, local_archive={"root": str(trial.DONOR)},
               original_archive={"snapshots_sha256": trial.ARCHIVE})
    request = tmp_path/"request.json"
    request.write_text(json.dumps(req))
    proof = dict(case=trial.CASE, request_sha256=trial.prior.digest(request),
                 protocol_sha256=trial.prior.digest(trial.PROTOCOL))
    (tmp_path/"projection.json").write_text(json.dumps(proof))
    import causal_0138
    original_checked = causal_0138.checked
    monkeypatch.setattr(causal_0138, "checked", lambda path, pin: original_checked(path, pin) if path == request else b"")
    with trial.binding(tmp_path):
        bound, actual = trial.prior.bound_request()
        assert actual == req
        assert bound["issued"] == 6772 and bound["admitted"] == 6769 and bound["portable"] is None
        assert trial.prior.CASE == trial.CASE and trial.prior.KEY == "0004"
    assert trial.prior.CASE == original


def test_science_gate_keeps_both_arms_and_reports_real_withhold_or_regression():
    row = dict(coverage={mode: dict(decision="complete", grid_points=179) for mode in ("named", "routed")},
               prior_named_terminal_equal=True,
               scientific=dict(runs={"named": {"horizontal_error_km": {"c0": 1.2, "fitted_c": 1.4}},
                                     "routed": {"horizontal_error_km": {"c0": 1.4, "fitted_c": 1.8}}}))
    gate = trial.measurement_gates(row)
    assert gate["same_standard_decision"] and gate["both_complete_grids"]
    assert not gate["both_position_regressions_within_250m"]
    row["coverage"]["routed"] = dict(decision="withheld", grid_points=None)
    gate = trial.measurement_gates(row)
    assert not gate["same_standard_decision"]
    assert gate["routed_minus_named_error_km"] is None
