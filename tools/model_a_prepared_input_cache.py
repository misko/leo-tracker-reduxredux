"""Exact public-contract training cache, built once through qualified ports."""

import fcntl
import time
from contextlib import contextmanager
from dataclasses import asdict, fields, is_dataclass, replace
from pathlib import Path

import ds21_model_a_timing_runtime_v2 as transport
import numpy as np

from leo.application.channel_group_holdout import GroupedProbeHoldout
from leo.application.regional_position_inputs import PreparedPositionWindows
from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior
from leo.contracts.scanner_tracking import TrackingCandidate, TrackingInput, TrackingProbe
from leo.scanner.persistent_hop import PersistentHopUtcTimingAuthorityV1

GATE = Path(__file__).resolve().parents[1] / (
    "reports/2026_10_14_ds21_ds22_next_round/local/model-a-preparation-admission.lock"
)


@contextmanager
def admission(*, seconds=120):
    """One expensive source qualification/preparation at a time; fits never lock."""
    GATE.parent.mkdir(parents=True, exist_ok=True)
    begun = time.monotonic()
    with GATE.open("a") as stream:
        while True:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - begun >= seconds:
                    raise TimeoutError("Preparation admission deadline exhausted") from None
                time.sleep(0.05)
        try:
            yield time.monotonic() - begun
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def tracking_value(source):
    value = asdict(source)
    value["timing"] = source.timing.model_dump(mode="json") if source.timing else None
    return value


def tracking_contract(value):
    value = dict(value)
    value["timing"] = (
        PersistentHopUtcTimingAuthorityV1.model_validate(value["timing"])
        if value["timing"] is not None
        else None
    )
    value["probes"] = tuple(
        TrackingProbe(
            **dict(row, candidates=tuple(TrackingCandidate(**c) for c in row["candidates"]))
        )
        for row in value["probes"]
    )
    return TrackingInput(**value)


def write_case(directory, frozen, case):
    directory = Path(directory)
    split = case["split"]
    arrays = {"nodes": case["nodes"]}
    arrays.update(
        {
            f"bank_{k}": getattr(case["bank"], k)
            for k in ("numbers", "nodes_s", "position_km", "velocity_km_s")
        }
    )
    prepared = {}
    for view, item in case["prepared"].items():
        value = asdict(item)
        obs = value.pop("observations")
        prepared[view] = dict(value, window_ids=obs.pop("window_ids"))
        arrays.update({f"{view}_{k}": v for k, v in obs.items()})
    with (directory / "training-cache.npz").open("xb") as stream:
        np.savez(stream, **arrays)
    value = dict(
        protocol=transport.binding(directory / "protocol.json"),
        training=tracking_value(split.training),
        partition=dict(
            seed=split.seed,
            block_seconds=split.block_seconds,
            held_blocks=split.held_blocks,
            assignments=split.assignments,
        ),
        prepared=prepared,
        prior=asdict(case["prior"]),
        arrays=transport.binding(directory / "training-cache.npz"),
        label=frozen["label"],
        reference_usage="none",
        held_observations="not serialized",
    )
    transport.immutable(directory / "training-cache.json", value)
    return value


def validate(directory, frozen):
    directory = Path(directory)
    value = transport.read(directory / "training-cache.json")
    identity = dict(
        protocol=transport.binding(directory / "protocol.json"),
        optimizer_calls=0,
        predictor_calls=0,
        objective_calls=0,
    )
    end = transport.read(directory / "training-cache-termination.json")
    if (
        transport.read(directory / "training-cache-launch.json") != identity
        or end.get("state") != "complete"
        or any(end.get(k) != v for k, v in identity.items())
        or end["cache"] != transport.binding(directory / "training-cache.json")
        or end["arrays"] != transport.binding(directory / "training-cache.npz")
        or value["arrays"] != end["arrays"]
        or value["protocol"] != identity["protocol"]
        or value["label"] != frozen["label"]
        or value["reference_usage"] != "none"
        or value["held_observations"] != "not serialized"
        or end["preparation_seconds"] > 45
    ):
        raise ValueError("Qualified exact training cache binding/identity changed")
    return value


