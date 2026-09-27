from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "native_reference_points_run_diagnostic", HERE / "run_diagnostic.py"
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def _candidate(rank=0, acquired=100.0, residual=20.0, epoch=7, margin=.2):
    return {
        "candidate_rank": rank, "epoch_sample": epoch,
        "acquired_cfo_hz": acquired, "residual_cfo_hz": residual,
        "tracking_cfo_hz": acquired + residual,
        "exact_score": margin + .1, "control_score": .1,
        "margin": margin, "passed_margin_gate": True,
    }


def _row(candidates=None):
    candidates = candidates or [_candidate()]
    observation = {
        "receiver": 0, "probe_index": 2, "probe_start_sample": 50_000,
        "dwell_epoch_sample": 50_007.0,
        "tracking_cfo_hz": candidates[0]["tracking_cfo_hz"],
        "margin": candidates[0]["margin"],
    }
    return {
        "rate_hz": 2_500_000,
        "outputs": {"application": {"probes": [{
            "receiver_id": 0, "probe_index": 2, "probe_start_ms": 20,
            "candidates": candidates,
        }]}},
        "application_pair_inventory": [{
            "receiver": 0, "first": observation,
            "second": {**observation, "probe_index": 4,
                       "probe_start_sample": 100_000,
                       "dwell_epoch_sample": 100_007.0},
        }],
    }


def test_frozen_receipt_selects_all_losses_and_two_anchors_per_rate_without_iq():
    receipt = runner.load_prior_receipt()
    selected = runner.selected_receiver_rows(receipt)
    assert len(selected) == 16
    assert sum(item["category"] == "k2_blind_lost_reference" for item in selected) == 12
    for rate in (2_500_000, 5_000_000):
        anchors = [item for item in selected
                   if item["rate_hz"] == rate and item["category"] == "matched_anchor"]
        assert len(anchors) == 2
        assert [item["receipt_row_index"] for item in anchors] == sorted(
            item["receipt_row_index"] for item in anchors
        )


def test_resolver_uses_lowest_rank_for_identical_duplicate():
    candidates = [_candidate(rank=5), _candidate(rank=2)]
    resolved = runner.resolve_observation(_row(candidates), _row(candidates)["application_pair_inventory"][0]["first"])
    assert resolved["candidate_rank"] == 2
    assert resolved["equivalent_candidate_ranks"] == [2, 5]
    assert resolved["acquired_cfo_hz"] == 100.0
    assert resolved["tracking_cfo_hz"] == 120.0


def test_resolver_rejects_acquired_cfo_ambiguity_hidden_by_tracking_cfo():
    candidates = [_candidate(rank=0, acquired=100, residual=20),
                  _candidate(rank=1, acquired=110, residual=10)]
    with pytest.raises(ValueError, match="scientifically different"):
        runner.resolve_observation(_row(candidates), _row(candidates)["application_pair_inventory"][0]["first"])


def test_strongest_pair_uses_minimum_margin_then_stable_inventory_index(monkeypatch):
    row = _row()
    first = row["application_pair_inventory"][0]
    second = copy.deepcopy(first)
    first["first"]["margin"], first["second"]["margin"] = .3, .4
    second["first"]["margin"], second["second"]["margin"] = .3, .8
    row["application_pair_inventory"] = [first, second]
    monkeypatch.setattr(runner, "resolved_pair", lambda _row, index, role: [{
        "acquired_cfo_hz": 0.0, "tracking_cfo_hz": 0.0,
    }] * 2)
    assert runner.select_pairs(row, 0)[0]["pair_inventory_index"] == 0


def _native_observation(**changes):
    value = {
        "receiver": 0, "probe_index": 0, "probe_start_sample": 0,
        "dwell_epoch_sample": 100.0, "tracking_cfo_hz": 1000.0,
        "margin": .2, "status": 0, "supported": True, "valid_bounds": True,
        "support_frames": 14, "fractional_complete": True,
    }
    value.update(changes)
    return value


