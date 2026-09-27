from __future__ import annotations

import json
import hashlib
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tg11_dataset as data  # noqa: E402


def observation(case, receiver, epoch, cfo, probe_start):
    return SimpleNamespace(
        receiver=receiver,
        probe_index=probe_start // (case.rate // 100),
        probe_start_sample=probe_start,
        local_epoch_sample=epoch - probe_start,
        dwell_epoch_sample=epoch,
        source_epoch_counter=case.source_counter + int(epoch),
        source_epoch_fraction=epoch - int(epoch),
        acquired_cfo_hz=cfo,
        tracking_cfo_hz=cfo,
        margin=0.2,
        fractional_complete=True,
        supported=True,
        fitted=True,
    )


def test_frozen_membership_and_manifest_order() -> None:
    real = data.real_cases()
    controls = data.controls()
    assert len(real) == 64
    assert len(data.timing_cases()) == 4
    assert len(controls) == 32
    assert len(data.control_receiver_cases()) == 64
    assert [case.visit_index for case in real[:32]] == list(range(1077, 1109))
    assert [case.visit_index for case in real[32:]] == list(range(1077, 1109))
    assert {case.rate for case in controls} == {2_500_000, 5_000_000}
    assert data.membership_digest() == "41c3e268e52a7c8295c64ec0e137e28d153d99bf1a232e9517c5958dc7ededb7"


def test_load_iq_checks_hash_dtype_geometry_and_is_read_only() -> None:
    case = data.controls()[0]
    values = data.load_iq(case)
    assert values.dtype == np.dtype("<i2")
    assert values.shape == (case.sample_count, 2, 2)
    assert not values.flags.writeable


def test_sequences_reuse_arrays_with_explicit_counter_and_phase_mapping() -> None:
    sequences = {sequence.id: sequence for sequence in data.sequences()}
    assert set(sequences) == {"quiet-to-pilot", "pilot-dropout", "changed-pilot"}
    for sequence in sequences.values():
        for index, step in enumerate(sequence.steps):
            case = step.case
            if index:
                prior = sequence.steps[index - 1].case
                assert case.source_counter - prior.source_counter == case.sample_count
            assert case.carrier_phase_reset is True
            assert case.raw_path.exists()
            assert case.virtual_counter_delta_samples == (
                case.source_counter
                - (case.raw_source_counter if case.raw_source_counter is not None else case.source_counter)
            )
    repeated = sequences["pilot-dropout"].steps[:2]
    assert repeated[0].case.raw_path == repeated[1].case.raw_path
    assert repeated[0].case.raw_sha256 == repeated[1].case.raw_sha256
    assert repeated[0].case.frame_lattice_phase_offset_samples == 0.0
    assert repeated[1].case.frame_lattice_phase_offset_samples == 0.0
    assert repeated[0].case.carrier_phase_offsets_cycles == ((0.0,), (0.0,))
    assert repeated[1].case.carrier_phase_offsets_cycles == ((0.0,), (0.0,))


def test_every_finite_original_pilot_has_only_the_actual_supported_probe_pair() -> None:
    pilots = [
        case
        for case in data.controls()
        if case.origin == "original_synthetic_control" and case.injected[0]
        and case.injected[0][0].kind == "pilot"
    ]
    assert len(pilots) == 4
    for case in pilots:
        expected = (1, 2, 3) if case.edge == "lower" else (7, 8, 9)
        for receiver in (0, 1):
            component = case.injected[receiver][0]
            assert data.supporting_probe_indices(case, component) == expected
            nonoverlap = [
                (first, second)
                for index, first in enumerate(expected)
                for second in expected[index + 1 :]
                if second - first >= 2
            ]
            assert nonoverlap == [(expected[0], expected[2])]


