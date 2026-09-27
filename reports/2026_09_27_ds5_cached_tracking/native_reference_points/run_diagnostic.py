"""Frozen, coordinate-for-coordinate native reference-point diagnostic.

This is deliberately not a detector benchmark.  It selects coordinates only
from the already-frozen full-application receipt, then evaluates the current
Python GLRT-64 statistic and the frozen TG11 guided statistic once at each
coordinate.  IQ is opened only by ``run()`` after an explicit source freeze.
"""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import asdict, dataclass, fields, is_dataclass
from enum import Enum
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import sys
import time
from typing import Any


HERE = Path(__file__).resolve().parent
REPORT = HERE.parent
ROOT = HERE.parents[2]
TG11 = REPORT / "tg11"
TRADEOFF = REPORT / "native_tradeoff"
CANDIDATES = REPORT / "native_candidates"
PRIOR_LOCK = CANDIDATES / "source_lock.json"
PRIOR_RECEIPT = CANDIDATES / "results.real.json"
EXPECTED_PRIOR_RECEIPT_SHA256 = "335a4bb946ede0c350511920641f5ee7b1ebe56e7768200f83ff3402f45aa1cb"
SOURCE_LOCK = HERE / "source_lock.json"
RESULT = HERE / "results.json"

sys.path[:0] = [str(ROOT / "src"), str(TG11), str(TRADEOFF)]

import numpy as np  # noqa: E402
import leo  # noqa: E402
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score  # noqa: E402
from native_engine import NativeTG11  # noqa: E402

if Path(leo.__file__).resolve() != ROOT / "src/leo/__init__.py":
    raise RuntimeError("reference-point diagnostic must use this checkout")


