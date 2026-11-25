from contextlib import contextmanager
import sys
from types import ModuleType, SimpleNamespace

import masked_cfo_0218_owner_residuals as observer
import pytest


def _packet():
    def point(oid, norad, role, residual):
        return dict(observation_id=oid, norad=norad, role=role, measured_cfo_hz=-100., residual_hz=residual,
                    prediction_hz=-100.-residual, receiver=2)

    return {"rows": {
        "c0": [point("first", 101, "conditional", -13.), point("second", 202, "predictive", 2.)],
        "fitted_c": [point("second", 202, "predictive", 3.), point("first", 101, "conditional", -11.)],
    }}


def _evidence(packet):
    return {"owner_rows": {arm: [[row["observation_id"], row["norad"], row["role"]] for row in rows]
                           for arm, rows in packet["rows"].items()}}


def test_selected_rows_hold_signed_values_roles_and_separate_arm_orders():
    packet = _packet()
    out = observer.selected_rows([packet["rows"]], _evidence(packet), "complete")
    assert [row["observation_id"] for row in out["c0"]] == ["first", "second"]
    assert [row["observation_id"] for row in out["fitted_c"]] == ["second", "first"]
    assert out["c0"][0] == dict(observation_id="first", norad=101, role="conditional", measured_cfo_hz=-100.,
                                prediction_hz=-87., residual_hz=-13.)
    assert out["fitted_c"][0]["role"] == "predictive" and out["fitted_c"][0]["residual_hz"] == 3.


def test_selected_rows_require_verified_owners_sign_and_genuine_withholding():
    packet = _packet()
    evidence = _evidence(packet)
    with pytest.raises(ValueError, match="Expected one"):
        observer.selected_rows([packet["rows"], packet["rows"]], evidence, "complete")
    with pytest.raises(ValueError, match="Expected one"):
        observer.selected_rows([packet["rows"]], {"owner_rows": {}}, "withheld")
    assert observer.selected_rows([], {"owner_rows": {}}, "withheld") == {}
    packet["rows"]["c0"].reverse()
    with pytest.raises(ValueError, match="ordered owners"):
        observer.selected_rows([packet["rows"]], evidence, "complete")
    packet["rows"]["fitted_c"][0]["residual_hz"] *= -1
    with pytest.raises(ValueError, match="signed CFO convention"):
        observer.selected_rows([packet["rows"]], _evidence(packet), "complete")


@pytest.mark.parametrize("mode", ["ordinary", "corrected"])
def test_opt_in_uses_original_worker_and_exports_after_verified_closure(tmp_path, monkeypatch, mode):
    packet, events = _packet(), []
    plan_pin = observer.saved.write(tmp_path/"plan.json", {"case": observer.held.CASE, "probe": False})

    def selected(token):
        assert token == "ordinary-selected-fit"
        events.append("selected")
        return packet

    tools = ModuleType("tools")
    tools.algo08_position = SimpleNamespace(selected_packet=selected)
    monkeypatch.setitem(sys.modules, "tools", tools)

    @contextmanager
    def features(native):
        assert native == "original-signed-handoff"
        events.append("features")
        yield

    def worker(*, observation_scope):
        with observation_scope("original-signed-handoff"):
            assert tools.algo08_position.selected_packet("ordinary-selected-fit") is packet

    def entry(root, pin, make_experiment, *, mode, fd):
        assert (root, pin, fd) == (tmp_path, plan_pin, 7)
        assert make_experiment is observer.held.experiment
        observer.saved.worker(observation_scope=features if mode == "corrected" else None)
        events.append("verified-publication-closed")

    def export(root, pin, which, captured):
        assert (root, pin, which) == (tmp_path, plan_pin, mode)
        assert events[-1] == "verified-publication-closed"
        assert len(captured) == 1 and captured[0] is packet["rows"]
        assert tools.algo08_position.selected_packet is selected and observer.saved.worker is worker
        return "optional-export-pin"

    monkeypatch.setattr(observer.saved, "worker", worker)
    monkeypatch.setattr(observer.held, "entry", entry)
    monkeypatch.setattr(observer, "export", export)
    assert observer.entry(tmp_path, plan_pin, mode, 7) == "optional-export-pin"
    assert events == (["features"] if mode == "corrected" else []) + ["selected", "verified-publication-closed"]


def test_export_binds_optional_artifact_to_verified_input_and_terminal(tmp_path, monkeypatch):
    from leo import presentation
    import named_history_once

    source = ModuleType("leo.presentation.localization_v3")
    source.prepare_packet = object()
    monkeypatch.setattr(presentation, "localization_v3", source, raising=False)
    tools = ModuleType("tools")
    tools.algo08_position = SimpleNamespace(prepare_packet=source.prepare_packet)
    monkeypatch.setitem(sys.modules, "tools", tools)
    monkeypatch.setattr(named_history_once, "checked", lambda module, path, pin: None)

    packet = _packet()
    witness_path = tmp_path / "substituted" / "exact-named-raw-witness.json"
    witness_path.parent.mkdir()
    evidence = dict(_evidence(packet), detail=dict(input_sha256="native", terminal_sha256="terminal"))
    witness_pin = observer.saved.write(witness_path, {"evidence": evidence})
    receipt_pin = observer.saved.write(tmp_path/"receipt.json", dict(plan_sha256="plan", input="native",
        witness=witness_pin, receipt=dict(decision="complete", terminal_sha256="terminal")))
    scope_pin = observer.saved.write(tmp_path/"masked-cfo-observation-witness.json", dict(
        stage_plan_sha256="plan", enabled=True, decision="complete", original_native_sha256="native"))

    with pytest.raises(ValueError, match="closed and verified"):
        observer.export(tmp_path, "wrong-plan", "corrected", [packet["rows"]])
    assert not (tmp_path/"owner-residuals.json").exists()
    timing_pin = observer.export(tmp_path, "plan", "corrected", [packet["rows"]])
    timing = observer.saved.document(tmp_path/"owner-residual-export-clock.json", timing_pin)
    document = observer.saved.document(tmp_path/"owner-residuals.json", timing["residuals_sha256"])
    assert (document["ordinary_receipt_sha256"], document["observation_witness_sha256"],
            document["publication_witness_sha256"]) == (receipt_pin, scope_pin, witness_pin)
    assert (document["role"], document["native_sha256"], document["terminal_sha256"]) == ("corrected", "native", "terminal")
    assert document["rows"] == observer.selected_rows([packet["rows"]], evidence, "complete")
