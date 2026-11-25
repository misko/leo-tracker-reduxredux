from copy import deepcopy
from hashlib import sha256
from importlib import import_module
import json
from math import sqrt
from pathlib import Path

import pytest


@pytest.fixture
def score(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("masked_cfo_0218_fixed_residuals")


def row(oid, measured, residual, *, norad=121, role="conditional"):
    return dict(observation_id=oid, norad=norad, role=role, measured_cfo_hz=measured,
                residual_hz=residual, prediction_hz=measured-residual)


def cell(score, *rows, withheld=False):
    if withheld:
        return dict(export=dict(decision="withheld", rows={}), witness=dict(owner_rows={}, detail=dict(arms=None)))
    identities = [[r["observation_id"], r["norad"], r["role"]] for r in rows]
    summary = dict(associated_points=len(rows), owner_sha256=score.digest({k:n for k,n,_ in identities}),
                   residual_rms_hz=sqrt(sum(r["residual_hz"]**2 for r in rows)/len(rows)))
    return dict(export=dict(decision="complete", rows={arm: list(rows) for arm in score.ARMS}),
                witness=dict(owner_rows={arm: identities for arm in score.ARMS},
                             detail=dict(arms={arm: summary for arm in score.ARMS})))


def edit(old, updated):
    return dict(original_hz=old, updated_hz=updated, forecast_hz=old+2*(updated-old))


def basic(score):
    period = score.PERIOD
    a, b = 10., -240_000.
    original = [dict(observation_id=oid, measured_cfo_hz=cfo) for oid,cfo in
                (("reowned", a), ("dropped", b), ("null", 50.), ("control", -20.), ("added", 40.))]
    # The signed residuals here use oppositely signed ordinary integer lifts.
    before = cell(score, row("reowned", a, a+period-(period+13.)),
                  row("dropped", b, b-period-(b-period-5.), role="predictive"),
                  row("null", 50., 7.), row("control", -20., -4.))
    after = cell(score, row("reowned", 12., 21., norad=880, role="predictive"),
                 row("null", 50., 8.), row("control", -20., 2.), row("added", 40., -15.))
    return before, after, original, dict(edits={"reowned": edit(a, 12.), "dropped": edit(b, b-2),
                                               "null": edit(50., 50.)})


def test_fixed_ordinary_set_preserves_lift_and_real_null_edit(score):
    before, after, original, edits = basic(score)
    result = score.compare(before, after, original, edits)
    assert result["c0"] == result["fitted_c"]
    fixed = result["c0"]["fixed_state"]
    assert fixed["all"]["ordinary"]["n"] == fixed["all"]["fixed"]["n"] == 4
    assert fixed["all"]["delta_sse_hz2"] == pytest.approx(-24.)
    assert fixed["by_original_role"]["conditional"]["delta_sse_hz2"] == pytest.approx(-8.)
    assert fixed["by_original_role"]["predictive"]["delta_sse_hz2"] == pytest.approx(-16.)
    assert fixed["changed"]["ordinary"]["n"] == 2
    assert fixed["null_edit"]["eligible"] == 1 and fixed["null_edit"]["changed"] == 0
    assert fixed["null_edit"]["delta_sse_hz2"] == fixed["unedited"]["delta_sse_hz2"] == 0.
    assert fixed["unedited"]["ordinary"] == fixed["unedited"]["fixed"]


def test_rebuilt_scope_records_satellite_role_and_support_changes(score):
    before, after, original, edits = basic(score)
    rebuilt = score.compare(before, after, original, edits)["c0"]["actual_rebuilt"]
    assert rebuilt["common"]["ordinary"]["n"] == 3
    assert rebuilt["common_changed_role"]["ordinary"]["n"] == 1
    assert rebuilt["common_changed_norad"]["ordinary"]["n"] == 1
    assert rebuilt["role_transitions"] == {"conditional->predictive": 1, "conditional->conditional": 2}
    assert rebuilt["ordinary_only"]["changed_edits"] == 1
    assert rebuilt["corrected_only"]["n"] == 1


def test_rejects_missing_ordinary_owner_and_changed_representation(score):
    before, after, original, edits = basic(score)
    missing = deepcopy(before)
    missing["export"]["rows"]["fitted_c"].pop()
    with pytest.raises(ValueError, match="missing"):
        score.compare(missing, after, original, edits)
    false = deepcopy(after)
    altered = false["export"]["rows"]["c0"][0]
    altered["measured_cfo_hz"] += score.PERIOD
    altered["prediction_hz"] = altered["measured_cfo_hz"]-altered["residual_hz"]
    with pytest.raises(ValueError, match="signed CFO"):
        score.compare(before, false, original, edits)
    with pytest.raises(ValueError, match="half-blend"):
        score.edited_winners(original, {"reowned": edit(10., 10.+score.PERIOD)})


def test_withholding_distinguishes_no_overlay_from_editor_withholding_after_graph(score):
    before, after, original, edits = basic(score)
    withheld = cell(score, withheld=True)
    applied = score.compare(before, withheld, original, edits)["fitted_c"]
    assert applied["fixed_state"]["all"]["ordinary"]["n"] == 4
    assert applied["corrected_selected"] is None and applied["actual_rebuilt"] is None
    skipped = score.compare(before, withheld, original, None)["fitted_c"]
    assert skipped["fixed_state"] is None
    assert skipped["fixed_unavailable"] == "no_observed_corrected_overlay"
    no_original = score.compare(withheld, after, original, edits)["fitted_c"]
    assert no_original["fixed_unavailable"] == "ordinary_withheld"
    assert no_original["fixed_state"] is None and no_original["actual_rebuilt"] is None


def test_native_id_and_winner_match_signed_receiver_order(score):
    def candidate(rank, cfo, margin):
        return dict(candidate_rank=rank, fractional_margin=margin, fractional_tracking_cfo_hz=cfo,
                    passed_fractional_margin_gate=True)

    packet = dict(clock_anchor=dict(sample_counter=20), source=dict(session_id="session", sample_rate_hz=score.ADC,
        probe_ms=20, probes=[dict(receiver_id=1, valid_start_counter=30, channel=4, actual_rf_hz=11.5e9,
                                 candidates=[candidate(1, 42., .2), candidate(0, -310_000., .2)])]))
    (winner,) = score.original_winners(packet)
    assert winner["observation_id"] == "sha256:"+sha256(b"session:1:30").hexdigest()
    assert winner["measured_cfo_hz"] == -310_000.
    assert winner["time_s"] == pytest.approx(.010001)


def test_closed_cell_checks_export_hash_and_terminal_state(score, tmp_path):
    def seal(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        path.write_bytes(body)
        return sha256(body).hexdigest()

    root = tmp_path / "ordinary"
    pub = root / "substituted"
    native = dict(provenance=dict(detector_sha256="frozen-detector"))
    native_pin = "sha256:" + seal(root / "derived-native.json", native)
    seal(pub / "fast-scan-automatic-work/native/detections.json", native)
    terminal = dict(native_sha256=native_pin, region={"width_km": 25}, decision="ok")
    terminal_pin = "sha256:" + seal(pub / "fast-scan-automatic-work/run/terminal.json", terminal)
    witness = dict(evidence=dict(detail=dict(input_sha256=native_pin, terminal_sha256=terminal_pin,
                                             region=terminal["region"], state="complete")))
    witness_pin = seal(pub / "exact-named-raw-witness.json", witness)
    plan = dict(case=score.CASE, enabled=False, probe=False, original_native_sha256=native_pin,
                sources={"held_cfo_features.py": score.FEATURE, "masked_cfo_saved.py": score.OVERLAY},
                change=dict(edits=[], derived_native_sha256=native_pin, recipe_sha256="frozen-detector",
                            recipe=dict(sparse_native_sha256=native_pin, edit_sha256=score.digest([]))))
    pins = dict(plan=seal(root / "plan.json", plan), clock=seal(root / "clock.json", {"exit_code": 0}))
    pins["isolation"] = seal(root / "worker-isolation.json", dict(inherited_descriptor=True,
                             socket_denied=True, readonly_operands=True))
    scope = dict(stage_plan_sha256=pins["plan"], enabled=False, decision="complete", native_sha256=native_pin,
                 original_native_sha256=native_pin, waveform_reads=0, forecast_cache_reads=0,
                 feature_source_sha256=score.FEATURE, approved_track_config_sha256=score.CONFIG)
    pins["observation"] = seal(root / "masked-cfo-observation-witness.json", scope)
    run = dict(case=score.CASE, graph_replayed=True, plan_sha256=pins["plan"], input=native_pin, handoffs=1,
               waveform_reads=0, receiver_rerun=False, selector_rerun=False, witness=witness_pin,
               receipt=dict(decision="complete", terminal_sha256=terminal_pin, run_id="run", region=terminal["region"]))
    pins["receipt"] = seal(root / "receipt.json", run)
    export = dict(schema="leo.research.selected-owner-residuals.v1", role="ordinary", decision="complete",
                  plan_sha256=pins["plan"], native_sha256=native_pin, terminal_sha256=terminal_pin,
                  ordinary_receipt_sha256=pins["receipt"], observation_witness_sha256=pins["observation"],
                  publication_witness_sha256=witness_pin, presentation_source_sha256=score.PRESENTATION,
                  observer_source_sha256=score.OBSERVER)
    path = root / "owner-residuals.json"
    pins["residuals"] = seal(path, export)
    clock = dict(residuals_sha256=pins["residuals"])
    pins["export_clock"] = seal(root / "owner-residual-export-clock.json", clock)
    assert score.read_cell(root, "ordinary", pins)["terminal"] == terminal

    seal(path, dict(export, native_sha256="wrong"))
    with pytest.raises(ValueError, match="Unverified saved input"):
        score.read_cell(root, "ordinary", pins)
