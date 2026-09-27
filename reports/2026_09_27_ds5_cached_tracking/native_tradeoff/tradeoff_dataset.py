"""Read-only corpus and truth-association port for the native tradeoff study."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
TG11 = REPORT / "tg11"
DIAGNOSTIC = REPORT / "tg11_diagnostic" / "dataset"
ORIGINAL_CONTROLS = REPORT.parent / "2026_09_26_ds5_server_eval" / "dataset"
NEW_DATA = REPORT / "new_data"
LAG3_CONTROLS = REPORT / "lag3_controls"

TG11_DATASET_SHA256 = "sha256:5f99db692bce15988055208744138e849f45752ee232a4ea2f0fbd2960841012"
DIAGNOSTIC_MANIFEST_SHA256 = "sha256:71c8bf508a54b83fd8990e05771c592944f850059ecc4651016f4f3ecc655ef8"
SOURCE_HASHES = {
    TG11 / "tg11_dataset.py": TG11_DATASET_SHA256,
    DIAGNOSTIC / "cases.json": DIAGNOSTIC_MANIFEST_SHA256,
    ORIGINAL_CONTROLS / "cases.json": "sha256:ce3a22f10abefca4623affe006331b770dad5d3788d99aa44bdad93d2f75af48",
    NEW_DATA / "cases.json": "sha256:b1a7a557a58de5adfe0af87e034ddde4737df18d917fc6536331146bff62a845",
    LAG3_CONTROLS / "cases.json": "sha256:5bc58aab84ce75d3704d08a294333010745caec382da5f059b04c9e5a5473188",
}
MARGIN_GATE = 0.025
CFO_GATE_HZ = 8_000.0
TIMING_GATE_S = 2e-6
PROBE_MS = 20
Profile = Literal["native_diverse", "baseline_early"]


@dataclass(frozen=True, slots=True)
class Component:
    kind: str
    trajectory_id: str
    cfo_hz: float | None
    frame_epoch_samples: tuple[float, ...]
    injection_start_sample: int
    injection_stop_sample: int
    supported_symbol_start: int
    supported_symbol_stop: int
    symbol_region: str
    analytic_power_over_noise_db: float | None


@dataclass(frozen=True, slots=True)
class ReceiverTruth:
    receiver: int
    components: tuple[Component, ...]
    constructed_negative: bool
    ambiguity: str

    @property
    def pilots(self) -> tuple[Component, ...]:
        return tuple(component for component in self.components if component.kind == "pilot")


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    origin: str
    split: str
    cohort: str
    rate: int
    edge: str
    channel: int
    source_counter: int
    source_end_counter: int
    session: str
    tuning_identity: str
    calibration_identity: str
    visit_index: int | None
    sequence_id: str | None
    sequence_index: int | None
    raw_path: Path
    raw_sha256: str
    receivers: tuple[ReceiverTruth, ReceiverTruth]
    activity_policy: str
    expected_active: bool | None

    @property
    def sample_count(self) -> int:
        return self.rate * 120 // 1_000

    @property
    def state_key_prefix(self) -> tuple[str, int, str, int, str, str]:
        return (self.session, self.channel, self.edge, self.rate,
                self.tuning_identity, self.calibration_identity)


@dataclass(frozen=True, slots=True)
class Observation:
    receiver: int
    probe_index: int
    probe_start_sample: int
    dwell_epoch_sample: float
    tracking_cfo_hz: float
    margin: float


@dataclass(frozen=True, slots=True)
class Pair:
    receiver: int
    first: Observation
    second: Observation


@dataclass(frozen=True, slots=True)
class Association:
    matched: bool
    receiver: int | None
    trajectory_id: str | None
    timing_errors_samples: tuple[float, float] | None
    cfo_errors_hz: tuple[float, float] | None
    support_frames: tuple[int, int] | None
    reason: str


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return "sha256:" + value.hexdigest()


def _load_tg11_module():
    path = TG11 / "tg11_dataset.py"
    if _digest(path) != TG11_DATASET_SHA256:
        raise ValueError("frozen TG11 dataset adapter changed")
    spec = importlib.util.spec_from_file_location("native_tradeoff_tg11_dataset", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load frozen TG11 dataset adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _legacy_component(component: Any) -> Component:
    return Component(
        kind=component.kind,
        trajectory_id=component.trajectory_id,
        cfo_hz=component.cfo_hz,
        frame_epoch_samples=tuple(component.frame_epoch_samples),
        injection_start_sample=component.injection_start_sample,
        injection_stop_sample=component.injection_stop_sample,
        supported_symbol_start=2,
        supported_symbol_stop=302,
        symbol_region="full",
        analytic_power_over_noise_db=None,
    )


def _legacy_case(raw: Any, *, expected_active: bool | None = None, sequence_id: str | None = None,
                 sequence_index: int | None = None) -> Case:
    receivers = tuple(
        ReceiverTruth(
            receiver=receiver,
            components=tuple(_legacy_component(item) for item in raw.injected[receiver]),
            constructed_negative=(
                raw.origin != "recorded_development"
                and not any(item.kind == "pilot" for item in raw.injected[receiver])
            ),
            ambiguity=(
                "invalid" if not any(item.kind == "pilot" for item in raw.injected[receiver])
                else "either" if sum(item.kind == "pilot" for item in raw.injected[receiver]) > 1
                else "single"
            ),
        )
        for receiver in (0, 1)
    )
    if expected_active is None and raw.origin != "recorded_development":
        expected_active = bool(any(receiver.pilots for receiver in receivers))
    activity_policy = (
        "recorded_unknown" if raw.origin == "recorded_development"
        else "required_active" if expected_active
        else "required_inactive"
    )
    return Case(
        id=raw.id, origin=raw.origin, split="development", cohort=(
            "legacy_sequence" if sequence_id else "legacy_control"
            if raw.origin != "recorded_development" else "recorded_real_prefix"
        ),
        rate=raw.rate, edge=raw.edge, channel=raw.channel,
        source_counter=raw.source_counter,
        source_end_counter=raw.source_counter + raw.sample_count,
        session=raw.session, tuning_identity=raw.tuning_identity,
        calibration_identity=raw.calibration_identity,
        visit_index=(raw.visit_index if raw.visit_index is not None else
                     sequence_index if sequence_index is not None else 0),
        sequence_id=sequence_id,
        sequence_index=sequence_index, raw_path=raw.raw_path,
        raw_sha256="sha256:" + raw.raw_sha256.removeprefix("sha256:"),
        receivers=receivers, activity_policy=activity_policy,
        expected_active=expected_active,
    )


def legacy_controls() -> tuple[Case, ...]:
    module = _load_tg11_module()
    cases = tuple(_legacy_case(case) for case in module.control_cases())
    if len(cases) != 32:
        raise ValueError("legacy control membership changed")
    return cases


def legacy_sequence_occurrences() -> tuple[Case, ...]:
    module = _load_tg11_module()
    cases = tuple(
        _legacy_case(step.case, expected_active=step.expected_active,
                     sequence_id=sequence.id, sequence_index=index)
        for sequence in module.control_sequences()
        for index, step in enumerate(sequence.steps)
    )
    if len(cases) != 10:
        raise ValueError("legacy sequence membership changed")
    return cases


def real_prefix_cases() -> tuple[Case, ...]:
    module = _load_tg11_module()
    cases = tuple(_legacy_case(case) for case in module.real_cases())
    if len(cases) != 64:
        raise ValueError("real prefix membership changed")
    for rate in (2_500_000, 5_000_000):
        selected = [case for case in cases if case.rate == rate]
        if selected != sorted(selected, key=lambda case: (case.source_counter, case.visit_index or -1)):
            raise ValueError("real prefix is not chronological within rate")
    return cases


def _diagnostic_component(raw: dict, sample_count: int) -> Component:
    region = raw.get("symbol_region", "full")
    symbol_range = raw.get("supported_symbol_range")
    if symbol_range is None:
        symbol_range = [2, 302] if region == "full" else ([2, 66] if region == "early" else [152, 216])
    power = raw.get("nominal_power_over_noise_db", raw.get("nominal_active_power_over_noise_db"))
    return Component(
        kind=raw["type"], trajectory_id=raw["trajectory_id"],
        cfo_hz=(float(raw["cfo_hz"]) if raw["type"] == "pilot" else None),
        frame_epoch_samples=tuple(
            float(item["physical_start_samples"]) for item in raw.get("frame_coordinates", ())
        ),
        injection_start_sample=0, injection_stop_sample=sample_count,
        supported_symbol_start=int(symbol_range[0]), supported_symbol_stop=int(symbol_range[1]),
        symbol_region=region,
        analytic_power_over_noise_db=(float(power) if power is not None else None),
    )


def diagnostic_development_cases() -> tuple[Case, ...]:
    path = DIAGNOSTIC / "cases.json"
    if _digest(path) != DIAGNOSTIC_MANIFEST_SHA256:
        raise ValueError("TG11 diagnostic manifest changed")
    payload = json.loads(path.read_text())
    if payload["validation_iq_opened"] is not False:
        raise ValueError("diagnostic validation state changed")
    cases = []
    for raw in payload["cases"]:
        if raw["split"] != "development":
            continue
        if not raw["raw_npy"]["materialized"] or not raw["raw_npy"]["sha256"]:
            raise ValueError("development diagnostic IQ is not materialized")
        receivers = tuple(
            ReceiverTruth(
                receiver=receiver,
                components=tuple(
                    _diagnostic_component(item, raw["rate_hz"] * 120 // 1_000)
                    for item in raw["receivers"][receiver]["components"]
                ),
                constructed_negative=bool(raw["receivers"][receiver]["constructed_negative"]),
                ambiguity=raw["receivers"][receiver]["ambiguity"],
            )
            for receiver in (0, 1)
        )
        cases.append(Case(
            id=raw["case_id"], origin=raw["origin"], split=raw["split"],
            cohort=raw["cohort"], rate=raw["rate_hz"], edge=raw["edge"],
            channel=raw["channel"], source_counter=raw["source_start_counter"],
            source_end_counter=raw["source_end_counter_exclusive"],
            session=raw["session_id"], tuning_identity=raw["tuning_identity"],
            calibration_identity="tg11diag-constructed-fixed-calibration",
            visit_index=(raw["sequence_index"] if raw["sequence_index"] is not None else 0),
            sequence_id=raw["sequence_id"],
            sequence_index=raw["sequence_index"],
            raw_path=(DIAGNOSTIC / raw["raw_npy"]["path"]).resolve(),
            raw_sha256=raw["raw_npy"]["sha256"], receivers=receivers,
            activity_policy=(
                "required_inactive" if all(receiver.constructed_negative for receiver in receivers)
                else "regional_report_only" if raw["cohort"].startswith("symbol-region")
                else "presence_report_only"
            ),
            expected_active=(False if all(receiver.constructed_negative for receiver in receivers) else None),
        ))
    if len(cases) != 26:
        raise ValueError("diagnostic development membership changed")
    return tuple(cases)


def all_cases() -> tuple[Case, ...]:
    cases = legacy_controls() + legacy_sequence_occurrences() + diagnostic_development_cases() + real_prefix_cases()
    if len(cases) != 132 or len({case.id for case in cases}) != 132:
        raise ValueError("native tradeoff corpus membership is not unique")
    return cases


def membership_sha256() -> str:
    payload = [{
        "id": case.id, "origin": case.origin, "split": case.split, "cohort": case.cohort,
        "rate": case.rate, "edge": case.edge, "channel": case.channel,
        "source_counter": case.source_counter, "session": case.session,
        "calibration_identity": case.calibration_identity,
        "sequence_id": case.sequence_id, "sequence_index": case.sequence_index,
        "raw_sha256": case.raw_sha256,
    } for case in all_cases()]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def source_hashes() -> dict[str, str]:
    """Return the complete metadata/source inventory used to select cases."""
    sources = {str(path.resolve()): expected for path, expected in SOURCE_HASHES.items()}
    for path, expected in sources.items():
        if _digest(Path(path)) != expected:
            raise ValueError(f"source hash mismatch: {path}")
    return dict(sorted(sources.items()))


def load_iq(case: Case) -> np.ndarray:
    if case.split != "development":
        raise ValueError("only development IQ is authorized")
    if _digest(case.raw_path) != case.raw_sha256:
        raise ValueError(f"IQ hash mismatch: {case.id}")
    values = np.load(case.raw_path, mmap_mode="r", allow_pickle=False)
    if values.dtype != np.dtype("<i2") or values.shape != (case.sample_count, 2, 2):
        raise ValueError(f"IQ geometry mismatch: {case.id}")
    values.setflags(write=False)
    return values


def _get(value: Any, name: str) -> Any:
    return value[name] if isinstance(value, dict) else getattr(value, name)


def _maybe_get(value: Any, name: str, default: Any) -> Any:
    try:
        return _get(value, name)
    except (AttributeError, KeyError, TypeError):
        return default


def _dwell_epoch(observation: Any) -> float:
    value = _maybe_get(observation, "dwell_epoch_sample", None)
    if value is not None:
        return float(value)
    return float(_get(observation, "probe_start_sample")) + float(_get(observation, "local_epoch_sample"))


def _unwrap_pair(value: Any) -> Any | None:
    if value is None:
        return None
    active = _maybe_get(value, "active", None)
    if active is not None:
        return _get(value, "pair") if bool(active) else None
    return value


def map_source_coordinate(case: Case, observation: Any) -> tuple[int, float]:
    epoch = _dwell_epoch(observation)
    whole = math.floor(epoch)
    return case.source_counter + whole, epoch - whole


def reference_positive_pair_inventory(analysis: Any, case: Case) -> tuple[Pair, ...]:
    passing: dict[int, list[Observation]] = {0: [], 1: []}
    for probe in _get(analysis, "probes"):
        receiver = int(_get(probe, "receiver_id"))
        probe_index = int(_get(probe, "probe_index"))
        probe_start = int(_get(probe, "probe_start_ms") * case.rate // 1_000)
        for candidate in _get(probe, "candidates"):
            margin = float(_get(candidate, "margin"))
            if not bool(_get(candidate, "passed_margin_gate")) or margin < MARGIN_GATE:
                continue
            passing[receiver].append(Observation(
                receiver, probe_index, probe_start,
                probe_start + float(_get(candidate, "epoch_sample")),
                float(_get(candidate, "tracking_cfo_hz")), margin,
            ))
    pairs = []
    minimum_gap = case.rate * PROBE_MS // 1_000
    for receiver, observations in passing.items():
        for index, first in enumerate(observations):
            for second in observations[index + 1:]:
                if second.probe_start_sample - first.probe_start_sample < minimum_gap:
                    continue
                if abs(second.tracking_cfo_hz - first.tracking_cfo_hz) > CFO_GATE_HZ:
                    continue
                pairs.append(Pair(receiver, first, second))
    return tuple(pairs)


def _observation(value: Any) -> Observation:
    return Observation(
        receiver=int(_get(value, "receiver")), probe_index=int(_get(value, "probe_index")),
        probe_start_sample=int(_get(value, "probe_start_sample")),
        dwell_epoch_sample=_dwell_epoch(value),
        tracking_cfo_hz=float(_get(value, "tracking_cfo_hz")),
        margin=float(_get(value, "margin")),
    )


def _normalized_pair(value: Any) -> Pair | None:
    pair = _unwrap_pair(value)
    if pair is None:
        return None
    first, second = _observation(_get(pair, "first")), _observation(_get(pair, "second"))
    return Pair(int(_get(pair, "receiver")), first, second)


def _region_for_frame(profile: Profile, frame: int, frame_start: float,
                      probe_stop: int, rate: int) -> tuple[int, int]:
    if profile == "baseline_early" or frame % 2 == 0:
        return 2, 66
    late = (152, 216)
    late_stop = frame_start + round(late[1] * rate * 4.4e-6)
    return (2, 66) if late_stop >= probe_stop else late


def _support_count(observation: Observation, component: Component, case: Case,
                   profile: Profile) -> int:
    probe_start = observation.probe_start_sample
    probe_stop = probe_start + case.rate * PROBE_MS // 1_000
    period = case.rate / 750.0
    tolerance = case.rate * TIMING_GATE_S
    count = 0
    for frame in range(16):
        predicted = observation.dwell_epoch_sample + round(frame * period)
        actual = min(component.frame_epoch_samples, key=lambda item: abs(item - predicted), default=None)
        if actual is None or abs(actual - predicted) > tolerance:
            continue
        first_symbol, stop_symbol = _region_for_frame(profile, frame, actual, probe_stop, case.rate)
        if component.supported_symbol_start > first_symbol or component.supported_symbol_stop < stop_symbol:
            continue
        begin = actual + round(first_symbol * case.rate * 4.4e-6)
        stop = actual + round(stop_symbol * case.rate * 4.4e-6)
        if (begin >= probe_start and stop <= probe_stop
                and begin >= component.injection_start_sample
                and stop <= component.injection_stop_sample):
            count += 1
    return count


def _pair_contract(pair: Pair, case: Case) -> str | None:
    if pair.receiver not in (0, 1) or pair.first.receiver != pair.receiver or pair.second.receiver != pair.receiver:
        return "pair receiver mismatch"
    if pair.second.probe_start_sample - pair.first.probe_start_sample < case.rate * PROBE_MS // 1_000:
        return "pair windows overlap"
    if abs(pair.second.tracking_cfo_hz - pair.first.tracking_cfo_hz) > CFO_GATE_HZ:
        return "pair CFOs are inconsistent"
    if pair.first.margin < MARGIN_GATE or pair.second.margin < MARGIN_GATE:
        return "pair margin is below threshold"
    return None


def associate_pair_to_truth(result_or_pair: Any, case: Case, receiver: int,
                            *, profile: Profile) -> Association:
    pair = _normalized_pair(result_or_pair)
    if pair is None:
        return Association(False, receiver, None, None, None, None, "inactive result")
    error = _pair_contract(pair, case)
    if error is not None:
        return Association(False, pair.receiver, None, None, None, None, error)
    if pair.receiver != receiver:
        return Association(False, pair.receiver, None, None, None, None, "pair selected another receiver")
    pilots = case.receivers[receiver].pilots
    if not pilots:
        return Association(False, receiver, None, None, None, None, "no injected pilot trajectory")
    period = case.rate / 750.0
    nearest: tuple[float, Association] | None = None
    for pilot in pilots:
        timing = tuple(abs((observation.dwell_epoch_sample - min(
            pilot.frame_epoch_samples,
            key=lambda epoch: abs((observation.dwell_epoch_sample - epoch + period / 2) % period - period / 2),
        ) + period / 2) % period - period / 2) for observation in (pair.first, pair.second))
        cfo = tuple(abs(observation.tracking_cfo_hz - float(pilot.cfo_hz))
                    for observation in (pair.first, pair.second))
        support = tuple(_support_count(observation, pilot, case, profile)
                        for observation in (pair.first, pair.second))
        if max(timing) <= case.rate * TIMING_GATE_S and max(cfo) <= CFO_GATE_HZ and min(support) >= 2:
            return Association(True, receiver, pilot.trajectory_id, timing, cfo, support,
                               "both fresh observations associate to one supported injected trajectory")
        distance = max(timing) / (case.rate * TIMING_GATE_S) + max(cfo) / CFO_GATE_HZ
        if min(support) < 2:
            distance += 2 - min(support)
        candidate = Association(
            False, receiver, pilot.trajectory_id, timing, cfo, support,
            "pair misses injected trajectory tolerance or detector-specific symbol support",
        )
        if nearest is None or distance < nearest[0]:
            nearest = distance, candidate
    assert nearest is not None
    return nearest[1]


def associate_pair_to_reference(result_or_pair: Any, inventory: tuple[Pair, ...],
                                case: Case, receiver: int) -> Association:
    pair = _normalized_pair(result_or_pair)
    if pair is None:
        return Association(False, receiver, None, None, None, None, "inactive result")
    error = _pair_contract(pair, case)
    if error is not None:
        return Association(False, pair.receiver, None, None, None, None, error)
    period = case.rate / 750.0
    nearest: tuple[float, Association] | None = None
    for reference in inventory:
        if pair.receiver != receiver or reference.receiver != receiver:
            continue
        timing = tuple(abs((actual.dwell_epoch_sample - expected.dwell_epoch_sample + period / 2)
                           % period - period / 2)
                       for actual, expected in zip((pair.first, pair.second),
                                                   (reference.first, reference.second), strict=True))
        cfo = tuple(abs(actual.tracking_cfo_hz - expected.tracking_cfo_hz)
                    for actual, expected in zip((pair.first, pair.second),
                                                (reference.first, reference.second), strict=True))
        if max(timing) <= case.rate * TIMING_GATE_S and max(cfo) <= CFO_GATE_HZ:
            return Association(True, receiver, None, timing, cfo, None,
                               "candidate pair associates to baseline inventory")
        distance = max(timing) / (case.rate * TIMING_GATE_S) + max(cfo) / CFO_GATE_HZ
        candidate = Association(
            False, receiver, None, timing, cfo, None,
            "candidate pair misses baseline inventory tolerance",
        )
        if nearest is None or distance < nearest[0]:
            nearest = distance, candidate
    if nearest is not None:
        return nearest[1]
    return Association(False, pair.receiver, None, None, None, None,
                       "baseline inventory has no pair for receiver")


def _profile_has_truth_support(case: Case, receiver: int, profile: Profile) -> bool:
    pilots = case.receivers[receiver].pilots
    if not pilots:
        return False
    for pilot in pilots:
        if profile == "baseline_early" and pilot.supported_symbol_start <= 2 and pilot.supported_symbol_stop >= 66:
            return True
        if profile == "native_diverse" and (
            (pilot.supported_symbol_start <= 2 and pilot.supported_symbol_stop >= 66)
            or (pilot.supported_symbol_start <= 152 and pilot.supported_symbol_stop >= 216)
        ):
            return True
    return False


def assess_receiver(candidate: Any, reference_inventory: tuple[Pair, ...], case: Case,
                    receiver: int, *, profile: Profile = "native_diverse") -> dict[str, Any]:
    pair = _normalized_pair(candidate)
    candidate_active = pair is not None and pair.receiver == receiver
    references = tuple(item for item in reference_inventory if item.receiver == receiver)
    reference_active = bool(references)
    reference_association = associate_pair_to_reference(candidate, references, case, receiver)
    truth_association = associate_pair_to_truth(candidate, case, receiver, profile=profile)
    truth = case.receivers[receiver]
    truth_present = bool(truth.pilots)
    profile_support = _profile_has_truth_support(case, receiver, profile)
    receiver_policy = (
        "required_inactive"
        if case.cohort != "recorded_real_prefix" and truth.constructed_negative
        else case.activity_policy
    )
    if candidate_active and reference_active:
        reference_outcome = "retained_associated" if reference_association.matched else "active_unassociated_reference"
    elif candidate_active:
        reference_outcome = "reference_extra"
    elif reference_active:
        reference_outcome = "reference_miss"
    else:
        reference_outcome = "both_inactive"
    if candidate_active and truth_association.matched:
        physical_outcome = "truth_associated_positive"
    elif candidate_active and truth.constructed_negative:
        physical_outcome = "constructed_negative_positive"
    elif candidate_active and case.activity_policy == "recorded_unknown":
        physical_outcome = "recorded_unknown_positive"
    elif candidate_active:
        physical_outcome = "truth_unassociated_positive"
    elif truth_present and not profile_support:
        physical_outcome = "regional_not_scored"
    elif truth_present and case.activity_policy in {"presence_report_only", "regional_report_only"}:
        physical_outcome = "present_inactive_report_only"
    elif truth_present:
        physical_outcome = "constructed_miss"
    elif truth.constructed_negative:
        physical_outcome = "constructed_true_negative"
    else:
        physical_outcome = "recorded_unknown_inactive"
    policy_passed: bool | None
    if receiver_policy == "required_active":
        policy_passed = candidate_active and truth_association.matched
    elif receiver_policy == "required_inactive":
        policy_passed = not candidate_active
    else:
        policy_passed = None
    return {
        "receiver": receiver,
        "profile": profile,
        "candidate_active": candidate_active,
        "reference_active": reference_active,
        "reference_pair_count": len(references),
        "reference_outcome": reference_outcome,
        "reference_association": asdict(reference_association),
        "physical_pilot_present": truth_present,
        "detector_profile_has_injected_symbol_support": profile_support,
        "truth_activity_policy": receiver_policy,
        "physical_outcome": physical_outcome,
        "truth_association": asdict(truth_association),
        "activity_policy_passed": policy_passed,
    }