def test_control_gate_single_pilot_noise_and_wrong_trajectory() -> None:
    pilot = next(case for case in data.controls() if case.id == "lag3-r2500000-pilot-cfo0-int")
    component = pilot.injected[0][0]
    first_epoch = min(value for value in component.frame_epoch_samples if value >= 0)
    second_epoch = min(
        value
        for value in component.frame_epoch_samples
        if value - first_epoch >= pilot.rate * 20 // 1_000
    )
    pair = SimpleNamespace(
        receiver=0,
        first=observation(pilot, 0, first_epoch, component.cfo_hz, 0),
        second=observation(
            pilot, 0, second_epoch, component.cfo_hz, pilot.rate * 20 // 1_000
        ),
    )
    result = SimpleNamespace(active=True, pair=pair)
    gate = data.control_gate(pilot, 0, result)
    assert gate["passed"] is True
    assert gate["matched_trajectory"] == "pilot"

    wrong = SimpleNamespace(
        active=True,
        pair=SimpleNamespace(
            receiver=0,
            first=observation(pilot, 0, first_epoch + 100, 20_000, 0),
            second=observation(pilot, 0, second_epoch + 100, 20_000, 50_000),
        ),
    )
    assert data.control_gate(pilot, 0, wrong)["passed"] is False
    noise = next(case for case in data.controls() if case.id == "lag3-r2500000-noise")
    assert data.control_gate(noise, 0, SimpleNamespace(active=False, pair=None))["passed"] is True
    assert data.control_gate(noise, 0, result)["passed"] is False

    # The original controls contain a finite 20 ms injection. Probes starting
    # at 10 and 30 ms see different injected halves and are nonoverlapping;
    # phase association is circular but actual injected support is aperture-local.
    old = next(case for case in data.controls() if case.id == "control-pilot-lower-s1901-1902")
    old_component = old.injected[0][0]
    period = old.rate / 750
    assert data.supporting_probe_indices(old, old_component) == (1, 2, 3)
    first_start, second_start = old.rate // 100, 3 * old.rate // 100
    first_epoch = min(value for value in old_component.frame_epoch_samples if value >= first_start)
    second_epoch = min(value for value in old_component.frame_epoch_samples if value >= second_start)
    old_pair = SimpleNamespace(
        receiver=0,
        first=observation(old, 0, first_epoch, old_component.cfo_hz, first_start),
        second=observation(
            old,
            0,
            second_epoch,
            old_component.cfo_hz,
            second_start,
        ),
    )
    assert data.control_gate(old, 0, SimpleNamespace(active=True, pair=old_pair))["passed"]

    # Circularly identical epochs in probes outside the finite injection are
    # not fresh injected observations and must fail association.
    extrapolated = SimpleNamespace(
        receiver=0,
        first=observation(old, 0, first_epoch - 8 * period, old_component.cfo_hz, 0),
        second=observation(
            old,
            0,
            second_epoch + 45 * period,
            old_component.cfo_hz,
            5 * old.rate // 100,
        ),
    )
    assert not data.control_gate(
        old, 0, SimpleNamespace(active=True, pair=extrapolated)
    )["passed"]


def test_reference_inventory_uses_all_full_response_pairs_and_safe_dwell_coordinates() -> None:
    case = replace(data.real_cases()[0], source_counter=2**60 + 123)

    def candidate(epoch, cfo, margin=0.1):
        return SimpleNamespace(
            epoch_sample=epoch,
            tracking_cfo_hz=cfo,
            margin=margin,
            passed_margin_gate=margin >= 0.025,
        )

    probes = (
        SimpleNamespace(receiver_id=0, probe_index=0, probe_start_ms=0, candidates=(candidate(200, 1_000),)),
        SimpleNamespace(receiver_id=0, probe_index=1, probe_start_ms=10, candidates=(candidate(300, 1_100),)),
        SimpleNamespace(receiver_id=0, probe_index=2, probe_start_ms=20, candidates=(candidate(400, 8_999),)),
        SimpleNamespace(receiver_id=1, probe_index=0, probe_start_ms=0, candidates=(candidate(500, 2_000),)),
        SimpleNamespace(receiver_id=1, probe_index=2, probe_start_ms=20, candidates=(candidate(600, 10_001),)),
    )
    inventory = data.reference_positive_pair_inventory(SimpleNamespace(probes=probes), case)
    assert len(inventory) == 1
    reference = inventory[0]
    assert reference.receiver == 0
    assert reference.first.dwell_epoch_sample == 200
    assert reference.second.dwell_epoch_sample == case.rate * 20 // 1_000 + 400
    assert not hasattr(reference.first, "source_epoch_sample")

    period = case.rate / 750
    pair = SimpleNamespace(
        receiver=0,
        first=observation(case, 0, 200 + period, 1_000, 0),
        second=observation(
            case,
            0,
            case.rate * 20 // 1_000 + 400 + period,
            8_999,
            case.rate * 20 // 1_000,
        ),
    )
    association = data.associate_candidate_to_reference(pair, inventory, case)
    assert association.matched is True
    assert max(association.timing_errors_samples or ()) < 1e-9


def test_design_matches_helper_contract() -> None:
    design = json.loads((HERE / "design.json").read_text())
    assert design["status"] == "frozen_before_tg11_outcomes"
    assert design["membership"]["sha256"] == "sha256:" + data.membership_digest()
    assert design["membership"]["control_receiver_streams"] == len(
        data.control_receiver_cases()
    )
    assert design["association"]["coordinate"].startswith("within-dwell")
    governing = HERE.parent / "application_coarse_alternatives/TRACK_GUIDED_DESIGN.md"
    assert design["governing_design"]["sha256"] == (
        "sha256:" + hashlib.sha256(governing.read_bytes()).hexdigest()
    )
