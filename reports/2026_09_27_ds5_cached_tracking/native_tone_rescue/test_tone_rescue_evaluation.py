from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_tone_rescue_owned_runner", HERE / "run_tone_rescue_evaluation.py"
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def test_fixed_development_membership_methods_and_bounds():
    assert {stage: len(runner.cases_for_stage(stage)) for stage in runner.STAGES} == {
        "controls": 42, "diagnostic": 26, "real": 64,
    }
    assert runner.METHODS == {
        "controls": ("native_tracked", "raw_rescue", "tone_rescue"),
        "diagnostic": ("application", "native_tracked", "tone_rescue"),
        "real": ("application", "native_tracked", "tone_rescue"),
    }
    assert runner.TIMEOUT_SECONDS == {"controls": 120, "diagnostic": 120, "real": 300}
    assert all(case.split == "development" for stage in runner.STAGES
               for case in runner.cases_for_stage(stage))


def test_rotation_includes_every_method_once():
    for stage in runner.STAGES:
        expected = set(runner.METHODS[stage])
        assert all(set(runner.rotated_methods(stage, index)) == expected
                   and len(runner.rotated_methods(stage, index)) == len(expected)
                   for index in range(6))


def _assessment(passed: bool):
    return {"activity_policy_passed": passed}


def _receipt(*, raw_pass=False, tone_pass=True, supplemental=24):
    methods = {
        "native_tracked": [_assessment(True), _assessment(True)],
        "raw_rescue": [_assessment(raw_pass), _assessment(True)],
        "tone_rescue": [_assessment(tone_pass), _assessment(True)],
    }
    return {
        "rows": [{"native_assessments": methods}],
        "supplemental_mirrored_negative_rows": [
            {"native_assessments": methods} for _ in range(supplemental)
        ],
    }


def test_raw_failed_comparator_does_not_gate_but_new_candidate_does():
    assert runner._required_policy_failures(_receipt(raw_pass=False, tone_pass=True)) == 0
    assert runner._required_policy_failures(_receipt(raw_pass=True, tone_pass=False)) == 25


def test_predecessor_requires_all_24_orientation_rows(monkeypatch, tmp_path):
    lock_path = tmp_path / "source_lock.json"
    lock_path.write_text("{}")
    monkeypatch.setattr(runner, "SOURCE_LOCK", lock_path)
    receipt = _receipt(raw_pass=False, tone_pass=True, supplemental=23)
    receipt.update({
        "status": "complete", "complete": True, "source_lock_stable": True,
        "source_lock": {"stages": {"controls": {"case_ids": ["one"]}}},
        "source_lock_sha256": runner.digest(lock_path),
    })
    path = tmp_path / "controls.json"
    path.write_text(json.dumps(receipt))
    monkeypatch.setattr(runner, "result_path", lambda _stage: path)
    with pytest.raises(ValueError, match="does not authorize"):
        runner.predecessor_receipts("diagnostic", receipt["source_lock"])


def test_tone_result_requires_every_engine_call_and_nuisance_receipt():
    primary = SimpleNamespace(active=False)
    result = SimpleNamespace(
        decisions=(primary, primary), primary_decisions=(primary, primary),
        rescue_receiver=0, rescue_acquisition_count=1,
        rescue_candidate_score_count=1, rescue_seed_guided_count=1,
        rescue_confirmation_guided_count=0,
        tone_guided_calls=(SimpleNamespace(
            receiver=0, probe_index=0,
            observation=SimpleNamespace(
                nuisance_enabled=True, nuisance_applied=True,
                nuisance_frequency_hz=1.0, nuisance_spectral_fraction=.2,
                nuisance_fitted_power_fraction=.1, nuisance_cpu_ms=.1,
                pack_cpu_ms=.1, conversion_cpu_ms=.1, glrt_cpu_ms=.2,
                glrt_evaluations=1,
            ),
        ),),
    )
    runner.validate_tone_result(result)
    result.tone_guided_calls = ()
    with pytest.raises(ValueError, match="every guided call"):
        runner.validate_tone_result(result)


def test_tone_result_rejects_dropped_nuisance_fields():
    primary = SimpleNamespace(active=False)
    result = SimpleNamespace(
        decisions=(primary, primary), primary_decisions=(primary, primary),
        rescue_receiver=0, rescue_acquisition_count=1,
        rescue_candidate_score_count=1, rescue_seed_guided_count=1,
        rescue_confirmation_guided_count=0,
        tone_guided_calls=(SimpleNamespace(
            receiver=0, probe_index=0, observation=SimpleNamespace(nuisance_enabled=True)
        ),),
    )
    with pytest.raises(ValueError, match="omitted nuisance_applied"):
        runner.validate_tone_result(result)


def test_primary_parity_is_exact_and_fail_closed():
    baseline = ({"active": False, "route": "blind"},) * 2
    outputs = {
        "native_tracked": baseline,
        "raw_rescue": SimpleNamespace(primary_decisions=baseline),
        "tone_rescue": SimpleNamespace(primary_decisions=baseline),
    }
    assert runner.primary_parity(outputs) == {
        "raw_rescue": True, "tone_rescue": True,
    }
    outputs["tone_rescue"] = SimpleNamespace(primary_decisions=(
        {"active": True, "route": "guided"}, baseline[1],
    ))
    with pytest.raises(ValueError, match="primary detector science/state"):
        runner.primary_parity(outputs)


def test_source_contract_mentions_parent_receipts_and_explicit_cli():
    text = (HERE / "run_tone_rescue_evaluation.py").read_text()
    assert "EXPECTED_RAW_LOCK" in text and "EXPECTED_RAW_CONTROLS" in text
    assert 'actions.add_argument("--freeze"' in text
    assert 'actions.add_argument("--stage", choices=STAGES)' in text
    assert '"holdout_opened": False' in text
    assert '"validation_opened": False' in text