def _load_dataset() -> Any:
    path = TRADEOFF / "tradeoff_dataset.py"
    spec = importlib.util.spec_from_file_location("native_reference_points_dataset", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen tradeoff dataset")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dataset = _load_dataset()

MARGIN_GATE = 0.025
CFO_IDENTITY_HZ = 8_000.0
TIMING_IDENTITY_S = 2e-6
SCORING_RANGE_HZ = 400_000.0
RESIDUAL_SUPPORT_HZ = 0.5 / 4.4e-6
SCORE_REPRODUCTION_TOLERANCE = 1e-12
CFO_REPRODUCTION_TOLERANCE_HZ = 1e-6
TIMEOUT_SECONDS = 120
THREAD_ENV = (
    "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
)


@dataclass(frozen=True, slots=True)
class ResolvedCoordinate:
    pair_inventory_index: int
    pair_role: str
    member: str
    receiver: int
    probe_index: int
    probe_start_sample: int
    local_epoch_sample: int
    dwell_epoch_sample: int
    candidate_list_index: int
    candidate_rank: int
    equivalent_candidate_ranks: tuple[int, ...]
    acquired_cfo_hz: float
    residual_cfo_hz: float
    tracking_cfo_hz: float
    exact_score: float
    control_score: float
    reference_margin: float


def digest(path: str | Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: jsonable(getattr(value, field.name)) for field in fields(value)}
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return jsonable(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite value cannot enter a scientific receipt")
    return value


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        jsonable(value), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def load_prior_receipt() -> dict[str, Any]:
    if digest(PRIOR_RECEIPT) != EXPECTED_PRIOR_RECEIPT_SHA256:
        raise ValueError("native-candidate real receipt differs from the governing design")
    payload = json.loads(PRIOR_RECEIPT.read_text())
    lock = json.loads(PRIOR_LOCK.read_text())
    if (
        payload.get("status") != "complete"
        or payload.get("complete") is not True
        or payload.get("stage") != "real"
        or payload.get("source_lock_stable") is not True
        or payload.get("source_lock") != lock
        or payload.get("source_lock_sha256") != digest(PRIOR_LOCK)
        or len(payload.get("rows", ())) != 64
        or len(lock.get("files", {})) != 74
    ):
        raise ValueError("frozen native-candidate real receipt is not complete and stable")
    for name, expected in lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"prior frozen source changed: {name}")
    return payload


def selected_receiver_rows(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    """Select all K2 losses and the first two matched rows per rate in receipt order."""
    selected: list[dict[str, Any]] = []
    anchors = {2_500_000: 0, 5_000_000: 0}
    for row_index, row in enumerate(receipt["rows"]):
        assessments = row["native_assessments"]["native_k2_blind"]
        by_receiver = {int(item["receiver"]): item for item in assessments}
        for receiver in (0, 1):
            item = by_receiver[receiver]
            category = None
            if item["lost_reference"]:
                category = "k2_blind_lost_reference"
            elif item["matched_reference"] and anchors[int(row["rate_hz"])] < 2:
                category = "matched_anchor"
                anchors[int(row["rate_hz"])] += 1
            if category is not None:
                selected.append({
                    "receipt_row_index": row_index,
                    "case_id": row["case_id"],
                    "rate_hz": int(row["rate_hz"]),
                    "edge": row["edge"],
                    "receiver": receiver,
                    "category": category,
                })
    losses = [item for item in selected if item["category"] == "k2_blind_lost_reference"]
    if len(losses) != 12 or anchors != {2_500_000: 2, 5_000_000: 2}:
        raise ValueError("expected exactly 12 K2 losses and two matched anchors per rate")
    return selected


def _same_float(left: Any, right: Any, *, absolute: float = 1e-9) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=absolute)


def resolve_observation(row: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    rate = int(row["rate_hz"])
    receiver = int(observation["receiver"])
    expected_start = int(observation["probe_start_sample"])
    local = float(observation["dwell_epoch_sample"]) - expected_start
    if not local.is_integer():
        raise ValueError("full-application inventory must contain integer epochs")
    candidates: list[tuple[int, dict[str, Any]]] = []
    for probe in row["outputs"]["application"]["probes"]:
        start = int(probe["probe_start_ms"]) * rate // 1_000
        if (int(probe["receiver_id"]) != receiver
                or int(probe["probe_index"]) != int(observation["probe_index"])
                or start != expected_start):
            continue
        for list_index, candidate in enumerate(probe["candidates"]):
            if (
                int(candidate["epoch_sample"]) == int(local)
                and _same_float(candidate["tracking_cfo_hz"], observation["tracking_cfo_hz"])
                and _same_float(candidate["margin"], observation["margin"])
            ):
                candidates.append((list_index, candidate))
    if not candidates:
        raise ValueError("pair observation does not resolve to a full-application candidate")
    signatures = {
        (
            float(item["acquired_cfo_hz"]), float(item["residual_cfo_hz"]),
            float(item["tracking_cfo_hz"]), float(item["exact_score"]),
            float(item["control_score"]), float(item["margin"]),
        )
        for _, item in candidates
    }
    if len(signatures) != 1:
        raise ValueError("pair observation ambiguously resolves to scientifically different candidates")
    candidates.sort(key=lambda item: (int(item[1]["candidate_rank"]), item[0]))
    list_index, chosen = candidates[0]
    return {
        "candidate_list_index": list_index,
        "candidate_rank": int(chosen["candidate_rank"]),
        "equivalent_candidate_ranks": [int(item[1]["candidate_rank"]) for item in candidates],
        "local_epoch_sample": int(local),
        "acquired_cfo_hz": float(chosen["acquired_cfo_hz"]),
        "residual_cfo_hz": float(chosen["residual_cfo_hz"]),
        "tracking_cfo_hz": float(chosen["tracking_cfo_hz"]),
    }


def resolved_pair(row: dict[str, Any], pair_index: int, role: str) -> list[dict[str, Any]]:
    pair = row["application_pair_inventory"][pair_index]
    rebuilt = _resolved_inventory(row)
    if len(rebuilt) != len(row["application_pair_inventory"]):
        raise ValueError("rebuilt application pair inventory has different length")
    output = []
    for member in ("first", "second"):
        observation = pair[member]
        resolved = rebuilt[pair_index][member]
        output.append(jsonable(ResolvedCoordinate(
            pair_inventory_index=pair_index,
            pair_role=role,
            member=member,
            receiver=int(pair["receiver"]),
            probe_index=int(observation["probe_index"]),
            probe_start_sample=int(observation["probe_start_sample"]),
            local_epoch_sample=resolved["local_epoch_sample"],
            dwell_epoch_sample=int(observation["dwell_epoch_sample"]),
            candidate_list_index=resolved["candidate_list_index"],
            candidate_rank=min(resolved["equivalent_candidate_ranks"]),
            equivalent_candidate_ranks=tuple(resolved["equivalent_candidate_ranks"]),
            acquired_cfo_hz=resolved["acquired_cfo_hz"],
            residual_cfo_hz=resolved["residual_cfo_hz"],
            tracking_cfo_hz=resolved["tracking_cfo_hz"],
            exact_score=resolved["exact_score"],
            control_score=resolved["control_score"],
            reference_margin=float(observation["margin"]),
        )))
    return output


def _resolved_inventory(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Rebuild the frozen adapter's ordered pair inventory with candidate identity.

    The published simplified inventory intentionally omits candidate rank and
    acquired CFO.  Replaying its deterministic enumeration is the only sound
    way to distinguish hypotheses that serialize to the same simplified
    observation but arose from different acquisition seeds.
    """
    rate = int(row["rate_hz"])
    passing: dict[int, list[dict[str, Any]]] = {0: [], 1: []}
    for probe in row["outputs"]["application"]["probes"]:
        receiver = int(probe["receiver_id"])
        probe_index = int(probe["probe_index"])
        probe_start = int(probe["probe_start_ms"]) * rate // 1_000
        for list_index, candidate in enumerate(probe["candidates"]):
            margin = float(candidate["margin"])
            if not bool(candidate["passed_margin_gate"]) or margin < MARGIN_GATE:
                continue
            signature = (
                int(candidate["epoch_sample"]), float(candidate["acquired_cfo_hz"]),
                float(candidate["residual_cfo_hz"]), float(candidate["tracking_cfo_hz"]),
                float(candidate["exact_score"]), float(candidate["control_score"]), margin,
            )
            equivalent_ranks = sorted(
                int(other["candidate_rank"])
                for other in probe["candidates"]
                if (
                    int(other["epoch_sample"]), float(other["acquired_cfo_hz"]),
                    float(other["residual_cfo_hz"]), float(other["tracking_cfo_hz"]),
                    float(other["exact_score"]), float(other["control_score"]),
                    float(other["margin"]),
                ) == signature
            )
            passing[receiver].append({
                "receiver": receiver,
                "probe_index": probe_index,
                "probe_start_sample": probe_start,
                "dwell_epoch_sample": probe_start + int(candidate["epoch_sample"]),
                "tracking_cfo_hz": float(candidate["tracking_cfo_hz"]),
                "margin": margin,
                "candidate_list_index": list_index,
                "candidate_rank": int(candidate["candidate_rank"]),
                "equivalent_candidate_ranks": equivalent_ranks,
                "local_epoch_sample": int(candidate["epoch_sample"]),
                "acquired_cfo_hz": float(candidate["acquired_cfo_hz"]),
                "residual_cfo_hz": float(candidate["residual_cfo_hz"]),
                "exact_score": float(candidate["exact_score"]),
                "control_score": float(candidate["control_score"]),
            })
    rebuilt = []
    minimum_gap = rate // 50
    for receiver in (0, 1):
        observations = passing[receiver]
        for index, first in enumerate(observations):
            for second in observations[index + 1:]:
                if second["probe_start_sample"] - first["probe_start_sample"] < minimum_gap:
                    continue
                if abs(second["tracking_cfo_hz"] - first["tracking_cfo_hz"]) > CFO_IDENTITY_HZ:
                    continue
                rebuilt.append({"receiver": receiver, "first": first, "second": second})
    published = row["application_pair_inventory"]
    if len(rebuilt) != len(published):
        raise ValueError("cannot reproduce published application pair inventory")
    keys = ("receiver", "probe_index", "probe_start_sample", "dwell_epoch_sample",
            "tracking_cfo_hz", "margin")
    for rebuilt_pair, published_pair in zip(rebuilt, published, strict=True):
        if int(rebuilt_pair["receiver"]) != int(published_pair["receiver"]):
            raise ValueError("published pair receiver ordering changed")
        for member in ("first", "second"):
            for key in keys:
                if key == "receiver":
                    continue
                left, right = rebuilt_pair[member][key], published_pair[member][key]
                if isinstance(left, float):
                    if not _same_float(left, right):
                        raise ValueError("published pair does not match deterministic reconstruction")
                elif left != right:
                    raise ValueError("published pair does not match deterministic reconstruction")
    return rebuilt


def select_pairs(row: dict[str, Any], receiver: int) -> list[dict[str, Any]]:
    inventory = row["application_pair_inventory"]
    available = [(index, pair) for index, pair in enumerate(inventory)
                 if int(pair["receiver"]) == receiver]
    if not available:
        raise ValueError("selected reference-positive receiver has no pair inventory")

    def strength(item: tuple[int, dict[str, Any]]) -> tuple[float, int]:
        index, pair = item
        return min(float(pair["first"]["margin"]), float(pair["second"]["margin"])), -index

    strongest_index, _ = max(available, key=strength)
    resolved_cache = {index: resolved_pair(row, index, "range_contrast") for index, _ in available}
    in_range = [
        (index, pair) for index, pair in available
        if all(
            abs(float(point["acquired_cfo_hz"])) <= SCORING_RANGE_HZ
            and abs(float(point["tracking_cfo_hz"])) <= SCORING_RANGE_HZ
            for point in resolved_cache[index]
        )
    ]
    selected = [(strongest_index, "strongest")]
    if in_range:
        constrained_index, _ = max(in_range, key=strength)
        if constrained_index != strongest_index:
            selected.append((constrained_index, "both_cfos_within_400khz"))
    output = []
    for pair_index, role in selected:
        output.append({
            "pair_inventory_index": pair_index,
            "pair_role": role,
            "minimum_reference_margin": min(
                float(inventory[pair_index]["first"]["margin"]),
                float(inventory[pair_index]["second"]["margin"]),
            ),
            "coordinates": resolved_pair(row, pair_index, role),
        })
    return output


def build_membership(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    membership = []
    for selected in selected_receiver_rows(receipt):
        row = receipt["rows"][selected["receipt_row_index"]]
        membership.append({**selected, "pairs": select_pairs(row, selected["receiver"])})
    return membership


def source_files() -> dict[str, str]:
    prior = json.loads(PRIOR_LOCK.read_text())
    if len(prior.get("files", {})) != 74:
        raise ValueError("prior source inventory must contain exactly 74 files")
    files = dict(prior["files"])
    required = {
        HERE / "DESIGN.md",
        HERE / "run_diagnostic.py",
        HERE / "test_reference_points_diagnostic.py",
        PRIOR_LOCK,
        PRIOR_RECEIPT,
        TG11 / "libtg11.so",
        ROOT / "src/leo/analysis/starlink/pilot_methods.py",
    }
    missing = [path for path in required if not path.exists()]
    if missing:
        raise ValueError(f"missing diagnostic sources: {missing}")
    for path in required:
        name, current = str(path.resolve()), digest(path)
        if name in files and files[name] != current:
            raise ValueError(f"current required source differs from prior pin: {name}")
        files[name] = current
    return dict(sorted(files.items()))


def freeze() -> None:
    if SOURCE_LOCK.exists():
        raise ValueError("preserve existing reference-point source lock")
    receipt = load_prior_receipt()
    membership = build_membership(receipt)
    payload = {
        "schema": "org.leo.research.native-reference-points-source-lock/v1",
        "frozen_before_outcomes": True,
        "files": source_files(),
        "prior_source_file_count": 74,
        "prior_receipt_sha256": digest(PRIOR_RECEIPT),
        "membership": membership,
        "membership_sha256": stable_hash(membership),
        "config": {
            "margin_gate_greater_than_or_equal": MARGIN_GATE,
            "identity_cfo_hz": CFO_IDENTITY_HZ,
            "identity_timing_seconds": TIMING_IDENTITY_S,
            "scoring_cfo_range_hz": SCORING_RANGE_HZ,
            "native_residual_support_hz": RESIDUAL_SUPPORT_HZ,
            "score_reproduction_absolute_tolerance": SCORE_REPRODUCTION_TOLERANCE,
            "cfo_reproduction_absolute_tolerance_hz": CFO_REPRODUCTION_TOLERANCE_HZ,
            "timeout_seconds": TIMEOUT_SECONDS,
            "calls_per_coordinate_per_method": 1,
            "affinity_cpu": 0,
        },
        "split": "development",
        "holdout_opened": False,
        "validation_opened": False,
    }
    with SOURCE_LOCK.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


def verify_lock() -> dict[str, Any]:
    lock = json.loads(SOURCE_LOCK.read_text())
    receipt = load_prior_receipt()
    membership = build_membership(receipt)
    if (lock.get("membership") != membership
            or lock.get("membership_sha256") != stable_hash(membership)
            or lock.get("prior_receipt_sha256") != digest(PRIOR_RECEIPT)
            or lock.get("split") != "development"):
        raise ValueError("frozen selection or prior receipt changed")
    for name, expected in lock["files"].items():
        if digest(name) != expected:
            raise ValueError(f"frozen source changed: {name}")
    return lock


def _complex_probe(raw: np.ndarray, coordinate: dict[str, Any], rate: int) -> np.ndarray:
    start = int(coordinate["probe_start_sample"])
    stop = start + rate // 50
    iq = raw[start:stop, int(coordinate["receiver"])]
    return np.asarray(iq[:, 0], dtype=np.float64) + 1j * np.asarray(iq[:, 1], dtype=np.float64)


def canonical_point(raw: np.ndarray, coordinate: dict[str, Any], rate: int, edge: str) -> dict[str, Any]:
    score = conditioned_glrt64_score(
        _complex_probe(raw, coordinate, rate), rate,
        epoch_sample=int(coordinate["local_epoch_sample"]),
        acquired_cfo_hz=float(coordinate["acquired_cfo_hz"]), edge=edge,
    )
    return {
        "supported": True,
        "status": "complete",
        "receiver": int(coordinate["receiver"]),
        "probe_index": int(coordinate["probe_index"]),
        "probe_start_sample": int(coordinate["probe_start_sample"]),
        "local_epoch_sample": int(coordinate["local_epoch_sample"]),
        "dwell_epoch_sample": int(coordinate["dwell_epoch_sample"]),
        "acquired_cfo_hz": float(coordinate["acquired_cfo_hz"]),
        "tracking_cfo_hz": float(score.tracking_cfo_hz),
        "residual_cfo_hz": float(score.residual_cfo_hz),
        "exact_score": float(score.exact_score),
        "control_score": float(score.control_score),
        "margin": float(score.margin),
    }


def verify_canonical_reproduction(point: dict[str, Any], coordinate: dict[str, Any]) -> None:
    for name, reference_name in (
        ("exact_score", "exact_score"),
        ("control_score", "control_score"),
        ("margin", "reference_margin"),
    ):
        if not math.isclose(
            float(point[name]), float(coordinate[reference_name]), rel_tol=0.0,
            abs_tol=SCORE_REPRODUCTION_TOLERANCE,
        ):
            raise ValueError(f"canonical {name} does not reproduce frozen application candidate")
    for name in ("residual_cfo_hz", "tracking_cfo_hz"):
        if not math.isclose(
            float(point[name]), float(coordinate[name]), rel_tol=0.0,
            abs_tol=CFO_REPRODUCTION_TOLERANCE_HZ,
        ):
            raise ValueError(f"canonical {name} does not reproduce frozen application candidate")


def native_point(engine: Any, raw: np.ndarray, coordinate: dict[str, Any]) -> dict[str, Any]:
    scoring = float(coordinate["acquired_cfo_hz"])
    expected = float(coordinate["tracking_cfo_hz"])
    if abs(scoring) > SCORING_RANGE_HZ:
        return {
            "supported": False, "status": "scoring_cfo_outside_known_range",
            "observation": None, "scoring_cfo_hz": scoring,
            "expected_physical_cfo_hz": expected,
        }
    if abs(expected - scoring) > RESIDUAL_SUPPORT_HZ:
        return {
            "supported": False, "status": "expected_residual_outside_known_range",
            "observation": None, "scoring_cfo_hz": scoring,
            "expected_physical_cfo_hz": expected,
        }
    observation = engine.guided(
        raw,
        receiver=int(coordinate["receiver"]),
        probe_index=int(coordinate["probe_index"]),
        predicted_local_epoch_sample=float(coordinate["local_epoch_sample"]),
        scoring_cfo_hz=scoring,
        expected_physical_cfo_hz=expected,
    )
    return {
        "supported": observation is not None,
        "status": "returned" if observation is not None else "native_guided_unsupported",
        "observation": jsonable(observation),
        "scoring_cfo_hz": scoring,
        "expected_physical_cfo_hz": expected,
    }


def timed(call: Any) -> tuple[Any, dict[str, float]]:
    cpu = time.process_time_ns()
    wall = time.perf_counter_ns()
    value = call()
    return value, {
        "cpu_ms": (time.process_time_ns() - cpu) / 1e6,
        "wall_ms": (time.perf_counter_ns() - wall) / 1e6,
    }


def _method_observation(point: dict[str, Any], method: str) -> dict[str, Any] | None:
    if method == "canonical_python":
        return point
    return point.get("observation")


def assess_pair(points: list[dict[str, Any]], coordinates: list[dict[str, Any]],
                method: str, rate: int) -> dict[str, Any]:
    observations = [_method_observation(point, method) for point in points]
    if any(item is None for item in observations):
        return {"passed": False, "reason": "unsupported", "point_assessments": []}
    point_assessments = []
    for observation, reference in zip(observations, coordinates, strict=True):
        assert observation is not None
        raw_timing_error = float(observation["dwell_epoch_sample"]) - float(reference["dwell_epoch_sample"])
        frame_period = rate / 750.0
        timing_error = (raw_timing_error + frame_period / 2) % frame_period - frame_period / 2
        physical_error = float(observation["tracking_cfo_hz"]) - float(reference["tracking_cfo_hz"])
        native_gates = True
        if method == "native_guided":
            native_gates = (
                int(observation["status"]) == 0
                and bool(observation["supported"])
                and bool(observation["valid_bounds"])
                and int(observation["support_frames"]) >= 2
                and bool(observation["fractional_complete"])
            )
        point_assessments.append({
            "native_full_gates_passed": native_gates,
            "margin_passed": float(observation["margin"]) >= MARGIN_GATE,
            "timing_error_samples": timing_error,
            "timing_identity_passed": abs(timing_error) <= rate * TIMING_IDENTITY_S,
            "physical_cfo_error_hz": physical_error,
            "physical_cfo_identity_passed": abs(physical_error) <= CFO_IDENTITY_HZ,
        })
    first, second = observations
    assert first is not None and second is not None
    pair_contract = (
        int(first["receiver"]) == int(second["receiver"])
        and int(second["probe_start_sample"]) - int(first["probe_start_sample"]) >= rate // 50
        and abs(float(second["tracking_cfo_hz"]) - float(first["tracking_cfo_hz"])) <= CFO_IDENTITY_HZ
    )
    passed = pair_contract and all(
        item["native_full_gates_passed"]
        and item["margin_passed"]
        and item["timing_identity_passed"]
        and item["physical_cfo_identity_passed"]
        for item in point_assessments
    )
    return {
        "passed": passed,
        "reason": "passed" if passed else "pair_or_point_gate_failed",
        "pair_contract_passed": pair_contract,
        "point_assessments": point_assessments,
    }


def run() -> None:
    if RESULT.exists():
        raise ValueError("preserve existing reference-point result")
    environment = {name: os.environ.get(name) for name in THREAD_ENV}
    if any(value != "1" for value in environment.values()):
        raise ValueError("all numerical thread counts must equal one")
    lock = verify_lock()
    cases = {case.id: case for case in dataset.real_prefix_cases()}
    selected_ids = {item["case_id"] for item in lock["membership"]}
    if any(cases[case_id].split != "development" for case_id in selected_ids):
        raise ValueError("only selected development IQ may be opened")
    affinity = os.sched_getaffinity(0)
    if 0 not in affinity:
        raise ValueError("CPU 0 unavailable")
    rows: list[dict[str, Any]] = []
    status, error = "complete", None
    started = time.perf_counter()
    previous_handler = signal.signal(
        signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError("120 second diagnostic bound")),
    )
    signal.alarm(TIMEOUT_SECONDS)
    try:
        raw_by_id = {case_id: dataset.load_iq(cases[case_id]) for case_id in selected_ids}
        hashes = {case_id: hashlib.sha256(raw).hexdigest() for case_id, raw in raw_by_id.items()}
        os.sched_setaffinity(0, {0})
        with ExitStack() as stack:
            engines = {
                geometry: stack.enter_context(NativeTG11(*geometry, library=TG11 / "libtg11.so"))
                for geometry in sorted({(cases[item["case_id"]].rate, cases[item["case_id"]].edge)
                                        for item in lock["membership"]})
            }
            point_number = 0
            for selection in lock["membership"]:
                case = cases[selection["case_id"]]
                raw = raw_by_id[case.id]
                pair_rows = []
                for pair in selection["pairs"]:
                    results = {"canonical_python": [], "native_guided": []}
                    timings = {"canonical_python": [], "native_guided": []}
                    orders = []
                    for coordinate in pair["coordinates"]:
                        order = ("canonical_python", "native_guided") if point_number % 2 == 0 else ("native_guided", "canonical_python")
                        point_number += 1
                        orders.append(list(order))
                        for method in order:
                            if method == "canonical_python":
                                value, timing = timed(lambda: canonical_point(raw, coordinate, case.rate, case.edge))
                                verify_canonical_reproduction(value, coordinate)
                            else:
                                value, timing = timed(lambda: native_point(engines[(case.rate, case.edge)], raw, coordinate))
                            results[method].append(value)
                            timings[method].append(timing)
                    pair_rows.append({
                        **pair,
                        "method_order_by_point": orders,
                        "results": results,
                        "timings": timings,
                        "assessment": {
                            method: assess_pair(results[method], pair["coordinates"], method, case.rate)
                            for method in ("canonical_python", "native_guided")
                        },
                    })
                if hashlib.sha256(raw).hexdigest() != hashes[case.id]:
                    raise ValueError(f"input mutated: {case.id}")
                rows.append({**{key: selection[key] for key in (
                    "receipt_row_index", "case_id", "rate_hz", "edge", "receiver", "category"
                )}, "raw_sha256": case.raw_sha256, "input_array_sha256": hashes[case.id],
                    "input_immutable": True, "pairs": pair_rows})
    except BaseException as exc:
        status, error = "failed", f"{type(exc).__name__}: {exc}"
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_handler)
        os.sched_setaffinity(0, affinity)
    stable = all(digest(name) == expected for name, expected in lock["files"].items())
    payload = {
        "schema": "org.leo.research.native-reference-points-result/v1",
        "status": status,
        "error": error,
        "complete": status == "complete" and len(rows) == len(lock["membership"]) and stable,
        "source_lock": lock,
        "source_lock_sha256": digest(SOURCE_LOCK),
        "source_lock_stable": stable,
        "prior_receipt_sha256": digest(PRIOR_RECEIPT),
        "thread_environment": environment,
        "affinity_cpu": 0,
        "affinity_restored": os.sched_getaffinity(0) == affinity,
        "rows": rows,
        "diagnostic_only": True,
        "native_guided_statistic_is_not_blind_conditioned_statistic": True,
        "holdout_opened": False,
        "validation_opened": False,
        "elapsed_seconds": time.perf_counter() - started,
    }
    with RESULT.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")
    if status != "complete" or not stable:
        raise RuntimeError(error or "source lock changed during diagnostic")


def main() -> None:
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--freeze", action="store_true")
    actions.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        run()


if __name__ == "__main__":
    main()