def test_native_pair_assessment_requires_full_gates_identity_and_spacing():
    coordinates = [
        {"dwell_epoch_sample": 100, "tracking_cfo_hz": 1000},
        {"dwell_epoch_sample": 50_100, "tracking_cfo_hz": 1200},
    ]
    points = [
        {"observation": _native_observation()},
        {"observation": _native_observation(
            probe_index=2, probe_start_sample=50_000,
            dwell_epoch_sample=50_100.0, tracking_cfo_hz=1200.0,
        )},
    ]
    assert runner.assess_pair(points, coordinates, "native_guided", 2_500_000)["passed"]
    broken = copy.deepcopy(points)
    broken[1]["observation"]["support_frames"] = 1
    assert not runner.assess_pair(broken, coordinates, "native_guided", 2_500_000)["passed"]


def test_pair_timing_identity_is_circular_and_margin_gate_is_inclusive():
    rate = 2_500_000
    period = rate / 750.0
    coordinates = [
        {"dwell_epoch_sample": 100.0, "tracking_cfo_hz": 1000.0},
        {"dwell_epoch_sample": 50_100.0, "tracking_cfo_hz": 1200.0},
    ]
    points = [
        {"observation": _native_observation(
            dwell_epoch_sample=100.0 + period, margin=runner.MARGIN_GATE)},
        {"observation": _native_observation(
            probe_index=2, probe_start_sample=50_000,
            dwell_epoch_sample=50_100.0 - period, tracking_cfo_hz=1200.0,
            margin=runner.MARGIN_GATE)},
    ]
    assessment = runner.assess_pair(points, coordinates, "native_guided", rate)
    assert assessment["passed"]
    assert max(abs(item["timing_error_samples"])
               for item in assessment["point_assessments"]) < 1e-9


def test_canonical_reproduction_rejects_perturbed_science():
    coordinate = {
        "exact_score": .3, "control_score": .1, "reference_margin": .2,
        "residual_cfo_hz": 20.0, "tracking_cfo_hz": 120.0,
    }
    point = {
        "exact_score": .3, "control_score": .1, "margin": .2,
        "residual_cfo_hz": 20.0, "tracking_cfo_hz": 120.0,
    }
    runner.verify_canonical_reproduction(point, coordinate)
    changed = {**point, "exact_score": point["exact_score"] + 1e-7}
    with pytest.raises(ValueError, match="does not reproduce"):
        runner.verify_canonical_reproduction(changed, coordinate)


def test_native_range_is_scoring_plus_residual_not_absolute_physical():
    class Engine:
        def guided(self, *_args, **kwargs):
            self.kwargs = kwargs
            return None

    coordinate = {
        "receiver": 0, "probe_index": 0, "local_epoch_sample": 7,
        "acquired_cfo_hz": 398_000.0, "tracking_cfo_hz": 510_000.0,
    }
    engine = Engine()
    result = runner.native_point(engine, object(), coordinate)
    assert result["status"] == "native_guided_unsupported"
    assert engine.kwargs["expected_physical_cfo_hz"] == 510_000.0


def test_native_point_rejects_only_scoring_or_residual_out_of_range():
    class NeverCalled:
        def guided(self, *_args, **_kwargs):
            raise AssertionError("guided must not be called")

    base = {"receiver": 0, "probe_index": 0, "local_epoch_sample": 7,
            "acquired_cfo_hz": 400_001.0, "tracking_cfo_hz": 400_001.0}
    assert runner.native_point(NeverCalled(), object(), base)["status"] == "scoring_cfo_outside_known_range"
    residual = {**base, "acquired_cfo_hz": 0.0,
                "tracking_cfo_hz": runner.RESIDUAL_SUPPORT_HZ + 1}
    assert runner.native_point(NeverCalled(), object(), residual)["status"] == "expected_residual_outside_known_range"


def test_source_inventory_contains_all_prior_files_and_prior_receipt():
    files = runner.source_files()
    prior = runner.json.loads(runner.PRIOR_LOCK.read_text())["files"]
    assert set(prior).issubset(files)
    assert len(prior) == 74
    assert str(runner.PRIOR_RECEIPT.resolve()) in files
    assert str((runner.TG11 / "libtg11.so").resolve()) in files


def test_cli_requires_explicit_freeze_or_run():
    text = (HERE / "run_diagnostic.py").read_text()
    assert 'add_mutually_exclusive_group(required=True)' in text
    assert 'actions.add_argument("--run"' in text
    assert "validation" not in str(runner.RESULT)
