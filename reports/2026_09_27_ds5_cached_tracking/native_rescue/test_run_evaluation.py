from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_rescue_owned_evaluation", HERE / "run_evaluation.py"
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def test_fixed_stage_memberships_and_methods_do_not_open_reserved_iq():
    assert {stage: len(runner.cases_for_stage(stage)) for stage in runner.STAGES} == {
        "controls": 42, "diagnostic": 26, "real": 64,
    }
    assert runner.METHODS["controls"] == ("native_tracked", "native_rescue")
    assert runner.METHODS["diagnostic"][0] == "application"
    assert runner.TIMEOUT_SECONDS == {"controls": 120, "diagnostic": 120, "real": 300}
    assert all(case.split == "development" for stage in runner.STAGES
               for case in runner.cases_for_stage(stage))


def test_mirrored_negative_membership_is_exact_and_balanced():
    parents = runner.supplemental_negative_parents()
    assert len(parents) == 12
    assert {rate: sum(case.rate == rate for case in parents)
            for rate in (2_500_000, 5_000_000)} == {2_500_000: 6, 5_000_000: 6}
    assert sum("noise" in case.id for case in parents) == 6
    assert sum("tone" in case.id for case in parents) == 6
    assert all(case.activity_policy == "required_inactive" for case in parents)
    assert all(all(rx.constructed_negative and not rx.pilots for rx in case.receivers)
               for case in parents)


def test_swap_descriptor_and_case_permute_truth_and_never_reuse_parent_hash():
    parent = runner.supplemental_negative_parents()[0]
    descriptor = runner.supplemental_descriptor(parent)
    assert descriptor["receiver_permutation"] == [1, 0]
    assert descriptor["parent_raw_npy_sha256"] == parent.raw_sha256
    derived = runner.swapped_case(parent, "a" * 64)
    assert derived.id.endswith("::rxswap-v1")
    assert derived.raw_sha256 == "sha256:" + "a" * 64
    assert derived.raw_sha256 != parent.raw_sha256
    assert derived.receivers[0].receiver == 0 and derived.receivers[1].receiver == 1
    assert derived.receivers[0].components == parent.receivers[1].components
    assert derived.receivers[1].components == parent.receivers[0].components


def test_rx_swap_payload_hash_changes_with_asymmetric_channels_and_is_read_only():
    raw = np.zeros((4, 2, 2), dtype="<i2")
    raw[:, 0, 0] = 1
    raw[:, 1, 0] = 2
    original = runner.hashlib.sha256(raw).hexdigest()
    swapped = np.ascontiguousarray(raw[:, (1, 0), :])
    swapped.setflags(write=False)
    assert runner.hashlib.sha256(swapped).hexdigest() != original
    assert not swapped.flags.writeable
    assert np.array_equal(swapped[:, 0], raw[:, 1])


def test_method_rotation_is_deterministic():
    assert runner.rotated_methods("controls", 0) == ("native_tracked", "native_rescue")
    assert runner.rotated_methods("controls", 1) == ("native_rescue", "native_tracked")
    assert runner.rotated_methods("real", 1) == (
        "native_tracked", "native_rescue", "application"
    )


def test_distribution_uses_nearest_rank_quantiles():
    result = runner.distribution([4.0, 1.0, 3.0, 2.0, 100.0])
    assert result["p50_ms"] == 3.0
    assert result["p95_ms"] == 100.0
    assert result["p99_ms"] == 100.0
    assert result["sum_ms"] == 110.0


def test_rescue_decisions_requires_exactly_two_receivers():
    @dataclass
    class Result:
        decisions: tuple

    assert runner.rescue_decisions(Result(("rx0", "rx1"))) == ("rx0", "rx1")
    with pytest.raises(ValueError, match="exactly two"):
        runner.rescue_decisions(Result(("rx0",)))


def test_result_validator_enforces_first_inactive_and_work_budget():
    inactive = SimpleNamespace(active=False)
    active = SimpleNamespace(active=True)
    result = SimpleNamespace(
        decisions=(inactive, active), primary_decisions=(inactive, active),
        rescue_receiver=0, rescue_acquisition_count=1,
        rescue_candidate_score_count=10, rescue_seed_guided_count=3,
        rescue_confirmation_guided_count=2,
    )
    runner.validate_rescue_result(result)
    result.rescue_receiver = 1
    with pytest.raises(ValueError, match="first-inactive"):
        runner.validate_rescue_result(result)
    result.rescue_receiver = 0
    result.rescue_seed_guided_count = 11
    with pytest.raises(ValueError, match="work budget"):
        runner.validate_rescue_result(result)


def test_only_fixed_probe_pair_route_counts_as_accepted_rescue():
    assert runner.is_rescue_route("rescue_probe0_probe2")
    assert not runner.is_rescue_route("rescue")
    assert not runner.is_rescue_route("guided")


def _receipt(*, supplemental_count=24, supplemental_failure=False):
    assessment = {"activity_policy_passed": True}
    supplemental = [{
        "native_assessments": {
            "native_tracked": [assessment, assessment],
            "native_rescue": [assessment, assessment],
        }
    } for _ in range(supplemental_count)]
    if supplemental_failure and supplemental:
        supplemental[0]["native_assessments"]["native_rescue"][0] = {
            "activity_policy_passed": False
        }
    return {
        "rows": [{
            "native_assessments": {
                "native_tracked": [assessment, assessment],
                "native_rescue": [assessment, assessment],
            }
        }],
        "supplemental_mirrored_negative_rows": supplemental,
    }


def test_supplemental_failure_is_a_predecessor_policy_failure():
    assert runner._policy_failures(_receipt()) == 0
    assert runner._policy_failures(_receipt(supplemental_failure=True)) == 1


def test_predecessor_rejects_missing_supplemental_rows_even_with_original_pass(monkeypatch, tmp_path):
    source_lock = tmp_path / "source_lock.json"
    source_lock.write_text("{}")
    monkeypatch.setattr(runner, "SOURCE_LOCK", source_lock)
    result = _receipt(supplemental_count=23)
    result.update({
        "status": "complete", "complete": True, "source_lock_stable": True,
        "source_lock": {"stages": {"controls": {"case_ids": ["only"]}}},
        "source_lock_sha256": runner.digest(source_lock),
    })
    result_path = tmp_path / "controls.json"
    result_path.write_text(json.dumps(result))
    monkeypatch.setattr(runner, "result_path", lambda _stage: result_path)
    lock = result["source_lock"]
    with pytest.raises(ValueError, match="does not authorize"):
        runner.predecessor_receipts("diagnostic", lock)


def test_runner_records_supplemental_rows_separately_and_requires_explicit_action():
    text = (HERE / "run_evaluation.py").read_text()
    assert '"supplemental_mirrored_negative_rows": supplemental_rows' in text
    assert 'actions.add_argument("--freeze"' in text
    assert 'actions.add_argument("--stage", choices=STAGES)' in text
    assert '"holdout_opened": False' in text
    assert '"validation_opened": False' in text