def ensure(directory, frozen):
    directory = Path(directory)
    with admission() as waited:
        if (directory / "training-cache-launch.json").exists():
            return validate(directory, frozen)
        identity = dict(
            protocol=transport.binding(directory / "protocol.json"),
            optimizer_calls=0,
            predictor_calls=0,
            objective_calls=0,
        )
        transport.immutable(directory / "training-cache-launch.json", identity)
        status, begun = (
            dict(**identity, state="failed", admission_wait_seconds=waited),
            time.monotonic(),
        )
        try:
            with transport.original.discovery.slice_bound(45):
                case = transport.prepare_case(frozen)
                value = write_case(directory, frozen, case)
            status.update(
                state="complete",
                preparation_seconds=time.monotonic() - begun,
                cache=transport.binding(directory / "training-cache.json"),
                arrays=value["arrays"],
            )
        except BaseException as error:
            status.update(error_type=type(error).__name__, reason=str(error))
            raise
        finally:
            transport.immutable(directory / "training-cache-termination.json", status)
    return validate(directory, frozen)


def load(directory, frozen):
    value = validate(directory, frozen)
    source = tracking_contract(value["training"])
    empty = replace(source, probes=())
    partition = value["partition"]
    split = GroupedProbeHoldout(
        source,
        empty,
        empty,
        tuple(partition["held_blocks"]),
        tuple(tuple(a) for a in partition["assignments"]),
        partition["seed"],
        partition["block_seconds"],
    )
    with np.load(value["arrays"]["path"], allow_pickle=False) as arrays:
        bank = PositionOrbitBank(
            *(arrays[f"bank_{k}"] for k in ("numbers", "nodes_s", "position_km", "velocity_km_s"))
        )
        prepared = {}
        for view, item in value["prepared"].items():
            item = dict(item)
            observations = PositionObservations(
                tuple(item.pop("window_ids")),
                *(
                    arrays[f"{view}_{k}"]
                    for k in ("times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin")
                ),
            )
            item["candidate_ids"] = tuple(item["candidate_ids"])
            item["bootstrap_tracks"] = tuple(tuple(t) for t in item["bootstrap_tracks"])
            prepared[view] = PreparedPositionWindows(observations=observations, **item)
        case = dict(
            source=empty,
            split=split,
            bank=bank,
            prepared=prepared,
            nodes=arrays["nodes"].copy(),
            prior=RegionalPrior(**value["prior"]),
        )
    transport.original.discovery.validate_preparation(
        case, transport.original.read_bound(frozen["case_protocol"])
    )
    if (
        bank.numbers.tolist() != frozen["original"]["inputs"]["candidate_numbers"]
        or {v: p.evidence_sha256 for v, p in prepared.items()}
        != frozen["original"]["inputs"]["prepared"]
    ):
        raise ValueError("Cached selected bank/evidence differs")
    return case


def exact_equal(a, b):
    """Exact arrays, contracts, objective gradients and posterior fields."""
    if isinstance(a, np.ndarray):
        if not isinstance(b, np.ndarray) or a.dtype != b.dtype or not np.array_equal(a, b):
            raise ValueError("Prepared cache array/objective equivalence differs")
    elif is_dataclass(a):
        if type(a) is not type(b):
            raise ValueError("Prepared cache public contract type differs")
        for field in fields(a):
            exact_equal(getattr(a, field.name), getattr(b, field.name))
    elif isinstance(a, dict):
        if set(a) != set(b):
            raise ValueError("Prepared cache metadata keys differ")
        for key in a:
            exact_equal(a[key], b[key])
    elif isinstance(a, (list, tuple)):
        if len(a) != len(b):
            raise ValueError("Prepared cache sequence differs")
        for left, right in zip(a, b, strict=True):
            exact_equal(left, right)
    elif a != b:
        raise ValueError("Prepared cache public field/objective equivalence differs")


