#!/usr/bin/env python3
"""Sealed paired DS1/DS3 preflight for exact top-K soft association.

This runner deliberately stops before an all-dataset geographic search.  It
uses only dataset-local RF evidence, evaluates a small coordinate stencil, and
measures candidate ambiguity and deletion influence.  Surveyed coordinates and
HELD observations are neither accepted nor read.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.special import logsumexp

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = HERE / "paired-plan-v2.json"
RESULT = HERE / "preflight-v2.json"
CANDIDATES = HERE / "candidate-table.json"
INFLUENCE = HERE / "influence-table.json"
ATLAS = HERE / "exact-phase-atlas.json"

ORBIT_RUNNER = ROOT / "reports/2026_09_24_ds1_train_full_orbit_soft/run.py"
I27_PLAN = ROOT / "reports/2026_09_25_ds1_iteration27_phase_cache/plan.json"
I27_SMOKE = ROOT / "reports/2026_09_25_ds1_iteration27_phase_cache/smoke.json"
I27_STENCIL = ROOT / "reports/2026_09_25_ds1_iteration27_phase_cache/stencil.json"
DS3_MANIFEST = ROOT / "reports/2026_09_24_ds3_all_captures/inference-manifest.json"
DS3_CACHE = Path("/var/tmp/leo-ds3-sep24-until-223658-cache")
DS3_SINGLE = ROOT / "reports/2026_09_24_ds3_all_captures/output/portable/inference"
SEARCH = ROOT / "reports/2026_09_23_long_training_search/search.py"
EXACT_ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
REPLAY = ROOT / "tools/replay_regional_doppler.py"

FOLDS = 5
BOOTSTRAPS = 256
TEMPERATURE_GRID_HZ = (25.0, 50.0, 100.0, 200.0, 400.0, 800.0, 1600.0)
AMBIGUITY_MARGIN_HZ = 25.0
AMBIGUITY_WIN_PROBABILITY = 0.10
CAP_HZ = 800.0
DS1_SPACING_KM = 0.048828125
DS3_SPACING_KM = 25.0
MAX_WORKERS = 4
STAGE_HARD_WALL_S = 1800
RATE_SIGMA_S_H = 0.09176615913014215
RATE_GRID_S_H = (-0.25, -0.125, -0.0625, -0.03125, 0.0, 0.03125, 0.0625, 0.125, 0.25)
RATE_LIKELIHOOD_SIGMA_HZ = 250.0


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verify_seal(path: Path) -> None:
    expected = digest(path).removeprefix("sha256:")
    sidecars = (path.with_suffix(path.suffix + ".sha256"), path.with_suffix(".sha256"))
    if not any(
        sidecar.is_file()
        and sidecar.read_text().strip().split()[0].removeprefix("sha256:") == expected
        for sidecar in sidecars
    ):
        raise ValueError(f"unsealed input: {path}")


def load_json(path: Path, sealed: bool = True) -> dict[str, Any]:
    if sealed:
        verify_seal(path)
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_sealed(path: Path, value: dict[str, Any]) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if path.exists() or sidecar.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical(value)
    path.write_text(text)
    sidecar.write_text(hashlib.sha256(text.encode()).hexdigest() + "\n")


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def deterministic_folds(session_id: str, track_id: str, count: int) -> np.ndarray:
    """Assign every sample to one of five folds without using sample values."""
    answer = np.empty(count, dtype=np.int8)
    for index in range(count):
        payload = f"iteration31:{session_id}:{track_id}:{index}".encode()
        answer[index] = hashlib.sha256(payload).digest()[0] % FOLDS
    # Very short or unlucky tracks get a deterministic round-robin fallback.
    if len(np.unique(answer)) < min(FOLDS, count):
        answer = np.arange(count, dtype=np.int8) % min(FOLDS, count)
    return answer


def bootstrap_margin(
    fold_mse: np.ndarray, first: int, second: int, seed_text: str
) -> dict[str, float]:
    seed = int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    margins = np.empty(BOOTSTRAPS)
    folds = fold_mse.shape[1]
    for index in range(BOOTSTRAPS):
        chosen = rng.integers(0, folds, folds)
        a = math.sqrt(float(np.mean(fold_mse[first, chosen])))
        b = math.sqrt(float(np.mean(fold_mse[second, chosen])))
        margins[index] = b - a
    return {
        "margin_q10_hz": float(np.quantile(margins, 0.10)),
        "margin_median_hz": float(np.median(margins)),
        "margin_q90_hz": float(np.quantile(margins, 0.90)),
        "runner_win_probability": float(np.mean(margins < 0.0)),
    }


def huber_location(values: np.ndarray) -> float:
    """Deterministic bounded-influence location over equal-weight sessions."""
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        return math.nan
    if len(values) <= 2:
        return float(np.mean(values))
    location = float(np.median(values))
    mad = float(np.median(np.abs(values - location)))
    scale = max(1.4826 * mad, 1e-9)
    cutoff = 1.5 * scale
    for _ in range(20):
        residual = values - location
        weight = np.minimum(1.0, cutoff / np.maximum(np.abs(residual), 1e-15))
        update = float(np.sum(weight * values) / np.sum(weight))
        if abs(update - location) <= 1e-14:
            break
        location = update
    return location


def mixture_loss(candidate_rms_hz: np.ndarray, temperature_hz: float) -> float:
    rms = np.asarray(candidate_rms_hz, dtype=float)
    finite = np.isfinite(rms)
    if not np.any(finite):
        return 1.0
    energy = 0.5 * (rms[finite] / temperature_hz) ** 2
    mixed = -float(logsumexp(-energy) - math.log(len(energy)))
    return min(max(2.0 * temperature_hz**2 * mixed / CAP_HZ**2, 0.0), 1.0)


def _eligible_track_count(cache_root: Path, session_id: str) -> int:
    receipt = load_json(cache_root / session_id / "cache_receipt.json", sealed=False)
    return sum(
        len(track["times_s"]) == len(track["measured_hz"])
        and len(track["times_s"]) >= 2
        and max(track["times_s"]) - min(track["times_s"]) >= 3.0
        for track in receipt["prepared_evidence"]["tracks"]
    )


def _ds3_preflight_session() -> str:
    manifest = load_json(DS3_MANIFEST)
    ranked = sorted(
        (
            -_eligible_track_count(DS3_CACHE, str(row["session_id"])),
            str(row["session_id"]),
        )
        for row in manifest["sessions"]
    )
    if len(ranked) != 56:
        raise ValueError("DS3 preflight selection requires all 56 sealed sessions")
    return ranked[0][1]


def _single_soft_path(session_id: str) -> Path:
    return DS3_SINGLE / f"single__{session_id}__soft-identity.json"


def create_plan() -> None:
    """Seal one paired plan before candidate or preflight outputs exist."""
    if any(path.exists() for path in (RESULT, CANDIDATES, INFLUENCE, ATLAS)):
        raise RuntimeError("refusing to seal plan after outputs exist")
    i27 = load_json(I27_PLAN)
    smoke = load_json(I27_SMOKE)
    ds3_session = _ds3_preflight_session()
    ds3_parent = load_json(_single_soft_path(ds3_session))
    if ds3_parent.get("reference_used_for_fit") is not False:
        raise ValueError("DS3 anchor parent is not reference-free")
    ds1_sessions = {
        group["group_id"]: [row["session_id"] for row in group["session_bindings"]]
        for group in smoke["groups"]
    }
    plan = {
        "schema": "paired-ds1-ds3-iteration31-exact-soft-preflight-plan/v1",
        "status": "sealed-before-output",
        "truth_used": False,
        "held_used": False,
        "full_geographic_search_authorized": False,
        "method": {
            "name": "exact_top_k_soft_association_with_causal_crossfit_rates",
            "candidate_generation": (
                "independent dataset-local all-sky causal catalogue at RF anchor"
            ),
            "folds": FOLDS,
            "fold_assignment": "sha256(dataset session, track, sample index) modulo five",
            "exact_phase_states": {
                "state": "receipt-bound causal SGP4 state at every retained candidate/rate node",
                "rate_grid_s_h": list(RATE_GRID_S_H),
                "earth_rotation": "fixed at receive_time_plus_group_tau while orbit phase changes",
                "state_interpolation": "none: rate likelihood is discrete over exact nodes",
            },
            "causal_rate_posterior": {
                "fit": (
                    "candidate-specific per-source discrete posterior on each fold's "
                    "other four folds"
                ),
                "rate_prior": f"N(0,{RATE_SIGMA_S_H} s/h)",
                "measurement_scale_hz": RATE_LIKELIHOOD_SIGMA_HZ,
                "evaluation": "fold-local CFO and rate posterior score only the omitted TRAIN fold",
            },
            "bootstrap_replicates": BOOTSTRAPS,
            "candidate_policy": {
                "stable": "retain leader only",
                "ambiguous": "retain top two; retain top three only when third also passes",
                "certification": (
                    "randomized TRAIN within-track bootstrap q10 margin <=25 Hz "
                    "or challenger win probability >=0.10"
                ),
            },
            "temperature_hz_grid": list(TEMPERATURE_GRID_HZ),
            "temperature_selection": (
                "minimum occupied-second weighted five-fold TRAIN predictive mixture NLL; "
                "tie chooses lower temperature; endpoints are a no-go"
            ),
            "track_score": "continuous equal-prior log-sum-exp over retained candidates",
            "aggregate": (
                "occupied-second mean within session; 1.5-MAD Huber location across "
                "equal sessions within group; frozen iteration27 DS1 group weights"
            ),
            "cap_hz": CAP_HZ,
        },
        "datasets": {
            "DS1": {
                "anchor": i27["anchor"],
                "sessions_by_group": ds1_sessions,
                "cache_roots": {
                    "20260921_00": "/tmp/leo-long-training-cache-full8h",
                    "20260921_16": "/tmp/leo-long-training-cache-second8h",
                },
                "coordinate_stencil": {
                    "east_km": [-DS1_SPACING_KM, 0.0, DS1_SPACING_KM],
                    "north_km": [-DS1_SPACING_KM, 0.0, DS1_SPACING_KM],
                },
                "required_source_table_entry": "66961",
            },
            "DS3": {
                "manifest": str(DS3_MANIFEST),
                "session_selection": "maximum eligible >=3-second track count; lexical tie-break",
                "session_id": ds3_session,
                "session_count_in_preflight": 1,
                "cache_root": str(DS3_CACHE),
                "anchor": {
                    "latitude_deg": ds3_parent["estimated_position"]["latitude_deg"],
                    "longitude_deg": ds3_parent["estimated_position"]["longitude_deg"],
                    "tau_s": ds3_parent["global_tau_s"],
                },
                "coordinate_stencil": {
                    "east_km": [-DS3_SPACING_KM, 0.0, DS3_SPACING_KM],
                    "north_km": [-DS3_SPACING_KM, 0.0, DS3_SPACING_KM],
                },
                "all56_search": "prohibited until both paired preflights pass",
            },
        },
        "gates": {
            "candidate_table_complete": True,
            "ds1_source_66961_present": True,
            "finite_coordinate_scores": True,
            "repeat_max_abs_score_difference": 1e-12,
            "ds1_leave_one_session_winner_agreement_min": 0.75,
            "leave_one_source_winner_agreement_min": 0.90,
            "temperature_must_be_interior": True,
            "source_influence": {
                "winner_agreement_min": 0.90,
                "maximum_normalized_surface_deformation": 1.0,
                "normalization": (
                    "full-stencil score range; compare source-deleted relative cell gaps "
                    "to full relative cell gaps"
                ),
                "reason": (
                    "location-relevant deformation is dimensionless and does not conflate "
                    "raw objective scale across DS1 and DS3"
                ),
            },
            "full_search": "both DS1 and DS3 gates must pass; this runner never launches it",
        },
        "execution": {
            "maximum_workers": MAX_WORKERS,
            "workers_used": 1,
            "single_thread_math": True,
            "stage_hard_wall_s": STAGE_HARD_WALL_S,
            "external_timeout_required": True,
        },
        "bindings": {
            "runner": digest(Path(__file__)),
            "orbit_runner": digest(ORBIT_RUNNER),
            "exact_orbit": digest(EXACT_ORBIT),
            "replay": digest(REPLAY),
            "search": digest(SEARCH),
            "iteration27_plan": digest(I27_PLAN),
            "iteration27_smoke": digest(I27_SMOKE),
            "iteration27_stencil": digest(I27_STENCIL),
            "ds3_manifest": digest(DS3_MANIFEST),
            "ds3_anchor_parent": digest(_single_soft_path(ds3_session)),
        },
    }
    write_sealed(PLAN, plan)


def validate_plan(plan: dict[str, Any]) -> None:
    if (
        plan.get("schema") != "paired-ds1-ds3-iteration31-exact-soft-preflight-plan/v1"
        or plan.get("status") != "sealed-before-output"
        or plan.get("truth_used") is not False
        or plan.get("held_used") is not False
        or plan.get("full_geographic_search_authorized") is not False
        or plan.get("execution", {}).get("maximum_workers") > MAX_WORKERS
    ):
        raise ValueError("invalid paired preflight plan")
    expected = {
        "runner": Path(__file__),
        "orbit_runner": ORBIT_RUNNER,
        "exact_orbit": EXACT_ORBIT,
        "replay": REPLAY,
        "search": SEARCH,
        "iteration27_plan": I27_PLAN,
        "iteration27_smoke": I27_SMOKE,
        "iteration27_stencil": I27_STENCIL,
        "ds3_manifest": DS3_MANIFEST,
        "ds3_anchor_parent": _single_soft_path(plan["datasets"]["DS3"]["session_id"]),
    }
    for name, path in expected.items():
        if plan["bindings"].get(name) != digest(path):
            raise ValueError(f"plan binding changed: {name}")


def make_engine(module: Any, spec: dict[str, Any], dataset: str) -> Any:
    if dataset == "DS1":
        session_ids = [sid for group in spec["sessions_by_group"].values() for sid in group]
        groups = {sid: group for group, ids in spec["sessions_by_group"].items() for sid in ids}
        options = {"cache_roots": spec["cache_roots"]}
    else:
        session_ids = [spec["session_id"]]
        groups = {spec["session_id"]: "ds3"}
        options = {"cache_root": spec["cache_root"]}
        module.CACHE_ROOTS["ds3"] = Path(spec["cache_root"])
    task = {
        "session_ids": session_ids,
        "session_groups": groups,
        "options": options,
    }
    return module.FullObservationEngine(task)


def _anchor(spec: dict[str, Any], dataset: str, group: str) -> tuple[float, float, float]:
    anchor = spec["anchor"]
    tau = anchor["group_tau_s"][group] if dataset == "DS1" else anchor["tau_s"]
    return float(anchor["latitude_deg"]), float(anchor["longitude_deg"]), float(tau)


def generate_candidates(
    engine: Any, spec: dict[str, Any], dataset: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate top-three OOF candidate evidence independently per dataset."""
    rows: list[dict[str, Any]] = []
    temperature_nll = {value: 0.0 for value in TEMPERATURE_GRID_HZ}
    temperature_weight = 0.0
    for session in engine.sessions:
        group = next(
            (
                g
                for g, ids in spec.get("sessions_by_group", {}).items()
                if session.session_id in ids
            ),
            "ds3",
        )
        lat, lon, tau = _anchor(spec, dataset, group)
        for track in session.tracks:
            prediction, visible = engine.predictions(session, track, lat, lon, tau)
            residual = track.measured[None, :] - prediction
            folds = deterministic_folds(session.session_id, track.track_id, len(track.times))
            fold_mse = np.full((len(session.candidate_id), FOLDS), np.inf)
            for fold in range(FOLDS):
                validation = folds == fold
                training = ~validation
                if not np.any(validation) or not np.any(training):
                    continue
                cfo = np.mean(residual[:, training], axis=1)
                fold_mse[:, fold] = np.mean((residual[:, validation] - cfo[:, None]) ** 2, axis=1)
            fold_mse[~visible, :] = np.inf
            mean_mse = np.mean(fold_mse, axis=1)
            ordered = np.argsort(mean_mse)[:3]
            finite = ordered[np.isfinite(mean_mse[ordered])]
            if len(finite) == 0:
                rows.append(
                    {
                        "dataset": dataset,
                        "group_id": group,
                        "session_id": session.session_id,
                        "track_id": track.track_id,
                        "weight_s": int(track.weight),
                        "retained_k": 0,
                        "ambiguous": False,
                        "candidates": [],
                    }
                )
                continue
            first = int(finite[0])
            diagnostics = []
            retained = 1
            for challenger_rank, challenger in enumerate(finite[1:], start=2):
                margin = bootstrap_margin(
                    fold_mse,
                    first,
                    int(challenger),
                    f"{dataset}:{session.session_id}:{track.track_id}:{challenger_rank}",
                )
                certified = (
                    margin["margin_q10_hz"] <= AMBIGUITY_MARGIN_HZ
                    or margin["runner_win_probability"] >= AMBIGUITY_WIN_PROBABILITY
                )
                diagnostics.append({**margin, "ambiguity_certified": bool(certified)})
                if certified and challenger_rank == retained + 1:
                    retained = challenger_rank
                else:
                    break
            candidate_rows = []
            for rank, candidate in enumerate(finite, start=1):
                candidate_rows.append(
                    {
                        "rank": rank,
                        "candidate_id": str(session.candidate_id[candidate]),
                        "oof_rms_hz": float(math.sqrt(mean_mse[candidate])),
                        "retained": rank <= retained,
                        "challenger_diagnostic": diagnostics[rank - 2]
                        if rank >= 2 and rank - 2 < len(diagnostics)
                        else None,
                    }
                )
            retained_indices = np.asarray(finite[:retained], dtype=int)
            for temperature in TEMPERATURE_GRID_HZ:
                for fold in range(FOLDS):
                    energy = 0.5 * fold_mse[retained_indices, fold] / temperature**2
                    value = -float(logsumexp(-energy) - math.log(len(energy))) + math.log(
                        temperature
                    )
                    temperature_nll[temperature] += track.weight * value / FOLDS
            temperature_weight += track.weight
            rows.append(
                {
                    "dataset": dataset,
                    "group_id": group,
                    "session_id": session.session_id,
                    "track_id": track.track_id,
                    "weight_s": int(track.weight),
                    "retained_k": retained,
                    "ambiguous": retained > 1,
                    "candidates": candidate_rows,
                }
            )
    normalized_nll = {
        str(key): float(value / max(temperature_weight, 1.0))
        for key, value in temperature_nll.items()
    }
    selected = min(TEMPERATURE_GRID_HZ, key=lambda value: (temperature_nll[value], value))
    entropies = []
    for row in rows:
        retained_rows = [candidate for candidate in row["candidates"] if candidate["retained"]]
        if not retained_rows:
            row["posterior_entropy_nats"] = None
            continue
        energy = np.asarray(
            [0.5 * (candidate["oof_rms_hz"] / selected) ** 2 for candidate in retained_rows]
        )
        posterior = np.exp(-energy - logsumexp(-energy))
        for candidate, probability in zip(retained_rows, posterior, strict=True):
            candidate["posterior"] = float(probability)
        entropy = -float(np.sum(posterior * np.log(np.maximum(posterior, 1e-300))))
        row["posterior_entropy_nats"] = entropy
        entropies.append(entropy)
    summary = {
        "temperature_hz": selected,
        "temperature_predictive_nll": normalized_nll,
        "tracks": len(rows),
        "unsupported_tracks": sum(row["retained_k"] == 0 for row in rows),
        "ambiguous_tracks": sum(row["ambiguous"] for row in rows),
        "top2_tracks": sum(row["retained_k"] == 2 for row in rows),
        "top3_tracks": sum(row["retained_k"] == 3 for row in rows),
        "mean_posterior_entropy_nats": float(np.mean(entropies)) if entropies else None,
        "maximum_posterior_entropy_nats": max(entropies, default=None),
    }
    return rows, summary


