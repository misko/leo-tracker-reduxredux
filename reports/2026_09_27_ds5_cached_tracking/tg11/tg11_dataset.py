"""Frozen TG11-v1 dataset adapters and scientific comparison helpers.

This report module references existing immutable NPY arrays.  It never rewrites
or synthesizes IQ.  Synthetic sequence occurrences carry virtual counter and
carrier-phase mappings explicitly so repeated arrays are not presented as new
physical recordings.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ROOT = HERE.parents[2]
NEW_DATA = REPORT / "new_data"
ORIGINAL_CONTROLS = ROOT / "reports/2026_09_26_ds5_server_eval/dataset"
LAG3_CONTROLS = REPORT / "lag3_controls"

SOURCE_HASHES = {
    NEW_DATA / "cases.json": "b1a7a557a58de5adfe0af87e034ddde4737df18d917fc6536331146bff62a845",
    ORIGINAL_CONTROLS / "cases.json": "ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48",
    LAG3_CONTROLS / "cases.json": "5bc58aab84ce75d3704d08a294333010745caec382da5f059b04c9e5a5473188",
}
RATES = (2_500_000, 5_000_000)
DWELL_MS = 120
MARGIN_GATE = 0.025
CFO_GATE_HZ = 8_000.0
TIMING_GATE_S = 2e-6


@dataclass(frozen=True, slots=True)
class InjectedComponent:
    kind: str
    trajectory_id: str
    cfo_hz: float | None
    frequency_hz: float | None
    frame_epoch_samples: tuple[float, ...]
    injection_start_sample: int
    injection_stop_sample: int


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    rate: int
    edge: str
    channel: int
    source_counter: int
    session: str
    raw_path: Path
    raw_sha256: str
    injected: tuple[tuple[InjectedComponent, ...], tuple[InjectedComponent, ...]]
    origin: str
    visit_index: int | None
    tuning_identity: str
    calibration_identity: str
    raw_source_counter: int | None
    virtual_counter_delta_samples: int
    frame_lattice_phase_offset_samples: float
    carrier_phase_reset: bool
    carrier_phase_offsets_cycles: tuple[tuple[float | None, ...], tuple[float | None, ...]]

    @property
    def sample_count(self) -> int:
        return self.rate * DWELL_MS // 1_000

    @property
    def state_key_prefix(self) -> tuple[str, int, str, int, str, str]:
        return (
            self.session,
            self.channel,
            self.edge,
            self.rate,
            self.tuning_identity,
            self.calibration_identity,
        )


@dataclass(frozen=True, slots=True)
class SequenceStep:
    case: Case
    expected_active: bool
    expected_route: str | None
    note: str


@dataclass(frozen=True, slots=True)
class ControlSequence:
    id: str
    purpose: str
    steps: tuple[SequenceStep, ...]
    declared_gate: str

    @property
    def cases(self) -> tuple[Case, ...]:
        return tuple(step.case for step in self.steps)


@dataclass(frozen=True, slots=True)
class ReferenceObservation:
    receiver: int
    probe_index: int
    probe_start_sample: int
    dwell_epoch_sample: float
    tracking_cfo_hz: float
    margin: float


@dataclass(frozen=True, slots=True)
class ReferencePair:
    receiver: int
    first: ReferenceObservation
    second: ReferenceObservation


@dataclass(frozen=True, slots=True)
class Association:
    matched: bool
    receiver: int | None
    trajectory_id: str | None
    timing_errors_samples: tuple[float, float] | None
    cfo_errors_hz: tuple[float, float] | None
    reason: str


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def verify_sources() -> None:
    changed = [str(path) for path, expected in SOURCE_HASHES.items() if _digest(path) != expected]
    if changed:
        raise ValueError(f"TG11 frozen source manifest changed: {changed}")


def _read(path: Path) -> dict:
    return json.loads(path.read_text())


def _empty_injected() -> tuple[tuple[InjectedComponent, ...], tuple[InjectedComponent, ...]]:
    return ((), ())


def _real_case(raw: dict) -> Case:
    return Case(
        id=raw["case_id"],
        rate=raw["rate_hz"],
        edge=raw["edge"],
        channel=raw["channel"],
        source_counter=raw["source_start_counter"],
        session=raw["session_id"],
        raw_path=(NEW_DATA / raw["raw_npy"]["path"]).resolve(),
        raw_sha256=raw["raw_npy"]["sha256"],
        injected=_empty_injected(),
        origin="recorded_development",
        visit_index=raw["visit_index"],
        tuning_identity=f"recording:{raw['session_id']}:channel:{raw['channel']}:edge:{raw['edge']}",
        calibration_identity="recording-fixed-unknown-calibration",
        raw_source_counter=raw["source_start_counter"],
        virtual_counter_delta_samples=0,
        frame_lattice_phase_offset_samples=0.0,
        carrier_phase_reset=False,
        carrier_phase_offsets_cycles=((), ()),
    )


def real_cases() -> tuple[Case, ...]:
    """Return the first 32 manifest-ordered development visits at each rate."""

    verify_sources()
    raw_cases = _read(NEW_DATA / "cases.json")["cases"]
    selected: list[Case] = []
    for rate in RATES:
        at_rate = [raw for raw in raw_cases if raw["split"] == "dev" and raw["rate_hz"] == rate]
        if len(at_rate) < 32:
            raise ValueError(f"insufficient frozen development visits at {rate}")
        chosen = at_rate[:32]
        if [raw["block_offset"] for raw in chosen] != list(range(32)):
            raise ValueError("TG11 real prefix is not the first manifest block segment")
        selected.extend(_real_case(raw) for raw in chosen)
    return tuple(selected)


def timing_cases() -> tuple[Case, ...]:
    cases = real_cases()
    return tuple(case for rate in RATES for case in [item for item in cases if item.rate == rate][:2])


def _old_components(raw: dict, receiver: int) -> tuple[InjectedComponent, ...]:
    truth = raw["truth"]
    receiver_truth = truth["receivers"][receiver]
    kind = truth["kind"]
    if kind == "pilot":
        period = raw["rate_hz"] / 750.0
        window_start = receiver_truth["window"] * (raw["rate_hz"] // 50)
        base = (
            window_start
            + receiver_truth["epoch_samples"]
            + receiver_truth["fractional_delay_samples"]
        )
        frames = tuple(base + round(index * period) for index in range(15))
        return (
            InjectedComponent(
                kind="pilot",
                trajectory_id="pilot",
                cfo_hz=float(receiver_truth["cfo_hz"]),
                frequency_hz=None,
                frame_epoch_samples=frames,
                injection_start_sample=window_start,
                injection_stop_sample=window_start + raw["rate_hz"] // 50,
            ),
        )
    if kind == "tone":
        return (
            InjectedComponent(
                kind="tone",
                trajectory_id="tone",
                cfo_hz=None,
                frequency_hz=float(receiver_truth["carrier_hz"]),
                frame_epoch_samples=(),
                injection_start_sample=0,
                injection_stop_sample=raw["rate_hz"] * DWELL_MS // 1_000,
            ),
        )
    return ()


def _lag_components(raw: dict, receiver: int) -> tuple[InjectedComponent, ...]:
    receiver_truth = raw["injected"]["receivers"][receiver]
    components = []
    for component in receiver_truth["components"]:
        kind = component["type"]
        frames = tuple(
            float(frame["physical_start_samples"])
            for frame in component.get("frame_coordinates", ())
        )
        components.append(
            InjectedComponent(
                kind=kind,
                trajectory_id=component.get("trajectory_id", kind),
                cfo_hz=(float(component["cfo_hz"]) if kind == "pilot" else None),
                frequency_hz=(float(component["frequency_hz"]) if kind == "tone" else None),
                frame_epoch_samples=frames,
                injection_start_sample=0,
                injection_stop_sample=raw["rate_hz"] * DWELL_MS // 1_000,
            )
        )
    return tuple(components)


def _synthetic_case(raw: dict, base: Path, ordinal: int, *, lag: bool) -> Case:
    rate = raw["rate_hz"]
    raw_counter = raw.get("source_start_counter")
    virtual = raw_counter if raw_counter is not None else 8_000_000_000 + ordinal * rate
    injected = tuple(
        _lag_components(raw, receiver) if lag else _old_components(raw, receiver)
        for receiver in (0, 1)
    )
    return Case(
        id=raw["case_id"],
        rate=rate,
        edge=raw["edge"],
        channel=raw.get("channel", 1),
        source_counter=virtual,
        session=f"control-single:{raw['case_id']}",
        raw_path=(base / raw["raw_npy"]["path"]).resolve(),
        raw_sha256=raw["raw_npy"]["sha256"],
        injected=injected,  # type: ignore[arg-type]
        origin="lag3_adversarial_control" if lag else "original_synthetic_control",
        visit_index=None,
        tuning_identity=f"control-single:{raw['case_id']}",
        calibration_identity="constructed-zero-calibration",
        raw_source_counter=raw_counter,
        virtual_counter_delta_samples=(0 if raw_counter is None else virtual - raw_counter),
        frame_lattice_phase_offset_samples=0.0,
        carrier_phase_reset=False,
        carrier_phase_offsets_cycles=tuple(
            tuple(0.0 for _ in receiver_components) for receiver_components in injected
        ),  # type: ignore[arg-type]
    )


def control_cases() -> tuple[Case, ...]:
    """Return 12 original and 20 adversarial physical cases (64 RX rows)."""

    verify_sources()
    old_raw = [
        raw
        for raw in _read(ORIGINAL_CONTROLS / "cases.json")["cases"]
        if raw["origin"] == "synthetic_control" and raw["rate_hz"] in RATES
    ]
    lag_raw = _read(LAG3_CONTROLS / "cases.json")["cases"]
    if len(old_raw) != 12 or len(lag_raw) != 20:
        raise ValueError("TG11 frozen control inventory changed")
    old = tuple(
        _synthetic_case(raw, ORIGINAL_CONTROLS, ordinal, lag=False)
        for ordinal, raw in enumerate(old_raw)
    )
    lag = tuple(
        _synthetic_case(raw, LAG3_CONTROLS, ordinal, lag=True)
        for ordinal, raw in enumerate(lag_raw)
    )
    return old + lag


def control_receiver_cases() -> tuple[tuple[Case, int], ...]:
    return tuple((case, receiver) for case in control_cases() for receiver in (0, 1))


def _frequencies(case: Case, receiver: int) -> tuple[float | None, ...]:
    return tuple(
        component.cfo_hz if component.kind == "pilot" else component.frequency_hz
        for component in case.injected[receiver]
    )


def _sequence_occurrence(
    base: Case,
    *,
    sequence_id: str,
    index: int,
    virtual_start: int,
) -> Case:
    raw_origin = virtual_start if base.raw_source_counter is None else base.raw_source_counter
    delta = virtual_start - raw_origin
    period = Fraction(base.rate, 750)
    phase_samples = float(Fraction(delta, 1) % period)
    phase_offsets = tuple(
        tuple(
            None
            if frequency is None
            else float((-Fraction(str(frequency)) * delta / base.rate) % 1)
            for frequency in _frequencies(base, receiver)
        )
        for receiver in (0, 1)
    )
    return replace(
        base,
        id=f"{sequence_id}-step{index:02d}-{base.id}",
        source_counter=virtual_start,
        session=f"control-sequence:{sequence_id}",
        channel=1,
        tuning_identity=f"control-sequence:{sequence_id}:channel1:{base.edge}",
        calibration_identity=f"control-sequence:{sequence_id}:fixed-calibration",
        virtual_counter_delta_samples=delta,
        frame_lattice_phase_offset_samples=phase_samples,
        carrier_phase_reset=True,
        carrier_phase_offsets_cycles=phase_offsets,  # type: ignore[arg-type]
        origin="constructed_metadata_sequence_reusing_frozen_iq",
    )


def control_sequences() -> tuple[ControlSequence, ...]:
    """Return the three frozen causal sequences without copying their arrays."""

    by_id = {case.id: case for case in control_cases()}
    specs = (
        (
            "quiet-to-pilot",
            "first pilot-bearing visit must route blind and find the injected pilot",
            (
                ("lag3-r2500000-noise", False, None, "quiet prefix"),
                ("lag3-r2500000-noise", False, None, "quiet prefix"),
                ("lag3-r2500000-pilot-cfo0-int", True, "blind", "first pilot-bearing visit"),
            ),
            20_000_000_000,
        ),
        (
            "pilot-dropout",
            "noise and tone visits after establishment must not emit stale active",
            (
                ("lag3-r2500000-pilot-cfo0-int", True, "blind", "blind establishment"),
                ("lag3-r2500000-pilot-cfo0-int", True, None, "track continuation"),
                ("lag3-r2500000-noise", False, None, "dropout to noise"),
                ("control-tone-lower-s3901-3902", False, None, "dropout to tone"),
            ),
            21_000_000_000,
        ),
        (
            "changed-pilot",
            "changed timing/CFO must fail open to blind and associate to the current pilot",
            (
                ("lag3-r2500000-pilot-cfo0-int", True, "blind", "blind establishment"),
                ("lag3-r2500000-pilot-cfo0-int", True, None, "track continuation"),
                (
                    "lag3-r2500000-pilot-cfom399k-fracm49",
                    True,
                    "blind",
                    "different timing and CFO",
                ),
            ),
            22_000_000_000,
        ),
    )
    sequences = []
    for sequence_id, gate, step_specs, start in specs:
        steps = tuple(
            SequenceStep(
                case=_sequence_occurrence(
                    by_id[case_id],
                    sequence_id=sequence_id,
                    index=index,
                    virtual_start=start + index * (2_500_000 * DWELL_MS // 1_000),
                ),
                expected_active=expected_active,
                expected_route=expected_route,
                note=note,
            )
            for index, (case_id, expected_active, expected_route, note) in enumerate(step_specs)
        )
        sequences.append(ControlSequence(sequence_id, gate, steps, gate))
    return tuple(sequences)


def load_iq(case: Case) -> np.ndarray:
    if _digest(case.raw_path) != case.raw_sha256.removeprefix("sha256:"):
        raise ValueError(f"TG11 IQ hash mismatch: {case.id}")
    values = np.load(case.raw_path, mmap_mode="r", allow_pickle=False)
    if values.dtype != np.dtype("<i2") or values.shape != (case.sample_count, 2, 2):
        raise ValueError(f"TG11 IQ geometry mismatch: {case.id}")
    values.setflags(write=False)
    return values


def _get(value: Any, name: str) -> Any:
    return value[name] if isinstance(value, dict) else getattr(value, name)


def reference_positive_pair_inventory(analysis: Any, case: Case) -> tuple[ReferencePair, ...]:
    """Enumerate every comparator-positive pair, not only its returned first hit."""

    passing: dict[int, list[ReferenceObservation]] = {0: [], 1: []}
    for probe in _get(analysis, "probes"):
        receiver = int(_get(probe, "receiver_id"))
        probe_index = int(_get(probe, "probe_index"))
        probe_start_sample = int(_get(probe, "probe_start_ms") * case.rate // 1_000)
        for candidate in _get(probe, "candidates"):
            margin = float(_get(candidate, "margin"))
            passed = bool(_get(candidate, "passed_margin_gate"))
            if not passed or margin < MARGIN_GATE:
                continue
            passing.setdefault(receiver, []).append(
                ReferenceObservation(
                    receiver=receiver,
                    probe_index=probe_index,
                    probe_start_sample=probe_start_sample,
                    dwell_epoch_sample=(
                        probe_start_sample + float(_get(candidate, "epoch_sample"))
                    ),
                    tracking_cfo_hz=float(_get(candidate, "tracking_cfo_hz")),
                    margin=margin,
                )
            )
    pairs = []
    minimum_gap = case.rate * 20 // 1_000
    for receiver, observations in passing.items():
        for first_index, first in enumerate(observations):
            for second in observations[first_index + 1 :]:
                if second.probe_start_sample - first.probe_start_sample < minimum_gap:
                    continue
                if abs(second.tracking_cfo_hz - first.tracking_cfo_hz) > CFO_GATE_HZ:
                    continue
                pairs.append(ReferencePair(receiver, first, second))
    return tuple(pairs)


def _pair(value: Any) -> Any | None:
    if value is None:
        return None
    if hasattr(value, "active") or isinstance(value, dict) and "active" in value:
        return _get(value, "pair") if bool(_get(value, "active")) else None
    return value


def _dwell_epoch(observation: Any) -> float:
    try:
        return float(_get(observation, "dwell_epoch_sample"))
    except (AttributeError, KeyError, TypeError):
        return float(_get(observation, "probe_start_sample")) + float(
            _get(observation, "local_epoch_sample")
        )


def _observation_match(
    observation: Any,
    component: InjectedComponent,
    case: Case,
) -> tuple[float, float] | None:
    if not bool(_get(observation, "supported")) or not bool(
        _get(observation, "fractional_complete")
    ) or float(_get(observation, "margin")) < MARGIN_GATE:
        return None
    epochs = component.frame_epoch_samples
    probe_start = int(_get(observation, "probe_start_sample"))
    if _supported_frame_count(case, component, probe_start) < 2:
        return None
    epoch = _dwell_epoch(observation)
    period = case.rate / 750.0
    errors = [
        abs((epoch - relative + period / 2) % period - period / 2)
        for relative in epochs
    ]
    if not errors:
        return None
    timing_error = min(errors)
    cfo_error = abs(
        float(_get(observation, "tracking_cfo_hz")) - (component.cfo_hz or 0.0)
    )
    if timing_error > case.rate * TIMING_GATE_S or cfo_error > CFO_GATE_HZ:
        return None
    return timing_error, cfo_error


def _supported_frame_count(case: Case, component: InjectedComponent, probe_start: int) -> int:
    """Count frames whose GLRT symbols 2..65 have real injected support."""

    probe_stop = probe_start + case.rate // 50
    symbol_samples = case.rate * 44 / 10_000_000
    glrt_start = round(2 * symbol_samples)
    glrt_stop = round(66 * symbol_samples)
    return sum(
        probe_start <= frame + glrt_start
        and frame + glrt_stop <= probe_stop
        and component.injection_start_sample <= frame + glrt_start
        and frame + glrt_stop <= component.injection_stop_sample
        for frame in component.frame_epoch_samples
    )


def supporting_probe_indices(case: Case, component: InjectedComponent) -> tuple[int, ...]:
    """Natural 20 ms probes containing at least two injected frame starts."""

    stride = case.rate // 100
    return tuple(
        probe_index
        for probe_index in range(11)
        if _supported_frame_count(case, component, probe_index * stride) >= 2
    )


def _component_supports_pair(case: Case, component: InjectedComponent) -> bool:
    probes = supporting_probe_indices(case, component)
    return any(second - first >= 2 for index, first in enumerate(probes) for second in probes[index + 1 :])


def _pair_contract_error(pair: Any, case: Case) -> str | None:
    receiver = int(_get(pair, "receiver"))
    first, second = _get(pair, "first"), _get(pair, "second")
    if int(_get(first, "receiver")) != receiver or int(_get(second, "receiver")) != receiver:
        return "pair members do not share the selected receiver"
    if (
        int(_get(second, "probe_start_sample")) - int(_get(first, "probe_start_sample"))
        < case.rate * 20 // 1_000
    ):
        return "pair windows overlap"
    if abs(
        float(_get(second, "tracking_cfo_hz"))
        - float(_get(first, "tracking_cfo_hz"))
    ) > CFO_GATE_HZ:
        return "pair CFOs are inconsistent"
    for observation in (first, second):
        if not bool(_get(observation, "supported")):
            return "pair contains an unsupported observation"
        if not bool(_get(observation, "fractional_complete")):
            return "pair contains a fractionally incomplete observation"
        if float(_get(observation, "margin")) < MARGIN_GATE:
            return "pair contains an observation below the inclusive margin gate"
    return None


def compare_candidate_pair_to_truth(result_or_pair: Any, case: Case, receiver: int) -> Association:
    """Apply constructed truth gates to one receiver result."""

    pair = _pair(result_or_pair)
    pilots = tuple(
        component
        for component in case.injected[receiver]
        if component.kind == "pilot" and _component_supports_pair(case, component)
    )
    if pair is None:
        if pilots:
            return Association(False, receiver, None, None, None, "injected pilot was inactive")
        return Association(True, receiver, None, None, None, "noise/tone control remained inactive")
    pair_receiver = int(_get(pair, "receiver"))
    if pair_receiver != receiver:
        return Association(False, pair_receiver, None, None, None, "pair selected another receiver")
    if not pilots:
        return Association(False, receiver, None, None, None, "noise/tone control became active")
    contract_error = _pair_contract_error(pair, case)
    if contract_error is not None:
        return Association(False, receiver, None, None, None, contract_error)
    first, second = _get(pair, "first"), _get(pair, "second")
    for component in pilots:
        first_match = _observation_match(first, component, case)
        second_match = _observation_match(second, component, case)
        if first_match is not None and second_match is not None:
            return Association(
                True,
                receiver,
                component.trajectory_id,
                (first_match[0], second_match[0]),
                (first_match[1], second_match[1]),
                "both fresh observations associate to one injected trajectory",
            )
    return Association(False, receiver, None, None, None, "active pair misses injected trajectories")


def validate_control(case: Case, receiver: int, result: Any) -> dict:
    """Return a JSON-ready truth gate for one of the 64 frozen control receivers."""

    association = compare_candidate_pair_to_truth(result, case, receiver)
    pilot_trajectories = [
        component.trajectory_id
        for component in case.injected[receiver]
        if component.kind == "pilot" and _component_supports_pair(case, component)
    ]
    active = bool(_get(result, "active"))
    return {
        "case_id": case.id,
        "receiver": receiver,
        "rate_hz": case.rate,
        "edge": case.edge,
        "expected": "active_associated" if pilot_trajectories else "inactive",
        "pilot_trajectories": pilot_trajectories,
        "observed_active": active,
        "passed": association.matched,
        "matched_trajectory": association.trajectory_id,
        "timing_errors_samples": association.timing_errors_samples,
        "cfo_errors_hz": association.cfo_errors_hz,
        "reason": association.reason,
    }


def associate_candidate_to_reference(
    result_or_pair: Any,
    inventory: tuple[ReferencePair, ...],
    case: Case,
) -> Association:
    pair = _pair(result_or_pair)
    if pair is None:
        return Association(False, None, None, None, None, "candidate inactive")
    receiver = int(_get(pair, "receiver"))
    contract_error = _pair_contract_error(pair, case)
    if contract_error is not None:
        return Association(False, receiver, None, None, None, contract_error)
    observations = (_get(pair, "first"), _get(pair, "second"))
    period = case.rate / 750.0
    for reference in inventory:
        if reference.receiver != receiver:
            continue
        timing_errors = []
        cfo_errors = []
        for observation, expected in zip(observations, (reference.first, reference.second), strict=True):
            delta = _dwell_epoch(observation) - expected.dwell_epoch_sample
            circular = abs((delta + period / 2) % period - period / 2)
            timing_errors.append(circular)
            cfo_errors.append(
                abs(float(_get(observation, "tracking_cfo_hz")) - expected.tracking_cfo_hz)
            )
        if max(timing_errors) <= case.rate * TIMING_GATE_S and max(cfo_errors) <= CFO_GATE_HZ:
            return Association(
                True,
                receiver,
                None,
                tuple(timing_errors),  # type: ignore[arg-type]
                tuple(cfo_errors),  # type: ignore[arg-type]
                "candidate pair associates to comparator inventory",
            )
    return Association(False, receiver, None, None, None, "candidate pair misses comparator inventory")


def membership_digest() -> str:
    payload = {
        "real": [case.id for case in real_cases()],
        "controls": [case.id for case in control_cases()],
        "sequences": [
            {"id": sequence.id, "cases": [case.id for case in sequence.cases]}
            for sequence in control_sequences()
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


# Stable runner-facing aliases named in RUN_PROTOCOL.md.
controls = control_cases
sequences = control_sequences
control_gate = validate_control