def qualify_equivalence(directory, frozen):
    """Separate counted numerical audit; cache building itself remains zero-fit."""
    directory = Path(directory)
    identity = dict(
        protocol=transport.binding(directory / "protocol.json"),
        cache=transport.binding(directory / "training-cache.json"),
        arrays=transport.binding(directory / "training-cache.npz"),
    )
    launch, end = (
        directory / "cache-equivalence-launch.json",
        directory / "cache-equivalence-termination.json",
    )
    if launch.exists():
        value = transport.read(directory / "cache-equivalence.json")
        if transport.read(launch) != identity or transport.read(end) != dict(
            **identity,
            state="complete",
            result=transport.binding(directory / "cache-equivalence.json"),
        ):
            raise ValueError("Cache equivalence failed/orphan/binding changed")
        return value
    transport.immutable(launch, identity)
    status, begun = dict(**identity, state="failed"), time.monotonic()
    calls = 0
    try:
        with admission() as waited, transport.original.discovery.slice_bound(45):
            fresh = transport.prepare_case(frozen)
        restored = load(directory, frozen)
        for key in ("prepared", "bank", "prior", "nodes"):
            exact_equal(fresh[key], restored[key])
        exact_equal(fresh["split"].training, restored["split"].training)
        for key in ("seed", "block_seconds", "held_blocks", "assignments"):
            exact_equal(getattr(fresh["split"], key), getattr(restored["split"], key))
        before, after = (
            transport.original.models_for(fresh),
            transport.original.models_for(restored),
        )
        states = {}
        for name in ("B", "C"):
            for view in ("all", "low", "high"):
                a, b = before[name][view], after[name][view]
                vector = np.zeros(a.size)
                vector[:2] = frozen["original"]["inputs"]["proposals"][0]["point_km"]
                vector[2:7] = [-80000, 0, -54000, 0, -500]
                nuisance = np.array(a.initial_nuisance, copy=True)
                left = a.evaluate_joint(vector, nuisance)
                calls += 1
                right = b.evaluate_joint(vector, nuisance)
                calls += 1
                exact_equal(left, right)
                states[f"{name}-{view}"] = dict(vector=vector, nuisance=nuisance)
        value = dict(
            **identity,
            objective_calls=calls,
            predictor_calls=calls,
            optimizer_calls=0,
            exact=True,
            states=states,
            preparation_admission_wait_seconds=waited,
            elapsed_seconds=time.monotonic() - begun,
            reference_usage="none",
            held_usage="none",
            predictor_count_basis=(
                "One orbit prediction per B base or SparseNativeJointObjective evaluation"
            ),
        )
        transport.immutable(directory / "cache-equivalence.json", value)
        status = dict(
            **identity,
            state="complete",
            result=transport.binding(directory / "cache-equivalence.json"),
        )
    except BaseException as error:
        status.update(error_type=type(error).__name__, reason=str(error), objective_calls=calls)
        raise
    finally:
        transport.immutable(end, status)
    return value


def equivalence_result(directory):
    directory = Path(directory)
    value = transport.read(directory / "cache-equivalence.json")
    identity = dict(
        protocol=transport.binding(directory / "protocol.json"),
        cache=transport.binding(directory / "training-cache.json"),
        arrays=transport.binding(directory / "training-cache.npz"),
    )
    if (
        transport.read(directory / "cache-equivalence-launch.json") != identity
        or transport.read(directory / "cache-equivalence-termination.json")
        != dict(
            **identity,
            state="complete",
            result=transport.binding(directory / "cache-equivalence.json"),
        )
        or any(value.get(k) != v for k, v in identity.items())
        or value["objective_calls"] != 12
        or value["predictor_calls"] != 12
        or value["optimizer_calls"] != 0
        or value["exact"] is not True
        or value["reference_usage"] != "none"
        or value["held_usage"] != "none"
    ):
        raise ValueError("Successful bound cache numerical equivalence required")
    return value