def _atlas_key(session_id: str, track_id: str, candidate_id: str) -> str:
    return f"{session_id}|{track_id}|{candidate_id}"


def build_exact_phase_atlas(
    engine: Any, spec: dict[str, Any], dataset: str, proposals: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Propagate only proposal candidates at every discrete causal-rate node.

    Each stored state is an exact receipt-bound SGP4 propagation.  There is no
    interpolation in rate or orbit phase; later scoring is a finite mixture on
    these exact nodes.  This is deliberately bounded to the independently
    generated top-three proposal table.
    """
    orbit = load_module(EXACT_ORBIT, f"iteration31_exact_orbit_{dataset}")
    replay = load_module(REPLAY, f"iteration31_replay_{dataset}")
    from leo.sky.propagation import parse_element_sets

    proposed = {(r["session_id"], r["track_id"]): r for r in proposals}
    atlas: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    for session in engine.sessions:
        group = next(
            (
                g
                for g, ids in spec.get("sessions_by_group", {}).items()
                if session.session_id in ids
            ),
            "ds3",
        )
        _lat, _lon, tau = _anchor(spec, dataset, group)
        receipt = load_json(session.cache_path / "cache_receipt.json", sealed=False)
        evidence = receipt["prepared_evidence"]
        payload = orbit.archive_payload(evidence["snapshot_digest"])
        catalogue = parse_element_sets(payload.decode("ascii"))
        candidate_index = {
            str(value): index for index, value in enumerate(catalogue.satellite_numbers)
        }
        epoch_ns = dict(
            zip(
                map(str, catalogue.satellite_numbers), catalogue.element_epoch_utc_ns(), strict=True
            )
        )
        grouped: dict[str, list[Any]] = {}
        for track in session.tracks:
            row = proposed[(session.session_id, track.track_id)]
            for candidate in row["candidates"]:
                grouped.setdefault(str(candidate["candidate_id"]), []).append(track)
        for candidate_id, tracks in sorted(grouped.items()):
            if candidate_id not in candidate_index or candidate_id not in epoch_ns:
                raise ValueError(f"candidate absent from receipt-bound snapshot: {candidate_id}")
            age_h = (int(evidence["start_utc_ns"]) - int(epoch_ns[candidate_id])) / 3.6e12
            if not math.isfinite(age_h) or age_h < 0.0:
                raise ValueError(f"invalid causal age for {session.session_id}:{candidate_id}")
            times = np.concatenate([track.times for track in tracks])
            states_p = np.empty((len(RATE_GRID_S_H), len(times), 3), dtype=float)
            states_v = np.empty_like(states_p)
            for rate_index, rate in enumerate(RATE_GRID_S_H):
                p, v, valid = replay.state_arrays(
                    catalogue,
                    [candidate_index[candidate_id]],
                    int(evidence["start_utc_ns"]),
                    times,
                    orbit_time_s=float(rate * age_h),
                    clock_s=float(tau),
                )
                if len(valid) != 1:
                    raise ValueError("exact phase state propagation failed")
                states_p[rate_index], states_v[rate_index] = p[0], v[0]
            offset = 0
            for track in tracks:
                end = offset + len(track.times)
                key = _atlas_key(session.session_id, track.track_id, candidate_id)
                atlas[key] = {
                    "position": states_p[:, offset:end],
                    "velocity": states_v[:, offset:end],
                    "age_h": age_h,
                    "tau_s": tau,
                }
                offset = end
            records.append(
                {
                    "dataset": dataset,
                    "session_id": session.session_id,
                    "candidate_id": candidate_id,
                    "track_count": len(tracks),
                    "observation_count": int(len(times)),
                    "causal_tle_age_h": float(age_h),
                    "rate_grid_s_h": list(RATE_GRID_S_H),
                    "position_digest": "sha256:" + hashlib.sha256(states_p.tobytes()).hexdigest(),
                    "velocity_digest": "sha256:" + hashlib.sha256(states_v.tobytes()).hexdigest(),
                    "receipt": digest(session.cache_path / "cache_receipt.json"),
                }
            )
    return atlas, records


def exact_predictions(
    engine: Any, atlas_row: dict[str, Any], latitude_deg: float, longitude_deg: float
) -> np.ndarray:
    receiver, _up = engine.search.receiver_ecef(latitude_deg, longitude_deg)
    delta = atlas_row["position"] - receiver
    return (
        -engine.search.REFERENCE_RF_HZ
        / engine.search.LIGHT_KM_S
        * np.sum(delta * atlas_row["velocity"], axis=-1)
        / np.linalg.norm(delta, axis=-1)
    )


def _rate_posteriors(
    engine: Any,
    rows: list[dict[str, Any]],
    atlas: dict[str, dict[str, Any]],
    latitude_deg: float,
    longitude_deg: float,
) -> dict[tuple[str, int], np.ndarray]:
    """Causal source-rate posteriors, cross-fitted by deterministic TRAIN fold."""
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for row in rows:
        for candidate in row["candidates"]:
            key = _atlas_key(row["session_id"], row["track_id"], str(candidate["candidate_id"]))
            if key not in atlas:
                raise ValueError(f"exact state absent: {key}")
            grouped.setdefault(str(candidate["candidate_id"]), []).append((row, atlas[key]))
    output: dict[tuple[str, int], np.ndarray] = {}
    rates = np.asarray(RATE_GRID_S_H)
    for source, items in grouped.items():
        for fold in range(FOLDS):
            energy = 0.5 * (rates / RATE_SIGMA_S_H) ** 2
            for row, state in items:
                predictions = exact_predictions(engine, state, latitude_deg, longitude_deg)
                folds = deterministic_folds(row["session_id"], row["track_id"], len(row["times_s"]))
                train = folds != fold
                residual = np.asarray(row["measured_hz"])[None, :] - predictions
                cfo = np.mean(residual[:, train], axis=1)
                error = residual[:, train] - cfo[:, None]
                energy += np.sum(error * error, axis=1) / (2.0 * RATE_LIKELIHOOD_SIGMA_HZ**2)
            output[(source, fold)] = np.exp(-energy - logsumexp(-energy))
    return output


def _candidate_fold_mse(
    engine: Any,
    row: dict[str, Any],
    candidate_id: str,
    atlas: dict[str, dict[str, Any]],
    latitude_deg: float,
    longitude_deg: float,
    posteriors: dict[tuple[str, int], np.ndarray],
) -> tuple[np.ndarray, list[float]]:
    state = atlas[_atlas_key(row["session_id"], row["track_id"], candidate_id)]
    prediction = exact_predictions(engine, state, latitude_deg, longitude_deg)
    measured = np.asarray(row["measured_hz"])
    folds = deterministic_folds(row["session_id"], row["track_id"], len(measured))
    values = np.full(FOLDS, np.inf)
    rate_mean: list[float] = []
    for fold in range(FOLDS):
        train, validation = folds != fold, folds == fold
        residual = measured[None, :] - prediction
        cfo = np.mean(residual[:, train], axis=1)
        mse = np.mean((residual[:, validation] - cfo[:, None]) ** 2, axis=1)
        posterior = posteriors[(candidate_id, fold)]
        values[fold] = float(posterior @ mse)
        rate_mean.append(float(posterior @ np.asarray(RATE_GRID_S_H)))
    return values, rate_mean


def exact_candidate_table(
    engine: Any,
    spec: dict[str, Any],
    dataset: str,
    proposals: list[dict[str, Any]],
    atlas: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Re-rank proposal support with exact SGP4 state nodes and OOF rate fits."""
    rows = []
    temperature_nll = {value: 0.0 for value in TEMPERATURE_GRID_HZ}
    weight_total = 0.0
    anchor = spec["anchor"]
    lat, lon = float(anchor["latitude_deg"]), float(anchor["longitude_deg"])
    evidence_rows = []
    for proposal in proposals:
        evidence_rows.append(
            {
                **proposal,
                "times_s": next(
                    t.times.tolist()
                    for s in engine.sessions
                    if s.session_id == proposal["session_id"]
                    for t in s.tracks
                    if t.track_id == proposal["track_id"]
                ),
                "measured_hz": next(
                    t.measured.tolist()
                    for s in engine.sessions
                    if s.session_id == proposal["session_id"]
                    for t in s.tracks
                    if t.track_id == proposal["track_id"]
                ),
            }
        )
    posteriors = _rate_posteriors(engine, evidence_rows, atlas, lat, lon)
    for row in evidence_rows:
        candidate_values = []
        for candidate in row["candidates"]:
            cid = str(candidate["candidate_id"])
            fold_mse, rates = _candidate_fold_mse(engine, row, cid, atlas, lat, lon, posteriors)
            candidate_values.append((cid, fold_mse, rates))
        ordered = sorted(candidate_values, key=lambda item: (float(np.mean(item[1])), item[0]))
        if not ordered:
            rows.append({k: v for k, v in row.items() if k not in {"times_s", "measured_hz"}})
            continue
        retained = 1
        diagnostics = []
        for rank, item in enumerate(ordered[1:], start=2):
            margin = bootstrap_margin(
                np.asarray([ordered[0][1], item[1]]),
                0,
                1,
                f"iteration31:{dataset}:{row['session_id']}:{row['track_id']}:{rank}",
            )
            certified = (
                margin["margin_q10_hz"] <= AMBIGUITY_MARGIN_HZ
                or margin["runner_win_probability"] >= AMBIGUITY_WIN_PROBABILITY
            )
            diagnostics.append({**margin, "ambiguity_certified": bool(certified)})
            if certified and rank == retained + 1:
                retained = rank
            else:
                break
        candidates = []
        for rank, (cid, fold_mse, rate_means) in enumerate(ordered, start=1):
            candidates.append(
                {
                    "rank": rank,
                    "candidate_id": cid,
                    "oof_rms_hz": float(math.sqrt(np.mean(fold_mse))),
                    "retained": rank <= retained,
                    "fold_mse_hz2": [float(value) for value in fold_mse],
                    "crossfit_rate_posterior_mean_s_h": rate_means,
                    "challenger_diagnostic": diagnostics[rank - 2]
                    if rank >= 2 and rank - 2 < len(diagnostics)
                    else None,
                }
            )
        kept = np.asarray([item[1] for item in ordered[:retained]])
        for temp in TEMPERATURE_GRID_HZ:
            for fold in range(FOLDS):
                energy = 0.5 * kept[:, fold] / temp**2
                temperature_nll[temp] += (
                    row["weight_s"]
                    * (-float(logsumexp(-energy) - math.log(len(energy))) + math.log(temp))
                    / FOLDS
                )
        weight_total += row["weight_s"]
        output = {
            k: v
            for k, v in row.items()
            if k
            not in {
                "times_s",
                "measured_hz",
                "candidates",
                "retained_k",
                "ambiguous",
                "posterior_entropy_nats",
            }
        }
        output.update({"retained_k": retained, "ambiguous": retained > 1, "candidates": candidates})
        rows.append(output)
    nll = {str(t): float(value / max(weight_total, 1.0)) for t, value in temperature_nll.items()}
    selected = min(TEMPERATURE_GRID_HZ, key=lambda t: (temperature_nll[t], t))
    for row in rows:
        kept = [c for c in row["candidates"] if c["retained"]]
        if not kept:
            row["posterior_entropy_nats"] = None
            continue
        energy = np.asarray([0.5 * (c["oof_rms_hz"] / selected) ** 2 for c in kept])
        posterior = np.exp(-energy - logsumexp(-energy))
        for candidate, probability in zip(kept, posterior, strict=True):
            candidate["posterior"] = float(probability)
        row["posterior_entropy_nats"] = -float(
            np.sum(posterior * np.log(np.maximum(posterior, 1e-300)))
        )
    return rows, {
        "temperature_hz": selected,
        "temperature_predictive_nll": nll,
        "temperature_interior": selected not in {TEMPERATURE_GRID_HZ[0], TEMPERATURE_GRID_HZ[-1]},
        "tracks": len(rows),
        "ambiguous_tracks": sum(row["ambiguous"] for row in rows),
        "top2_tracks": sum(row["retained_k"] == 2 for row in rows),
        "top3_tracks": sum(row["retained_k"] == 3 for row in rows),
    }


def _selected_rms(
    engine: Any,
    session: Any,
    track: Any,
    candidate_ids: list[str],
    lat: float,
    lon: float,
    tau: float,
) -> np.ndarray:
    indices = []
    lookup = {str(value): index for index, value in enumerate(session.candidate_id)}
    for value in candidate_ids:
        if value not in lookup:
            raise ValueError(f"fixed candidate absent from dataset-local cache: {value}")
        indices.append(lookup[value])
    query = track.times + tau
    grid = session.grid
    if query.min() < grid[0] or query.max() > grid[-1]:
        raise ValueError("coordinate preflight query outside causal cache")
    step = grid[1] - grid[0]
    position = (query - grid[0]) / step
    low = np.floor(position).astype(int)
    high = np.minimum(low + 1, len(grid) - 1)
    fraction = position - low
    idx = np.asarray(indices, dtype=int)
    p = session.position[idx][:, low, :] * (1.0 - fraction)[None, :, None]
    p += session.position[idx][:, high, :] * fraction[None, :, None]
    v = session.velocity[idx][:, low, :] * (1.0 - fraction)[None, :, None]
    v += session.velocity[idx][:, high, :] * fraction[None, :, None]
    receiver, up = engine.search.receiver_ecef(lat, lon)
    delta = p - receiver
    distance = np.linalg.norm(delta, axis=-1)
    predicted = (
        -engine.search.REFERENCE_RF_HZ
        / engine.search.LIGHT_KM_S
        * np.sum(delta * v, axis=-1)
        / distance
    )
    visible = np.max(np.sum(delta * up, axis=-1) / distance, axis=1) >= 0.0
    residual = track.measured[None, :] - predicted
    cfo = np.mean(residual, axis=1)
    rms = np.sqrt(np.mean((residual - cfo[:, None]) ** 2, axis=1))
    return np.where(visible, rms, np.inf)


def _aggregate(
    rows: list[dict[str, Any]],
    dataset: str,
    spec: dict[str, Any],
    omit_session: str | None = None,
    omit_source: str | None = None,
) -> float:
    selected = [
        row
        for row in rows
        if row["session_id"] != omit_session and row["leader_source"] != omit_source
    ]
    if not selected:
        return math.nan
    sessions: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in selected:
        sessions.setdefault((row["group_id"], row["session_id"]), []).append(row)
    session_scores: dict[str, list[float]] = {}
    for (group, _session), tracks in sessions.items():
        denominator = sum(track["weight_s"] for track in tracks)
        value = sum(track["weight_s"] * track["loss"] for track in tracks) / denominator
        session_scores.setdefault(group, []).append(value)
    group_scores = {
        group: huber_location(np.asarray(values)) for group, values in session_scores.items()
    }
    if dataset == "DS1":
        weights = spec["anchor"]["group_weights"]
        denominator = sum(float(weights[group]) for group in group_scores)
        return float(
            sum(float(weights[group]) * value for group, value in group_scores.items())
            / denominator
        )
    return huber_location(np.asarray(list(group_scores.values())))


def attach_evidence(engine: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tracks = {
        (session.session_id, track.track_id): track
        for session in engine.sessions
        for track in session.tracks
    }
    output = []
    for row in rows:
        track = tracks[(row["session_id"], row["track_id"])]
        output.append(
            {**row, "times_s": track.times.tolist(), "measured_hz": track.measured.tolist()}
        )
    return output


def score_stencil(
    engine: Any,
    spec: dict[str, Any],
    dataset: str,
    candidates: list[dict[str, Any]],
    atlas: dict[str, dict[str, Any]],
    temperature: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_rows = attach_evidence(engine, candidates)
    by_track = {(row["session_id"], row["track_id"]): row for row in evidence_rows}
    cells = []
    track_cells = []
    anchor = spec["anchor"]
    for east in spec["coordinate_stencil"]["east_km"]:
        for north in spec["coordinate_stencil"]["north_km"]:
            lat, lon = engine.search.offset_coordinate(
                (float(anchor["latitude_deg"]), float(anchor["longitude_deg"])), east, north
            )
            posteriors = _rate_posteriors(engine, evidence_rows, atlas, lat, lon)
            rows = []
            for session in engine.sessions:
                group = next(
                    (
                        value
                        for value, ids in spec.get("sessions_by_group", {}).items()
                        if session.session_id in ids
                    ),
                    "ds3",
                )
                _alat, _alon, tau = _anchor(spec, dataset, group)
                for track in session.tracks:
                    item = by_track[(session.session_id, track.track_id)]
                    ids = [row["candidate_id"] for row in item["candidates"] if row["retained"]]
                    if ids:
                        rms = np.asarray(
                            [
                                math.sqrt(
                                    float(
                                        np.mean(
                                            _candidate_fold_mse(
                                                engine,
                                                item,
                                                candidate_id,
                                                atlas,
                                                lat,
                                                lon,
                                                posteriors,
                                            )[0]
                                        )
                                    )
                                )
                                for candidate_id in ids
                            ]
                        )
                        loss = mixture_loss(rms, temperature)
                    else:
                        rms = np.asarray([], dtype=float)
                        loss = 1.0
                    row = {
                        "cell_id": f"E{east:+.9f}_N{north:+.9f}",
                        "east_km": east,
                        "north_km": north,
                        "group_id": group,
                        "session_id": session.session_id,
                        "track_id": track.track_id,
                        "leader_source": ids[0] if ids else None,
                        "retained_k": len(ids),
                        "candidate_rms_hz": [float(value) for value in rms],
                        "weight_s": int(track.weight),
                        "loss": loss,
                    }
                    rows.append(row)
                    track_cells.append(row)
            cells.append(
                {
                    "cell_id": f"E{east:+.9f}_N{north:+.9f}",
                    "east_km": east,
                    "north_km": north,
                    "latitude_deg": lat,
                    "longitude_deg": lon,
                    "score": _aggregate(rows, dataset, spec),
                }
            )
    return cells, track_cells


def winner(cells: list[dict[str, Any]], scores: dict[str, float] | None = None) -> str:
    if scores is None:
        scores = {row["cell_id"]: row["score"] for row in cells}
    finite = [(value, key) for key, value in scores.items() if math.isfinite(value)]
    if not finite:
        return "none"
    return min(finite)[1]


def influence_table(
    cells: list[dict[str, Any]],
    track_cells: list[dict[str, Any]],
    dataset: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    full = winner(cells)
    cell_rows = {cell["cell_id"]: [] for cell in cells}
    for row in track_cells:
        cell_rows[row["cell_id"]].append(row)
    sessions = sorted({row["session_id"] for row in track_cells})
    sources = sorted({row["leader_source"] for row in track_cells if row["leader_source"]})
    session_rows = []
    if len(sessions) > 1:
        for session in sessions:
            scores = {
                cell: _aggregate(rows, dataset, spec, omit_session=session)
                for cell, rows in cell_rows.items()
            }
            session_rows.append(
                {
                    "session_id": session,
                    "winner_cell_id": winner(cells, scores),
                    "winner_agrees": winner(cells, scores) == full,
                    "scores": scores,
                }
            )
    source_rows = []
    full_scores = {row["cell_id"]: row["score"] for row in cells}
    full_winner_score = full_scores[full]
    full_range = max(full_scores.values()) - min(full_scores.values())
    for source in sources:
        scores = {
            cell: _aggregate(rows, dataset, spec, omit_source=source)
            for cell, rows in cell_rows.items()
        }
        finite_shifts = [
            abs(scores[cell] - full_scores[cell])
            for cell in scores
            if math.isfinite(scores[cell]) and math.isfinite(full_scores[cell])
        ]
        relative_deformation = [
            abs((scores[cell] - scores[full]) - (full_scores[cell] - full_winner_score))
            for cell in scores
            if math.isfinite(scores[cell]) and math.isfinite(scores[full])
        ]
        source_rows.append(
            {
                "source": source,
                "winner_cell_id": winner(cells, scores),
                "winner_agrees": winner(cells, scores) == full,
                "maximum_absolute_score_shift": max(finite_shifts, default=math.inf),
                "maximum_relative_surface_deformation": max(relative_deformation, default=math.inf),
                "normalized_surface_deformation": (
                    max(relative_deformation, default=math.inf) / max(full_range, 1e-12)
                ),
                "scores": scores,
            }
        )
    return {
        "full_winner_cell_id": full,
        "leave_one_session": session_rows,
        "leave_one_source": source_rows,
        "leave_one_session_winner_agreement": (
            float(np.mean([row["winner_agrees"] for row in session_rows])) if session_rows else None
        ),
        "leave_one_source_winner_agreement": (
            float(np.mean([row["winner_agrees"] for row in source_rows])) if source_rows else None
        ),
        "maximum_single_source_score_shift": max(
            (row["maximum_absolute_score_shift"] for row in source_rows), default=math.inf
        ),
        "full_stencil_score_range": float(full_range),
        "maximum_normalized_surface_deformation": max(
            (row["normalized_surface_deformation"] for row in source_rows), default=math.inf
        ),
    }


def dataset_run(
    module: Any, plan: dict[str, Any], dataset: str
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    started = time.monotonic()
    spec = plan["datasets"][dataset]
    engine = make_engine(module, spec, dataset)
    proposals, proposal_summary = generate_candidates(engine, spec, dataset)
    atlas, atlas_records = build_exact_phase_atlas(engine, spec, dataset, proposals)
    candidates, candidate_summary = exact_candidate_table(engine, spec, dataset, proposals, atlas)
    candidate_elapsed = time.monotonic() - started
    score_started = time.monotonic()
    cells, track_cells = score_stencil(
        engine, spec, dataset, candidates, atlas, candidate_summary["temperature_hz"]
    )
    first_scores = np.asarray([row["score"] for row in cells])
    repeat_cells, _repeat_tracks = score_stencil(
        engine, spec, dataset, candidates, atlas, candidate_summary["temperature_hz"]
    )
    repeat_scores = np.asarray([row["score"] for row in repeat_cells])
    repeat_error = float(np.max(np.abs(first_scores - repeat_scores)))
    influence = influence_table(cells, track_cells, dataset, spec)
    gates = plan["gates"]
    source_66961 = [
        row
        for row in candidates
        if any(candidate["candidate_id"] == "66961" for candidate in row["candidates"])
    ]
    session_agreement = influence["leave_one_session_winner_agreement"]
    if dataset == "DS3" and len(engine.sessions) == 1:
        # Removing the only session is undefined and is reported, not faked.
        session_gate = True
        session_gate_note = "not_applicable_one_session_preflight"
    else:
        session_gate = bool(
            session_agreement >= gates["ds1_leave_one_session_winner_agreement_min"]
        )
        session_gate_note = "evaluated"
    criteria = {
        "candidate_table_complete": len(candidates)
        == sum(len(session.tracks) for session in engine.sessions),
        "required_ds1_source_66961_present": dataset != "DS1" or bool(source_66961),
        "finite_coordinate_scores": bool(np.all(np.isfinite(first_scores))),
        "repeat_score": repeat_error <= gates["repeat_max_abs_score_difference"],
        "leave_one_session_stability": session_gate,
        "temperature_interior": (
            not gates["temperature_must_be_interior"] or candidate_summary["temperature_interior"]
        ),
        "leave_one_source_stability": influence["leave_one_source_winner_agreement"]
        >= gates["source_influence"]["winner_agreement_min"],
        "scale_aware_source_influence": influence["maximum_normalized_surface_deformation"]
        <= gates["source_influence"]["maximum_normalized_surface_deformation"],
        "stage_hard_wall": time.monotonic() - started <= STAGE_HARD_WALL_S,
    }
    result = {
        "dataset": dataset,
        "preflight_passed": all(criteria.values()),
        "criteria": criteria,
        "session_gate_note": session_gate_note,
        "session_ids": [session.session_id for session in engine.sessions],
        "candidate_summary": candidate_summary,
        "nominal_proposal_summary": proposal_summary,
        "exact_phase_state_records": len(atlas_records),
        "cache_bindings": engine.bindings,
        "source_66961_entries": source_66961,
        "cells": cells,
        "influence_summary": {
            key: value
            for key, value in influence.items()
            if key not in {"leave_one_session", "leave_one_source"}
        },
        "repeat_max_abs_score_difference": repeat_error,
        "runtime_s": {
            "candidate_generation": candidate_elapsed,
            "coordinate_scoring_repeat_and_influence": time.monotonic() - score_started,
            "total": time.monotonic() - started,
        },
        "full_geographic_search_run": False,
        "truth_used": False,
        "held_used": False,
    }
    return result, candidates, influence, atlas_records


def run() -> None:
    plan = load_json(PLAN)
    validate_plan(plan)
    if any(path.exists() for path in (RESULT, CANDIDATES, INFLUENCE, ATLAS)):
        raise FileExistsError("preflight outputs already exist")
    module = load_module(ORBIT_RUNNER, "iteration31_orbit_runner")
    started = time.monotonic()
    results = {}
    candidate_tables = {}
    influence_tables = {}
    atlas_records = {}
    for dataset in ("DS1", "DS3"):
        result, candidates, influence, records = dataset_run(module, plan, dataset)
        results[dataset] = result
        candidate_tables[dataset] = candidates
        influence_tables[dataset] = influence
        atlas_records[dataset] = records
    candidate_artifact = {
        "schema": "paired-ds1-ds3-iteration31-exact-candidates/v1",
        "plan": digest(PLAN),
        "truth_used": False,
        "held_used": False,
        "datasets": candidate_tables,
    }
    influence_artifact = {
        "schema": "paired-ds1-ds3-iteration31-scale-aware-influence/v1",
        "plan": digest(PLAN),
        "truth_used": False,
        "held_used": False,
        "datasets": influence_tables,
    }
    write_sealed(CANDIDATES, candidate_artifact)
    write_sealed(INFLUENCE, influence_artifact)
    write_sealed(
        ATLAS,
        {
            "schema": "paired-ds1-ds3-iteration31-exact-phase-state-atlas/v1",
            "plan": digest(PLAN),
            "truth_used": False,
            "held_used": False,
            "state_storage": "in-memory only; this receipt records every exact node digest",
            "datasets": atlas_records,
        },
    )
    both_pass = all(results[name]["preflight_passed"] for name in ("DS1", "DS3"))
    output = {
        "schema": "paired-ds1-ds3-iteration31-exact-soft-preflight/v1",
        "complete": True,
        "plan": digest(PLAN),
        "runner": digest(Path(__file__)),
        "candidate_table": digest(CANDIDATES),
        "influence_table": digest(INFLUENCE),
        "exact_phase_atlas": digest(ATLAS),
        "truth_used": False,
        "held_used": False,
        "datasets": results,
        "paired_preflight_passed": both_pass,
        "full_geographic_search_run": False,
        "disposition": (
            "eligible_for_separately_sealed_paired_search"
            if both_pass
            else "no_go_preflight_gate_failed"
        ),
        "elapsed_s": time.monotonic() - started,
        "execution": {
            "workers_used": 1,
            "workers_allowed": MAX_WORKERS,
            "hard_wall_s": STAGE_HARD_WALL_S,
            "external_timeout_invocation": (
                "timeout --signal=TERM 1800s .venv/bin/python "
                "reports/2026_09_25_ds1_ds3_iteration31_exact_soft_preflight/run.py --run"
            ),
        },
    }
    write_sealed(RESULT, output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create-plan", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.create_plan:
        create_plan()
    else:
        run()


if __name__ == "__main__":
    main()
