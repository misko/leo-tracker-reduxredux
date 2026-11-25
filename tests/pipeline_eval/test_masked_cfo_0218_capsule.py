from pathlib import Path

import masked_cfo_0218_capsule as capsule
import pytest


def _cell(root, mode, *, exit_code=0, bad_residual_pin=False):
    cell = root/mode
    cell.mkdir()
    enabled = mode == "corrected"
    write = capsule.saved.write
    plan = write(cell/"plan.json", dict(case=capsule.held.CASE, enabled=enabled, probe=False,
                                       original_native_sha256="signed-native"))
    write(cell/"clock.json", {"exit_code": exit_code})
    obs = write(cell/"masked-cfo-observation-witness.json", dict(stage_plan_sha256=plan, enabled=enabled,
        decision="withheld", waveform_reads=0, forecast_cache_reads=0, native_sha256="signed-native", eligible=0))
    rec = write(cell/"receipt.json", dict(receipt=dict(decision="withheld", terminal_sha256="terminal"),
        handoffs=1, waveform_reads=0, input="signed-native", witness="publication"))
    write(cell/"worker-isolation.json", dict(inherited_descriptor=True, socket_denied=True, readonly_operands=True,
                                              mount_namespace="mock mount", network_namespace="mock network"))
    res = write(cell/"owner-residuals.json", dict(plan_sha256=plan, role=mode, decision="withheld",
        terminal_sha256="terminal", publication_witness_sha256="publication", native_sha256="signed-native",
        ordinary_receipt_sha256=rec, observation_witness_sha256=obs, observer_source_sha256=capsule.saved.identifier(capsule.OBSERVER), rows={}))
    write(cell/"owner-residual-export-clock.json", {"residuals_sha256": "invalid" if bad_residual_pin else res})
    return cell, plan


def test_real_sealer_rejects_failed_exit_and_detached_observer_artifact(tmp_path):
    before, pin = _cell(tmp_path, "ordinary", exit_code=124)
    with pytest.raises(ValueError, match="exited"):
        capsule.sealed_cell(before, "ordinary", pin)
    after, pin = _cell(tmp_path, "corrected", bad_residual_pin=True)
    with pytest.raises(ValueError, match="residual artifact"):
        capsule.sealed_cell(after, "corrected", pin)


def test_ordinary_parity_closes_before_held_scoring_and_accepts_zero_edit_withhold(tmp_path, monkeypatch):
    calls = []

    def verify(root, pins):
        calls.append(tuple(pins))
        if "corrected" not in pins:
            assert not (root/"verification-pins.json").exists()
            capsule.saved.write(root/"ordinary-parity.json", {"exact_ordinary_scientific_parity":True})
        else:
            assert pins == capsule.saved.document(root/"verification-pins.json")
            assert calls[0] == ("ordinary",)
            capsule.saved.write(root/"score.json", {"decision":"withheld"})

    monkeypatch.setattr(capsule.scoring, "verify", verify)
    _, pin = _cell(tmp_path, "ordinary")
    gate_pin = capsule.finish(tmp_path, "ordinary", pin, "official-pair", None)
    gate = capsule.saved.document(tmp_path/"ordinary-gate.json", gate_pin)
    assert gate["field_pair"] == "official-pair"
    assert not (tmp_path/"score.json").exists()
    _, pin = _cell(tmp_path, "corrected")
    result = capsule.finish(tmp_path, "corrected", pin, "official-pair", gate["ordinary"])
    assert capsule.saved.document(tmp_path/"score.json", result) == {"decision":"withheld"}
    assert calls == [("ordinary",), ("ordinary", "corrected")]


def test_corrected_admission_requires_ordinary_gate_before_a_watch(tmp_path, monkeypatch):
    cell = tmp_path/"corrected"
    cell.mkdir()
    write = capsule.saved.write
    ready = write(cell/"capsule-ready.json", dict(plan="stage-plan", cell="corrected", inputs=[],
        launcher=capsule.saved.identifier(capsule.WORKER), observer=capsule.saved.identifier(capsule.OBSERVER)))
    monkeypatch.setattr(capsule, "DRIVER", Path(__file__))
    monkeypatch.setattr(capsule, "DRIVER_PIN", capsule.saved.identifier(capsule.DRIVER))
    monkeypatch.setattr(capsule.held, "status", lambda: dict(verified_pair=True, pair_sha256="sha256:pair"))
    monkeypatch.setattr(capsule, "operands", lambda *args: (dict(original=dict(verified_field_pair_sha256="pair")), [], []))
    with pytest.raises(ValueError, match="ordinary parity gate"):
        capsule.watch(tmp_path, "corrected", 0, ready, None)
