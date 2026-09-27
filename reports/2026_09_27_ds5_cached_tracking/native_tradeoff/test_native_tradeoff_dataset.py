from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent


def load_adapter():
    spec = importlib.util.spec_from_file_location("native_tradeoff_dataset", HERE / "tradeoff_dataset.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def pair_for(module, case, receiver: int, trajectory: str, probes=(0, 2)):
    pilot = next(item for item in case.receivers[receiver].pilots if item.trajectory_id == trajectory)
    period = case.rate / 750.0
    observations = []
    for probe in probes:
        start = probe * case.rate // 100
        local = pilot.frame_epoch_samples[0] % period
        observations.append(module.Observation(receiver, probe, start, start + local,
                                               float(pilot.cfo_hz), 0.2))
    return module.Pair(receiver, observations[0], observations[1])


def test_fixed_membership_and_validation_exclusion() -> None:
    module = load_adapter()
    assert len(module.legacy_controls()) == 32
    assert len(module.legacy_sequence_occurrences()) == 10
    assert len(module.diagnostic_development_cases()) == 26
    assert len(module.real_prefix_cases()) == 64
    cases = module.all_cases()
    assert len(cases) == len({case.id for case in cases}) == 132
    assert all(case.split == "development" for case in cases)
    diagnostic = module.diagnostic_development_cases()
    assert all(case.source_counter > 2**53 for case in diagnostic)
    assert {case.edge for case in diagnostic} == {"lower", "upper"}
    assert all(case.calibration_identity for case in cases)
    assert len(module.source_hashes()) == 5


def test_sequence_key_and_counter_geometry() -> None:
    module = load_adapter()
    diagnostic = module.diagnostic_development_cases()
    for rate in (2_500_000, 5_000_000):
        sequence = [case for case in diagnostic if case.rate == rate and case.sequence_id]
        assert [case.sequence_index for case in sequence] == [0, 1, 2, 3]
        assert len({case.state_key_prefix for case in sequence}) == 1
        assert [case.source_counter for case in sequence] == [
            sequence[0].source_counter + index * sequence[0].sample_count for index in range(4)
        ]


def test_load_iq_hash_geometry_and_read_only() -> None:
    module = load_adapter()
    cases = (module.legacy_controls()[0], module.diagnostic_development_cases()[0],
             module.real_prefix_cases()[0])
    for case in cases:
        values = module.load_iq(case)
        assert values.dtype == np.dtype("<i2")
        assert values.shape == (case.sample_count, 2, 2)
        assert not values.flags.writeable


def test_baseline_inventory_retains_every_qualifying_pair() -> None:
    module = load_adapter()
    case = module.diagnostic_development_cases()[0]
    candidate = lambda probe, epoch, cfo, margin: SimpleNamespace(
        epoch_sample=epoch, tracking_cfo_hz=cfo, margin=margin,
        passed_margin_gate=margin >= 0.025,
    )
    analysis = SimpleNamespace(probes=(
        SimpleNamespace(receiver_id=0, probe_index=0, probe_start_ms=0,
                        candidates=(candidate(0, 100, 10_000, 0.1),)),
        SimpleNamespace(receiver_id=0, probe_index=2, probe_start_ms=20,
                        candidates=(candidate(2, 100, 12_000, 0.2),)),
        SimpleNamespace(receiver_id=0, probe_index=4, probe_start_ms=40,
                        candidates=(candidate(4, 100, 14_000, 0.3),)),
        SimpleNamespace(receiver_id=1, probe_index=0, probe_start_ms=0,
                        candidates=(candidate(0, 100, 0, 0.01),)),
    ))
    inventory = module.reference_positive_pair_inventory(analysis, case)
    assert len(inventory) == 3
    assert all(pair.receiver == 0 for pair in inventory)


def test_detector_specific_symbol_support_and_no_late_only_false_negative() -> None:
    module = load_adapter()
    cases = module.diagnostic_development_cases()
    case = next(item for item in cases if item.rate == 2_500_000
                and item.cohort == "symbol-region-support")
    early = pair_for(module, case, 0, "early-pilot")
    late = pair_for(module, case, 1, "late-pilot")
    assert module.associate_pair_to_truth(early, case, 0, profile="baseline_early").matched
    assert module.associate_pair_to_truth(early, case, 0, profile="native_diverse").matched
    assert not module.associate_pair_to_truth(late, case, 1, profile="baseline_early").matched
    assert module.associate_pair_to_truth(late, case, 1, profile="native_diverse").matched
    assessment = module.assess_receiver(None, (), case, 1, profile="baseline_early")
    assert assessment["physical_outcome"] == "regional_not_scored"
    assert assessment["activity_policy_passed"] is None


def test_low_snr_presence_and_reference_extra_are_separate() -> None:
    module = load_adapter()
    case = next(item for item in module.diagnostic_development_cases()
                if item.cohort == "ladder")
    pair = pair_for(module, case, 0, "pilot")
    assessment = module.assess_receiver(pair, (), case, 0, profile="native_diverse")
    assert assessment["reference_outcome"] == "reference_extra"
    assert assessment["physical_outcome"] == "truth_associated_positive"
    assert assessment["truth_activity_policy"] == "presence_report_only"
    assert assessment["activity_policy_passed"] is None

    shifted = module.Pair(
        pair.receiver,
        module.Observation(pair.receiver, pair.first.probe_index,
                           pair.first.probe_start_sample,
                           pair.first.dwell_epoch_sample + case.rate * 4e-6,
                           pair.first.tracking_cfo_hz + 20_000, pair.first.margin),
        module.Observation(pair.receiver, pair.second.probe_index,
                           pair.second.probe_start_sample,
                           pair.second.dwell_epoch_sample + case.rate * 4e-6,
                           pair.second.tracking_cfo_hz + 20_000, pair.second.margin),
    )
    missed = module.associate_pair_to_truth(shifted, case, 0, profile="native_diverse")
    assert not missed.matched
    assert missed.trajectory_id == "pilot"
    assert missed.timing_errors_samples is not None
    assert missed.cfo_errors_hz == (20_000.0, 20_000.0)


def test_receiver_policy_handles_mixed_dropout_and_recorded_unknown() -> None:
    module = load_adapter()
    mixed = next(
        case for case in module.diagnostic_development_cases()
        if case.sequence_id and any(receiver.constructed_negative for receiver in case.receivers)
        and any(receiver.pilots for receiver in case.receivers)
    )
    negative_receiver = next(receiver.receiver for receiver in mixed.receivers
                             if receiver.constructed_negative)
    assessment = module.assess_receiver(None, (), mixed, negative_receiver)
    assert assessment["truth_activity_policy"] == "required_inactive"
    assert assessment["activity_policy_passed"] is True

    recorded = module.real_prefix_cases()[0]
    pair = module.Pair(
        0,
        module.Observation(0, 0, 0, 100.0, 0.0, 0.2),
        module.Observation(0, 2, recorded.rate * 20 // 1_000,
                           recorded.rate * 20 // 1_000 + 100.0, 0.0, 0.2),
    )
    assessment = module.assess_receiver(pair, (), recorded, 0)
    assert assessment["physical_outcome"] == "recorded_unknown_positive"
    assert assessment["truth_activity_policy"] == "recorded_unknown"
    assert assessment["activity_policy_passed"] is None


def test_exact_source_mapping_above_float_integer_precision() -> None:
    module = load_adapter()
    case = module.diagnostic_development_cases()[0]
    observation = SimpleNamespace(dwell_epoch_sample=12345.375)
    counter, fraction = module.map_source_coordinate(case, observation)
    assert counter == case.source_counter + 12345
    assert fraction == 0.375
