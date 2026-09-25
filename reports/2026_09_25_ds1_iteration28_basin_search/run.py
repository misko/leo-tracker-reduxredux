#!/usr/bin/env python3
# ruff: noqa: E402
"""DS1 iteration 28: sealed truth-blind basin bracketing and closure."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import multiprocessing as mp
import os
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

for _name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
I27_DIR = ROOT / "reports/2026_09_25_ds1_iteration27_phase_cache"
I27_RUN = I27_DIR / "run.py"
I27_PLAN = I27_DIR / "plan.json"
I27_SMOKE = I27_DIR / "smoke.json"
I27_STENCIL = I27_DIR / "stencil.json"
I27_CHECKPOINT = I27_DIR / "checkpoint.json"
CACHE_MANIFEST = Path("/tmp/ds1-iteration27-phase-state-cache/manifest.json")
ANCHOR = (37.85822833, -122.47896246)
GROUPS = ("20260921_00", "20260921_16")
GROUP_WEIGHTS = {"20260921_00": 0.2742, "20260921_16": 0.7258}
EXPECTED_INPUTS = {
    "iteration27_plan": "sha256:237a773ab67f2417d3edfc300bb6462bc862cb7d0053f835378ea8ee9763891f",
    "iteration27_runner": "sha256:9a3814244c695dedf48058fd6c36b60222a8f970e54706112d6db50933410c18",
    "iteration27_smoke": "sha256:d6792f8607a11c39e5d14a9373c781814ae55efc486118756ab1024fff391202",
    "iteration27_stencil": (
        "sha256:f21d1473597cca0d944c128e2e63428ad6ca373afa27cc8fab1af10149503d36"
    ),
    "iteration27_checkpoint": (
        "sha256:f16a2516e7b0e005c573c3262a5a476d34409c479b4d56f0913746c6674efab2"
    ),
    "iteration27_cache_manifest": (
        "sha256:300af370054740cb527f88ef94cbbd24d3a2d8f6cf8d312b8eb7959beec2b9d3"
    ),
}
MAX_WORKERS = 4
MAX_ERROR_HZ = 0.2
MAX_TAIL = 1e-4
RADIAL_CAP_M = 6250.0
GOLDEN = (math.sqrt(5.0) - 1.0) / 2.0

_I27: Any = None
_CONTEXTS: dict[str, Any] | None = None
_CACHE: Any = None


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def verified_json(path: Path) -> dict[str, Any]:
    seal = path.with_suffix(path.suffix + ".sha256")
    if not seal.exists() or seal.read_text().strip().split()[0] != digest(path).split(":", 1)[1]:
        raise ValueError(f"bad seal: {path}")
    return json.loads(path.read_text())


def write_sealed(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.with_suffix(path.suffix + ".sha256").exists():
        raise FileExistsError(path)
    content = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(content)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "  " + path.name + "\n"
    )


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def validate_plan(plan: dict[str, Any]) -> None:
    if plan.get("schema") != "ds1-iteration28-basin-search-plan/v1":
        raise ValueError("plan schema mismatch")
    if plan.get("status") != "sealed-before-output":
        raise ValueError("plan was not sealed before output")
    inputs = plan.get("inputs", {})
    if any(inputs.get(key) != value for key, value in EXPECTED_INPUTS.items()):
        raise ValueError("plan input binding mismatch")
    policy = plan.get("data_policy", {})
    if policy.get("partition") != "original randomized TRAIN rows only":
        raise ValueError("partition mismatch")
    if policy.get("truth_used") is not False or policy.get("held_used") is not False:
        raise ValueError("truth/HELD forbidden")
    if plan.get("execution", {}).get("maximum_workers") != MAX_WORKERS:
        raise ValueError("worker plan mismatch")
    if plan.get("transverse_and_powell", {}).get("radial_cap_m") != RADIAL_CAP_M:
        raise ValueError("radial cap mismatch")
    if plan.get("numerical_gates", {}).get("maximum_atlas_direct_doppler_error_hz") != MAX_ERROR_HZ:
        raise ValueError("atlas gate mismatch")


def validate_inputs() -> dict[str, Any]:
    paths = {
        "iteration27_plan": I27_PLAN,
        "iteration27_runner": I27_RUN,
        "iteration27_smoke": I27_SMOKE,
        "iteration27_stencil": I27_STENCIL,
        "iteration27_checkpoint": I27_CHECKPOINT,
        "iteration27_cache_manifest": CACHE_MANIFEST,
    }
    found = {key: digest(path) for key, path in paths.items()}
    if found != EXPECTED_INPUTS:
        raise ValueError(f"iteration-27 input drift: {found}")
    for path in (I27_PLAN, I27_SMOKE, I27_STENCIL, I27_CHECKPOINT):
        verified_json(path)
    manifest = json.loads(CACHE_MANIFEST.read_text())
    if manifest.get("schema") != "ds1-phase-state-cache/v1" or not manifest.get("complete"):
        raise ValueError("invalid cache manifest")
    if manifest.get("truth_used") is not False or manifest.get("held_used") is not False:
        raise ValueError("cache truth/HELD contamination")
    for record in manifest.get("records", []):
        chunk = CACHE_MANIFEST.parent / record["chunk"]
        if chunk.stat().st_size != record["chunk_bytes"] or digest(chunk) != record["chunk_digest"]:
            raise ValueError(f"cache chunk drift: {chunk}")
    return {
        **found,
        "cache_record_count": len(manifest["records"]),
        "cache_chunk_bytes": manifest["chunk_bytes"],
    }


def bindings() -> dict[str, Any]:
    return {
        "plan": digest(PLAN),
        "runner": digest(Path(__file__)),
        **validate_inputs(),
    }


def float_key(east_m: float, north_m: float) -> str:
    bits = np.asarray([east_m, north_m], dtype="<f8").view("<u8")
    return f"{int(bits[0]):016x}:{int(bits[1]):016x}"


def enu_to_geodetic(east_m: float, north_m: float) -> tuple[float, float]:
    """Map a tangent-plane offset at the sealed anchor through WGS84 ECEF."""
    a = 6378137.0
    f = 1.0 / 298.257223563
    e2 = f * (2.0 - f)
    lat0, lon0 = map(math.radians, ANCHOR)
    n0 = a / math.sqrt(1.0 - e2 * math.sin(lat0) ** 2)
    origin = np.asarray(
        [
            n0 * math.cos(lat0) * math.cos(lon0),
            n0 * math.cos(lat0) * math.sin(lon0),
            n0 * (1.0 - e2) * math.sin(lat0),
        ]
    )
    east = np.asarray([-math.sin(lon0), math.cos(lon0), 0.0])
    north = np.asarray(
        [-math.sin(lat0) * math.cos(lon0), -math.sin(lat0) * math.sin(lon0), math.cos(lat0)]
    )
    x, y, z = origin + east_m * east + north_m * north
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - e2))
    for _ in range(12):
        n = a / math.sqrt(1.0 - e2 * math.sin(lat) ** 2)
        height = p / math.cos(lat) - n
        updated = math.atan2(z, p * (1.0 - e2 * n / (n + height)))
        if abs(updated - lat) < 1e-15:
            lat = updated
            break
        lat = updated
    return math.degrees(lat), math.degrees(lon)


def quadratic_surface(rows: Iterable[dict[str, Any]], score_key: str) -> dict[str, Any]:
    rows = list(rows)
    x = np.asarray(
        [
            [
                1.0,
                r["east_m"],
                r["north_m"],
                0.5 * r["east_m"] ** 2,
                r["east_m"] * r["north_m"],
                0.5 * r["north_m"] ** 2,
            ]
            for r in rows
        ]
    )
    y = np.asarray([r[score_key] for r in rows])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    h = np.asarray([[coef[3], coef[4]], [coef[4], coef[5]]])
    eigen = np.linalg.eigvalsh(h)
    stationary = -np.linalg.solve(h, coef[1:3]) if np.all(eigen > 0) else np.full(2, np.nan)
    return {
        "intercept": float(coef[0]),
        "gradient_score_per_m": [float(coef[1]), float(coef[2])],
        "hessian_score_per_m2": h.tolist(),
        "hessian_eigenvalues": eigen.tolist(),
        "positive_definite": bool(np.all(eigen > 0)),
        "stationary_east_m": float(stationary[0]),
        "stationary_north_m": float(stationary[1]),
        "fit_rms": float(np.sqrt(np.mean((x @ coef - y) ** 2))),
    }


def stencil_leaveout_rows(
    stencil: dict[str, Any], excluded_group: str, index: int
) -> list[dict[str, Any]]:
    rows = []
    for cell in stencil["cells"]:
        group_scores = {}
        for group in GROUPS:
            values = np.asarray([s["score"] for s in cell["groups"][group]["actual"]["sessions"]])
            group_scores[group] = (
                float(np.mean(np.delete(values, index)))
                if group == excluded_group
                else float(np.mean(values))
            )
        rows.append(
            {
                "east_m": cell["east_m"],
                "north_m": cell["north_m"],
                "score": sum(GROUP_WEIGHTS[g] * group_scores[g] for g in GROUPS),
            }
        )
    return rows


def direction_checkpoint() -> dict[str, Any]:
    stencil = verified_json(I27_STENCIL)
    full_rows = [
        {"east_m": c["east_m"], "north_m": c["north_m"], "score": c["actual_material_score"]}
        for c in stencil["cells"]
    ]
    full = quadratic_surface(full_rows, "score")
    gradient = np.asarray(full["gradient_score_per_m"])
    norm = float(np.linalg.norm(gradient))
    direction = -gradient / norm
    orthogonal = np.asarray([direction[1], -direction[0]])
    leaveouts = []
    for group in GROUPS:
        sessions = stencil["cells"][0]["groups"][group]["actual"]["sessions"]
        for index, session in enumerate(sessions):
            fit = quadratic_surface(stencil_leaveout_rows(stencil, group, index), "score")
            loo_gradient = np.asarray(fit["gradient_score_per_m"])
            leaveouts.append(
                {
                    "excluded_group_id": group,
                    "excluded_session_id": session["session_id"],
                    "fit": fit,
                    "gradient_dot_full": float(loo_gradient @ gradient),
                }
            )
    criteria = {
        "finite_nonzero_full_gradient": bool(np.all(np.isfinite(gradient)) and norm > 0),
        "full_hessian_positive_definite": full["positive_definite"],
        "all_leave_one_session_gradients_agree": all(r["gradient_dot_full"] > 0 for r in leaveouts),
        "all_leave_one_session_hessians_positive_definite": all(
            r["fit"]["positive_definite"] for r in leaveouts
        ),
        "leave_one_session_count": len(leaveouts) == 12,
    }
    return {
        "schema": "ds1-iteration28-direction/v1",
        "complete": True,
        "truth_used": False,
        "held_used": False,
        "bindings": bindings(),
        "iteration27_stencil_digest": digest(I27_STENCIL),
        "full_surface": full,
        "descent_direction_east_north": direction.tolist(),
        "descent_bearing_deg": float(math.degrees(math.atan2(direction[0], direction[1])) % 360.0),
        "orthogonal_direction_east_north": orthogonal.tolist(),
        "leave_one_session_surfaces": leaveouts,
        "gate": {"criteria": criteria, "passed": all(criteria.values())},
    }


def init_worker() -> None:
    global _I27, _CONTEXTS, _CACHE
    _I27 = load_module(I27_RUN, f"i28_i27_{os.getpid()}")
    _CONTEXTS = {group: _I27.prepare_group(group) for group in GROUPS}
    _CACHE = _I27.PhaseStateCache(_CONTEXTS, create=False)
    if _CACHE.provenance()["manifest_digest"] != EXPECTED_INPUTS["iteration27_cache_manifest"]:
        raise ValueError("worker cache mismatch")


def score_cell_task(coordinate: tuple[float, float]) -> dict[str, Any]:
    if _I27 is None or _CONTEXTS is None or _CACHE is None:
        init_worker()
    east_m, north_m = map(float, coordinate)
    if math.hypot(east_m, north_m) > RADIAL_CAP_M + 1e-9:
        raise ValueError("radial cap exceeded")
    latitude, longitude = enu_to_geodetic(east_m, north_m)
    per_group = {}
    maximum_error = float(_CACHE.provenance()["maximum_adjacent_midpoint_error_hz"])
    maximum_tail = 0.0
    midpoint_count = 0
    for group, context in _CONTEXTS.items():
        receiver = context.search.receiver_ecef(latitude, longitude)[0]
        midpoint_error, count = _CACHE.validate_midpoints(context, [receiver])
        maximum_error = max(maximum_error, midpoint_error)
        midpoint_count += count
        surrogate_acc = np.zeros(len(context.sessions))
        actual_acc = np.zeros(len(context.sessions))
        for source in sorted(np.unique(context.data.source.astype(str))):
            evaluator = _I27.SourceEvaluator(context, source, receiver, _CACHE)
            modes = evaluator.modes()
            fine = evaluator.integrate(16.0, 0.0125)
            surrogate_acc += fine["expected_session_numerators"]
            audit = _I27.audit_distribution(evaluator, fine, modes)
            actual_acc += audit["actual_material_session_numerators"]
            maximum_error = max(maximum_error, audit["maximum_absolute_prediction_error_hz"])
            maximum_tail = max(maximum_tail, fine["tail_mass"])
        per_group[group] = {
            "surrogate": _I27.score_sessions(context, surrogate_acc),
            "actual": _I27.score_sessions(context, actual_acc),
        }
    surrogate = _I27.pool({g: per_group[g]["surrogate"] for g in GROUPS})
    actual = _I27.pool({g: per_group[g]["actual"] for g in GROUPS})
    return {
        "coordinate_key": float_key(east_m, north_m),
        "east_m": east_m,
        "north_m": north_m,
        "latitude_deg": latitude,
        "longitude_deg": longitude,
        "surrogate_score": surrogate,
        "actual_material_score": actual,
        "atlas_direct_pooled_score_discrepancy": actual - surrogate,
        "maximum_atlas_direct_doppler_error_hz": maximum_error,
        "maximum_tail_mass": maximum_tail,
        "adjacent_midpoint_validation_count": midpoint_count,
        "groups": per_group,
    }


def anchor_row() -> dict[str, Any]:
    stencil = verified_json(I27_STENCIL)
    row = next(c for c in stencil["cells"] if c["east_m"] == 0 and c["north_m"] == 0)
    return {
        "coordinate_key": float_key(0.0, 0.0),
        "east_m": 0.0,
        "north_m": 0.0,
        "latitude_deg": ANCHOR[0],
        "longitude_deg": ANCHOR[1],
        "surrogate_score": row["surrogate_score"],
        "actual_material_score": row["actual_material_score"],
        "atlas_direct_pooled_score_discrepancy": row["actual_material_score"]
        - row["surrogate_score"],
        "maximum_atlas_direct_doppler_error_hz": stencil["maximum_atlas_validation_error_hz"],
        "maximum_tail_mass": stencil["maximum_tail_mass"],
        "adjacent_midpoint_validation_count": stencil["per_cell_adjacent_midpoint_validation_count"]
        // 9,
        "groups": row["groups"],
        "reused_bit_for_bit_from_iteration27": True,
    }


class Scorer:
    def __init__(self, workers: int) -> None:
        self.rows: dict[str, dict[str, Any]] = {float_key(0.0, 0.0): anchor_row()}
        self.pool = mp.get_context("spawn").Pool(workers, initializer=init_worker)

    def close(self) -> None:
        self.pool.close()
        self.pool.join()

    def score(self, coordinates: Iterable[tuple[float, float]]) -> list[dict[str, Any]]:
        requested = [(float(e), float(n)) for e, n in coordinates]
        missing = [p for p in requested if float_key(*p) not in self.rows]
        if missing:
            if any(math.hypot(*p) > RADIAL_CAP_M + 1e-9 for p in missing):
                raise ValueError("radial cap exceeded")
            for row in self.pool.map(score_cell_task, missing):
                self.rows[row["coordinate_key"]] = row
        return [self.rows[float_key(*p)] for p in requested]


def decision(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    actual = sorted(rows, key=lambda r: (r["actual_material_score"], r["coordinate_key"]))
    surrogate = sorted(rows, key=lambda r: (r["surrogate_score"], r["coordinate_key"]))
    gap = float(actual[1]["actual_material_score"] - actual[0]["actual_material_score"])
    discrepancy = max(abs(r["atlas_direct_pooled_score_discrepancy"]) for r in rows)
    threshold = max(1e-10, 10.0 * discrepancy)
    criteria = {
        "atlas_direct_winner_match": actual[0]["coordinate_key"] == surrogate[0]["coordinate_key"],
        "decision_gap": gap > threshold,
        "atlas_direct_doppler": max(r["maximum_atlas_direct_doppler_error_hz"] for r in rows)
        <= MAX_ERROR_HZ,
        "tail_mass": max(r["maximum_tail_mass"] for r in rows) <= MAX_TAIL,
    }
    return {
        "label": label,
        "actual_winner_key": actual[0]["coordinate_key"],
        "surrogate_winner_key": surrogate[0]["coordinate_key"],
        "actual_winner_east_m": actual[0]["east_m"],
        "actual_winner_north_m": actual[0]["north_m"],
        "actual_winner_score": actual[0]["actual_material_score"],
        "runner_up_gap": gap,
        "maximum_absolute_atlas_direct_pooled_score_discrepancy": discrepancy,
        "required_gap": threshold,
        "criteria": criteria,
        "passed": all(criteria.values()),
    }


def point(origin: np.ndarray, direction: np.ndarray, offset: float) -> tuple[float, float]:
    value = origin + float(offset) * direction
    return float(value[0]), float(value[1])


def refine_bracket(
    scorer: Scorer,
    origin: np.ndarray,
    direction: np.ndarray,
    scalar_rows: dict[float, dict[str, Any]],
    maximum_new: int = 8,
    stop_width: float = 97.65625,
) -> dict[str, Any]:
    history = []
    for iteration in range(maximum_new + 1):
        ordered = sorted(scalar_rows)
        winner_index = min(
            range(len(ordered)),
            key=lambda i: (scalar_rows[ordered[i]]["actual_material_score"], ordered[i]),
        )
        if winner_index in (0, len(ordered) - 1):
            return {"passed": False, "reason": "unbracketed endpoint winner", "history": history}
        left, center, right = ordered[winner_index - 1 : winner_index + 2]
        local_rows = [scalar_rows[x] for x in (left, center, right)]
        gate = decision(local_rows, f"refine-{iteration}")
        history.append(
            {
                "iteration": iteration,
                "left_m": left,
                "center_m": center,
                "right_m": right,
                "decision": gate,
            }
        )
        if not gate["passed"]:
            return {"passed": False, "reason": "numerical decision gate", "history": history}
        if right - left <= stop_width:
            return {
                "passed": True,
                "best_offset_m": center,
                "bracket_m": [left, right],
                "history": history,
            }
        yl, yc, yr = (scalar_rows[x]["actual_material_score"] for x in (left, center, right))
        numerator = (center - left) ** 2 * (yc - yr) - (center - right) ** 2 * (yc - yl)
        denominator = 2.0 * ((center - left) * (yc - yr) - (center - right) * (yc - yl))
        proposal = center - numerator / denominator if denominator else math.nan
        margin = 0.1 * (right - left)
        existing = np.asarray(ordered)
        if (
            not math.isfinite(proposal)
            or not left + margin < proposal < right - margin
            or np.min(np.abs(existing - proposal)) < 1e-8
        ):
            if right - center >= center - left:
                proposal = center + (1.0 - GOLDEN) * (right - center)
            else:
                proposal = center - (1.0 - GOLDEN) * (center - left)
        scalar_rows[float(proposal)] = scorer.score([point(origin, direction, proposal)])[0]
    return {"passed": False, "reason": "refinement budget exhausted", "history": history}


def bracket_line(
    scorer: Scorer,
    origin: np.ndarray,
    direction: np.ndarray,
    label: str,
    initial_offsets: list[float] | None = None,
) -> dict[str, Any]:
    offsets = list(initial_offsets or [-195.3125, 0.0, 195.3125])
    rows = scorer.score([point(origin, direction, value) for value in offsets])
    scalar_rows = dict(zip(offsets, rows, strict=True))
    decisions = []
    radii = [390.625, 781.25, 1562.5, 3125.0]
    while True:
        ordered = sorted(scalar_rows)
        local = [scalar_rows[x] for x in ordered]
        gate = decision(local, f"{label}-bracket-{len(decisions)}")
        decisions.append(gate)
        if not gate["passed"]:
            return {"passed": False, "reason": "numerical decision gate", "decisions": decisions}
        winner = min(ordered, key=lambda x: (scalar_rows[x]["actual_material_score"], x))
        if winner not in (ordered[0], ordered[-1]):
            break
        sign = -1.0 if winner == ordered[0] else 1.0
        candidates = [
            sign * radius
            for radius in radii
            if sign * radius not in scalar_rows and abs(sign * radius) > abs(winner)
        ]
        if not candidates:
            return {"passed": False, "reason": "line cap endpoint winner", "decisions": decisions}
        offset = candidates[0]
        scalar_rows[offset] = scorer.score([point(origin, direction, offset)])[0]
    refined = refine_bracket(scorer, origin, direction, scalar_rows)
    return {
        "passed": refined["passed"],
        "reason": refined.get("reason"),
        "decisions": decisions,
        "refinement": refined,
        "sampled_offsets_m": sorted(scalar_rows),
        "best_point": point(origin, direction, refined["best_offset_m"])
        if refined["passed"]
        else None,
    }


def primary_ray(scorer: Scorer, direction: np.ndarray) -> dict[str, Any]:
    origin = np.zeros(2)
    offsets = [-195.3125, 0.0, 195.3125, 390.625, 781.25, 1562.5, 3125.0, 6250.0]
    rows = scorer.score([point(origin, direction, value) for value in offsets])
    scalar_rows = dict(zip(offsets, rows, strict=True))
    gate = decision(rows, "primary-ray-coarse")
    winner_index = min(
        range(len(offsets)), key=lambda i: (rows[i]["actual_material_score"], offsets[i])
    )
    if not gate["passed"]:
        return {"passed": False, "reason": "numerical decision gate", "coarse_decision": gate}
    if winner_index in (0, len(offsets) - 1):
        return {"passed": False, "reason": "primary ray endpoint winner", "coarse_decision": gate}
    refined = refine_bracket(scorer, origin, direction, scalar_rows)
    return {
        "passed": refined["passed"],
        "reason": refined.get("reason"),
        "coarse_decision": gate,
        "sampled_offsets_m": sorted(scalar_rows),
        "refinement": refined,
        "best_point": point(origin, direction, refined["best_offset_m"])
        if refined["passed"]
        else None,
    }


def pattern_closure(scorer: Scorer, start: np.ndarray) -> dict[str, Any]:
    center = np.asarray(start, float)
    spacings = [195.3125, 97.65625, 48.828125, 24.4140625]
    budgets = [4, 2, 2, 2]
    stages = []
    final_rows = None
    for spacing, budget in zip(spacings, budgets, strict=True):
        translations = 0
        polls = []
        while True:
            coords = [
                (float(center[0] + e), float(center[1] + n))
                for n in (-spacing, 0.0, spacing)
                for e in (-spacing, 0.0, spacing)
            ]
            rows = scorer.score(coords)
            gate = decision(rows, f"pattern-{spacing:.7f}-{translations}")
            winner = min(rows, key=lambda r: (r["actual_material_score"], r["coordinate_key"]))
            center_key = float_key(float(center[0]), float(center[1]))
            polls.append(
                {
                    "center_east_m": float(center[0]),
                    "center_north_m": float(center[1]),
                    "decision": gate,
                }
            )
            if not gate["passed"]:
                return {
                    "passed": False,
                    "reason": "numerical decision gate",
                    "stages": stages + [{"spacing_m": spacing, "polls": polls}],
                }
            if winner["coordinate_key"] == center_key:
                final_rows = rows
                stages.append({"spacing_m": spacing, "translations": translations, "polls": polls})
                break
            translations += 1
            if translations > budget:
                return {
                    "passed": False,
                    "reason": "pattern translation budget exhausted",
                    "stages": stages + [{"spacing_m": spacing, "polls": polls}],
                }
            center = np.asarray([winner["east_m"], winner["north_m"]])
            if np.linalg.norm(center) > RADIAL_CAP_M:
                return {
                    "passed": False,
                    "reason": "pattern radial cap",
                    "stages": stages + [{"spacing_m": spacing, "polls": polls}],
                }
    assert final_rows is not None
    local_rows = [
        {
            **row,
            "local_east_m": row["east_m"] - center[0],
            "local_north_m": row["north_m"] - center[1],
        }
        for row in final_rows
    ]
    fit_rows = [
        {
            "east_m": r["local_east_m"],
            "north_m": r["local_north_m"],
            "score": r["actual_material_score"],
        }
        for r in local_rows
    ]
    fit = quadratic_surface(fit_rows, "score")
    half = spacings[-1] / 2.0
    proposal_inside = (
        fit["positive_definite"]
        and abs(fit["stationary_east_m"]) <= half
        and abs(fit["stationary_north_m"]) <= half
    )
    if not proposal_inside:
        return {
            "passed": False,
            "reason": "quadratic stationary point outside half cell",
            "stages": stages,
            "final_fit": fit,
        }
    proposal = center + np.asarray([fit["stationary_east_m"], fit["stationary_north_m"]])
    spacing = spacings[-1]
    fresh_coords = [
        (float(proposal[0] + e), float(proposal[1] + n))
        for n in (-spacing, 0.0, spacing)
        for e in (-spacing, 0.0, spacing)
    ]
    fresh_rows = scorer.score(fresh_coords)
    fresh_gate = decision(fresh_rows, "fresh-final-poll")
    fresh_winner = min(fresh_rows, key=lambda r: (r["actual_material_score"], r["coordinate_key"]))
    proposal_key = float_key(float(proposal[0]), float(proposal[1]))
    passed = fresh_gate["passed"] and fresh_winner["coordinate_key"] == proposal_key
    return {
        "passed": passed,
        "reason": None if passed else "fresh final poll did not select center",
        "stages": stages,
        "final_fit": fit,
        "proposal_east_m": float(proposal[0]),
        "proposal_north_m": float(proposal[1]),
        "fresh_poll_decision": fresh_gate,
        "fresh_poll_center_won": fresh_winner["coordinate_key"] == proposal_key,
    }


def omit_score(row: dict[str, Any], excluded_group: str, excluded_index: int) -> float:
    total = 0.0
    for group in GROUPS:
        values = np.asarray([s["score"] for s in row["groups"][group]["actual"]["sessions"]])
        group_score = (
            float(np.mean(np.delete(values, excluded_index)))
            if group == excluded_group
            else float(np.mean(values))
        )
        total += GROUP_WEIGHTS[group] * group_score
    return total


def stability_tile(scorer: Scorer, estimate: np.ndarray) -> dict[str, Any]:
    offsets = [-390.625, -195.3125, 0.0, 195.3125, 390.625]
    coords = [(float(estimate[0] + e), float(estimate[1] + n)) for n in offsets for e in offsets]
    rows = scorer.score(coords)
    full_gate = decision(rows, "stability-full")
    full_winner = min(rows, key=lambda r: (r["actual_material_score"], r["coordinate_key"]))
    center_key = float_key(float(estimate[0]), float(estimate[1]))
    leaveouts = []
    for group in GROUPS:
        sessions = rows[0]["groups"][group]["actual"]["sessions"]
        for excluded_index, session in enumerate(sessions):
            ranked = sorted(
                ((omit_score(row, group, excluded_index), row) for row in rows),
                key=lambda pair: (pair[0], pair[1]["coordinate_key"]),
            )
            winner = ranked[0][1]
            local_e = winner["east_m"] - estimate[0]
            local_n = winner["north_m"] - estimate[1]
            off_ring = abs(local_e) < 390.625 - 1e-9 and abs(local_n) < 390.625 - 1e-9
            neighbourhood = [
                row
                for row in rows
                if abs(row["east_m"] - winner["east_m"]) <= 195.3125 + 1e-9
                and abs(row["north_m"] - winner["north_m"]) <= 195.3125 + 1e-9
            ]
            fit = None
            inside = False
            estimated = np.asarray([winner["east_m"], winner["north_m"]])
            if len(neighbourhood) == 9:
                fit_rows = [
                    {
                        "east_m": row["east_m"] - winner["east_m"],
                        "north_m": row["north_m"] - winner["north_m"],
                        "score": omit_score(row, group, excluded_index),
                    }
                    for row in neighbourhood
                ]
                fit = quadratic_surface(fit_rows, "score")
                inside = (
                    fit["positive_definite"]
                    and abs(fit["stationary_east_m"]) <= 195.3125
                    and abs(fit["stationary_north_m"]) <= 195.3125
                )
                if inside:
                    estimated += np.asarray([fit["stationary_east_m"], fit["stationary_north_m"]])
            displacement = float(np.linalg.norm(estimated - estimate))
            leaveouts.append(
                {
                    "excluded_group_id": group,
                    "excluded_session_id": session["session_id"],
                    "winner_east_m": winner["east_m"],
                    "winner_north_m": winner["north_m"],
                    "winner_off_outer_ring": off_ring,
                    "local_fit": fit,
                    "stationary_inside_neighbourhood": inside,
                    "estimate_east_m": float(estimated[0]),
                    "estimate_north_m": float(estimated[1]),
                    "displacement_from_full_m": displacement,
                }
            )
    displacements = [row["displacement_from_full_m"] for row in leaveouts]
    criteria = {
        "full_numerical_gate": full_gate["passed"],
        "full_center_winner": full_winner["coordinate_key"] == center_key,
        "all_12_leave_one_session_winners_off_outer_ring": len(leaveouts) == 12
        and all(row["winner_off_outer_ring"] for row in leaveouts),
        "all_12_leave_one_session_local_fits_valid": len(leaveouts) == 12
        and all(row["stationary_inside_neighbourhood"] for row in leaveouts),
        "maximum_leave_one_session_displacement": max(displacements) <= 500.0,
        "median_leave_one_session_displacement": float(np.median(displacements)) <= 250.0,
    }
    return {
        "passed": all(criteria.values()),
        "criteria": criteria,
        "full_decision": full_gate,
        "full_center_won": full_winner["coordinate_key"] == center_key,
        "leave_one_session": leaveouts,
        "maximum_displacement_m": max(displacements),
        "median_displacement_m": float(np.median(displacements)),
    }


def summarized_cells(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda r: (r["north_m"], r["east_m"]))


def run_search(
    direction_record: dict[str, Any], workers: int
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    begun = time.perf_counter()
    direction = np.asarray(direction_record["descent_direction_east_north"], float)
    orthogonal = np.asarray(direction_record["orthogonal_direction_east_north"], float)
    scorer = Scorer(workers)
    stages = []
    try:
        primary = primary_ray(scorer, direction)
        stages.append({"stage": 1, "name": "primary_ray", **primary})
        if not primary["passed"]:
            return finish_search(scorer, stages, begun, "primary ray failed")
        p = np.asarray(primary["best_point"])
        transverse = bracket_line(scorer, p, orthogonal, "transverse")
        stages.append({"stage": 2, "name": "transverse", **transverse})
        if not transverse["passed"]:
            return finish_search(scorer, stages, begun, "transverse bracket failed")
        p = np.asarray(transverse["best_point"])
        displacement = p
        d2 = (
            displacement / np.linalg.norm(displacement)
            if np.linalg.norm(displacement) > 1e-12
            else direction
        )
        q2 = np.asarray([d2[1], -d2[0]])
        powell_d = bracket_line(scorer, p, d2, "powell-primary")
        if not powell_d["passed"]:
            stages.append({"stage": 2, "name": "powell_primary", **powell_d})
            return finish_search(scorer, stages, begun, "Powell primary bracket failed")
        p = np.asarray(powell_d["best_point"])
        powell_q = bracket_line(scorer, p, q2, "powell-orthogonal")
        stages.extend(
            [
                {"stage": 2, "name": "powell_primary", **powell_d},
                {"stage": 2, "name": "powell_orthogonal", **powell_q},
            ]
        )
        if not powell_q["passed"]:
            return finish_search(scorer, stages, begun, "Powell orthogonal bracket failed")
        p = np.asarray(powell_q["best_point"])
        closure = pattern_closure(scorer, p)
        stages.append({"stage": 3, "name": "pattern_closure", **closure})
        if not closure["passed"]:
            return finish_search(scorer, stages, begun, "pattern closure failed")
        estimate = np.asarray([closure["proposal_east_m"], closure["proposal_north_m"]])
        stability = stability_tile(scorer, estimate)
        stages.append({"stage": 4, "name": "stability_tile", **stability})
        reason = None if stability["passed"] else "stability tile failed"
        return finish_search(scorer, stages, begun, reason, estimate)
    finally:
        scorer.close()


def finish_search(
    scorer: Scorer,
    stages: list[dict[str, Any]],
    begun: float,
    failure_reason: str | None,
    estimate: np.ndarray | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    rows = summarized_cells(scorer.rows.values())
    maximum_error = max(r["maximum_atlas_direct_doppler_error_hz"] for r in rows)
    maximum_tail = max(r["maximum_tail_mass"] for r in rows)
    repeat_difference = None
    if estimate is not None:
        first = scorer.rows[float_key(float(estimate[0]), float(estimate[1]))][
            "actual_material_score"
        ]
        repeated = score_cell_task((float(estimate[0]), float(estimate[1])))[
            "actual_material_score"
        ]
        repeat_difference = abs(first - repeated)
    numerical = {
        "maximum_atlas_direct_doppler_error_hz": maximum_error,
        "maximum_tail_mass": maximum_tail,
        "repeated_final_score_absolute_difference": repeat_difference,
        "atlas_direct_gate": maximum_error <= MAX_ERROR_HZ,
        "tail_mass_gate": maximum_tail <= MAX_TAIL,
        "repeat_gate": repeat_difference is not None and repeat_difference <= 1e-12,
    }
    qualified = failure_reason is None and all(
        numerical[k] for k in ("atlas_direct_gate", "tail_mass_gate", "repeat_gate")
    )
    inference = {
        "schema": "ds1-iteration28-basin-search-inference/v1",
        "complete": True,
        "truth_used": False,
        "held_used": False,
        "bindings": bindings(),
        "direction_checkpoint": digest(HERE / "stage-0-direction.json"),
        "elapsed_s": time.perf_counter() - begun,
        "workers_used": MAX_WORKERS,
        "cell_count": len(rows),
        "stages": stages,
        "numerical": numerical,
        "estimate": None
        if estimate is None
        else {
            "east_m": float(estimate[0]),
            "north_m": float(estimate[1]),
            "latitude_deg": enu_to_geodetic(float(estimate[0]), float(estimate[1]))[0],
            "longitude_deg": enu_to_geodetic(float(estimate[0]), float(estimate[1]))[1],
        },
        "failure_reason": failure_reason,
    }
    qualification = {
        "schema": "ds1-iteration28-basin-search-qualification/v1",
        "complete": True,
        "truth_used": False,
        "held_used": False,
        "inference_pending_digest": True,
        "qualified": qualified,
        "failure_reason": failure_reason
        if failure_reason is not None
        else (None if qualified else "numerical gate failed"),
        "requirements": {
            "direction_gate": True,
            "all_search_stages_passed": failure_reason is None,
            "no_terminal_boundary_point": failure_reason is None,
            "numerical_gates": all(
                numerical[k] for k in ("atlas_direct_gate", "tail_mass_gate", "repeat_gate")
            ),
            "truth_blind": True,
            "held_blind": True,
        },
    }
    return inference, qualification, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("direction", "search"), required=True)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()
    validate_plan(verified_json(PLAN))
    validate_inputs()
    if args.stage == "direction":
        output = HERE / "stage-0-direction.json"
        record = direction_checkpoint()
        write_sealed(output, record)
        print(
            json.dumps({"output": str(output), "passed": record["gate"]["passed"]}, sort_keys=True)
        )
        return
    if not 1 <= args.workers <= MAX_WORKERS:
        raise ValueError("workers outside sealed plan")
    direction = verified_json(HERE / "stage-0-direction.json")
    if direction.get("gate", {}).get("passed") is not True or direction.get("bindings", {}).get(
        "plan"
    ) != digest(PLAN):
        raise ValueError("sealed direction gate required")
    inference, qualification, cells = run_search(direction, args.workers)
    cells_record = {
        "schema": "ds1-iteration28-basin-search-cells/v1",
        "complete": True,
        "truth_used": False,
        "held_used": False,
        "bindings": bindings(),
        "cells": cells,
    }
    write_sealed(HERE / "cells.json", cells_record)
    inference["cells_digest"] = digest(HERE / "cells.json")
    write_sealed(HERE / "inference.json", inference)
    qualification["inference_pending_digest"] = False
    qualification["inference_digest"] = digest(HERE / "inference.json")
    qualification["bindings"] = bindings()
    write_sealed(HERE / "qualification.json", qualification)
    for number, stage in enumerate(inference["stages"], 1):
        write_sealed(
            HERE / f"stage-{number}-{stage['name']}.json",
            {
                "schema": "ds1-iteration28-basin-search-stage/v1",
                "complete": True,
                "truth_used": False,
                "held_used": False,
                "inference_digest": digest(HERE / "inference.json"),
                "stage": stage,
            },
        )
    print(
        json.dumps(
            {
                "qualified": qualification["qualified"],
                "failure_reason": qualification["failure_reason"],
                "cell_count": len(cells),
                "elapsed_s": inference["elapsed_s"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
