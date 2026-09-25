#!/usr/bin/env python3
# ruff: noqa: E402
"""DS1 iteration 26: TRAIN-only rate-marginalized geographic score."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

for _name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
I23 = ROOT / "reports/2026_09_25_ds1_iteration23_widened_rate/run.py"
DS1 = ROOT / "reports/2026_09_24_ds1/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
ANCHOR = (37.85822833, -122.47896246)
GROUPS = ("20260921_00", "20260921_16")
TAUS = {"20260921_00": -0.75, "20260921_16": -0.50}
GROUP_WEIGHTS = {"20260921_00": 0.2742, "20260921_16": 0.7258}
SIGMA = 0.09176615913014215
ROBUST_SCALE_HZ = 250.0
CAP_HZ = 800.0
TAIL_ORDER = 64
MATERIAL_MASS = 1e-6


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verified_json(path: Path) -> dict[str, Any]:
    seal = path.with_suffix(path.suffix + ".sha256")
    if not seal.exists() or seal.read_text().strip().split()[0] != digest(path).split(":", 1)[1]:
        raise ValueError(f"bad seal: {path}")
    return json.loads(path.read_text())


def validate_plan(plan: dict[str, Any]) -> None:
    """Fail closed if code and the pre-output sealed contract diverge."""
    expected = {
        "anchor": {
            "latitude_deg": ANCHOR[0],
            "longitude_deg": ANCHOR[1],
            "group_tau_s": TAUS,
            "group_weights": GROUP_WEIGHTS,
        },
        "posterior": {
            "robust_scale_hz": ROBUST_SCALE_HZ,
            "gaussian_rate_sigma_s_h": SIGMA,
            "mode_scan_maximum_phase_step_s": 0.05,
            "coarse_quadrature_maximum_phase_step_s": 0.025,
            "fine_quadrature_maximum_phase_step_s": 0.0125,
            "core_sigma_radii": [12.0, 16.0],
            "tail_rule": "64-point Gauss-Legendre rational transform on each infinite tail",
            "endpoints_are_fitted_candidates": False,
        },
        "smoke_gates": {
            "repeated_score_absolute_tolerance": 1e-12,
            "coarse_fine_score_absolute_tolerance": 1e-6,
            "twelve_sixteen_sigma_score_absolute_tolerance": 1e-6,
            "maximum_tail_mass": 1e-4,
            "maximum_exact_sgp4_error_hz": 0.2,
            "maximum_exact_surrogate_expected_score_difference": 1e-4,
            "posterior_material_node_minimum_discrete_mass": MATERIAL_MASS,
            "exact_sgp4_nodes": (
                "zero, every refined mode, and every fine-16-sigma quadrature node "
                "with normalized discrete posterior mass >=1e-6"
            ),
        },
        "sealed_stencil": {
            "spacing_m": 48.828125,
            "east_m": [-48.828125, 0.0, 48.828125],
            "north_m": [-48.828125, 0.0, 48.828125],
            "translation_or_refinement": False,
            "required_winner": "center",
            "minimum_winner_gap": 2e-6,
            "require_exact_surrogate_winner_match": True,
            "leave_one_session_reranks": 12,
            "require_all_leave_one_session_winners": "center",
        },
        "execution": {
            "hard_wall_s": 1800,
            "workers": 4,
            "single_thread_math": True,
            "smoke_must_pass_before_stencil": True,
        },
    }
    if plan.get("status") != "sealed-before-output":
        raise ValueError("plan status mismatch")
    if plan.get("anchor") != expected["anchor"]:
        raise ValueError("anchor/tau/weight plan mismatch")
    for section in ("posterior", "smoke_gates", "sealed_stencil", "execution"):
        actual = plan.get(section, {})
        if any(actual.get(key) != value for key, value in expected[section].items()):
            raise ValueError(f"{section} plan mismatch")
    policy = plan.get("data_policy", {})
    if policy != {
        "partition": "original randomized TRAIN rows only",
        "identity": "hard association selected once at the anchor from TRAIN and frozen",
        "unsupported_track_loss": 1.0,
        "truth_used": False,
        "held_used": False,
    }:
        raise ValueError("data policy mismatch")
    if plan.get("score") != {
        "track_loss": "min((TRAIN_RMS_hz/800)^2,1)",
        "within_session_weight": "occupied seconds",
        "session_weight": "equal within group",
        "group_weights": "frozen anchor weights",
    }:
        raise ValueError("score plan mismatch")


def write_sealed(path: Path, value: dict[str, Any]) -> None:
    if path.exists() or path.with_suffix(path.suffix + ".sha256").exists():
        raise FileExistsError(path)
    content = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(content)
    path.with_suffix(path.suffix + ".sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


@dataclass
class GroupData:
    group: str
    tau_s: float
    data: Any
    search: Any
    orbit: Any
    sessions: tuple[str, ...]
    session_denominators: np.ndarray
    unsupported_numerators: np.ndarray
    bindings: list[dict[str, Any]]


def prepare_group(group: str) -> GroupData:
    """Select identity at the anchor using TRAIN values alone, then discard HELD rows."""
    i23 = load_module(I23, f"i26_i23_{group}")
    ds1 = load_module(DS1, f"i26_ds1_{group}")
    orbit = load_module(ORBIT, f"i26_orbit_{group}")
    case = i23.load_case(group)
    _clock, engine = ds1.make_engine(case)
    for session in engine.sessions:
        session["cache_path"] = str(ds1.CACHE_ROOTS[group] / session["session_id"])
    receiver, up = engine.search.receiver_ecef(*ANCHOR)
    tau = TAUS[group]
    fields = {key: [] for key in ("y", "track", "source", "session", "time")}
    weights: dict[str, float] = {}
    assignments: list[dict[str, Any]] = []
    source_info: dict[str, Any] = {}
    unsupported: dict[str, float] = {}
    denominators: dict[str, float] = {}
    for session in engine.sessions:
        sid = str(session["session_id"])
        receipt = json.loads((Path(session["cache_path"]) / "cache_receipt.json").read_text())
        evidence = receipt["prepared_evidence"]
        norads: set[str] = set()
        unsupported[sid] = 0.0
        denominators[sid] = float(sum(track["weight"] for track in session["tracks"]))
        for track in session["tracks"]:
            train = np.asarray(track["train"], bool)
            times = np.asarray(track["times"], float)[train]
            measured = np.asarray(track["measured"], float)[train]
            # Interpolation, visibility, CFO, and identity choice see TRAIN rows only.
            p, v = engine.interpolate(session, times, np.asarray([tau]))
            p, v = p[:, :, 0, :], v[:, :, 0, :]
            delta = p - receiver
            distance = np.linalg.norm(delta, axis=-1)
            prediction = (
                -engine.search.REFERENCE_RF_HZ
                / engine.search.LIGHT_KM_S
                * np.sum(delta * v, axis=-1)
                / distance
            )
            residual = measured[None, :] - prediction
            error = residual - np.mean(residual, axis=1)[:, None]
            rms = np.sqrt(np.mean(error * error, axis=1))
            visible = np.max(np.sum(delta * up, axis=-1) / distance, axis=1) >= 0
            rms = np.where(visible, rms, np.inf)
            winner = int(np.argmin(rms))
            weight = float(track["weight"])
            if not np.isfinite(rms[winner]):
                unsupported[sid] += weight
                assignments.append(
                    {"session_id": sid, "track_id": str(track["track_id"]), "candidate_id": None}
                )
                continue
            source = str(session["candidate_ids"][winner])
            name = f"{sid}:{track['track_id']}"
            fields["y"].append(measured)
            fields["track"].append(np.full(len(times), name, object))
            fields["source"].append(np.full(len(times), source, object))
            fields["session"].append(np.full(len(times), sid, object))
            fields["time"].append(times)
            weights[name] = weight
            norads.add(source)
            assignments.append(
                {"session_id": sid, "track_id": str(track["track_id"]), "candidate_id": source}
            )
        source_info[sid] = {
            "snapshot_digest": evidence["snapshot_digest"],
            "capture_start_utc_ns": int(evidence["start_utc_ns"]),
            "norads": sorted(norads),
        }
    if not fields["y"]:
        raise ValueError("no TRAIN-supported tracks")
    y = np.concatenate(fields["y"])
    track = np.concatenate(fields["track"])
    source = np.concatenate(fields["source"])
    session_values = np.concatenate(fields["session"])
    time_s = np.concatenate(fields["time"])
    ages = orbit.causal_ages(source_info)
    age_h = np.empty(len(y), float)
    for sid, info in source_info.items():
        for norad in info["norads"]:
            rows = (session_values.astype(str) == sid) & (source.astype(str) == norad)
            age_h[rows] = (info["capture_start_utc_ns"] - ages[(sid, norad)]) / 3.6e12
    p_nodes, v_nodes = orbit.exact_phase_nodes(session_values, source, time_s, source_info, tau)
    data = orbit.Prepared(
        y=y,
        train=np.ones(len(y), bool),
        track=track,
        source=source,
        session=session_values,
        age_h=age_h,
        time_s=time_s,
        p_nodes=p_nodes,
        v_nodes=v_nodes,
        weights=weights,
        assignments=assignments,
        sources=source_info,
    )
    sessions = tuple(sorted(denominators))
    return GroupData(
        group=group,
        tau_s=tau,
        data=data,
        search=engine.search,
        orbit=orbit,
        sessions=sessions,
        session_denominators=np.asarray([denominators[s] for s in sessions]),
        unsupported_numerators=np.asarray([unsupported[s] for s in sessions]),
        bindings=engine.bindings,
    )


class SourceEvaluator:
    def __init__(self, context: GroupData, source: str, receiver: np.ndarray):
        self.context = context
        self.source = source
        data = context.data
        self.rows = np.flatnonzero(data.source.astype(str) == source)
        self.y = np.asarray(data.y[self.rows], float)
        self.age = np.asarray(data.age_h[self.rows], float)
        self.p = np.asarray(data.p_nodes[self.rows], float)
        self.v = np.asarray(data.v_nodes[self.rows], float)
        self.track = data.track[self.rows].astype(str)
        self.session = data.session[self.rows].astype(str)
        self.tracks = tuple(np.unique(self.track))
        self.receiver = receiver
        self.track_masks = [self.track == track for track in self.tracks]
        self.track_weights = np.asarray([data.weights[track] for track in self.tracks], float)
        session_index = {sid: index for index, sid in enumerate(context.sessions)}
        self.track_sessions = np.asarray(
            [session_index[str(self.session[np.flatnonzero(mask)[0]])] for mask in self.track_masks]
        )
        self.maximum_age_h = float(np.max(np.abs(self.age)))

    def evaluate(
        self, rates: np.ndarray, *, losses: bool = True
    ) -> tuple[np.ndarray, np.ndarray | None]:
        rates = np.asarray(rates, float)
        energy = np.empty(len(rates), float)
        numerators = np.zeros((len(rates), len(self.context.sessions)), float) if losses else None
        for start in range(0, len(rates), 256):
            local = rates[start : start + 256]
            count = len(local)
            phase = (local[:, None] * self.age[None, :]).reshape(-1)
            p = self.context.orbit.quartic(np.tile(self.p, (count, 1, 1)), phase)
            v = self.context.orbit.quartic(np.tile(self.v, (count, 1, 1)), phase)
            prediction = self.context.orbit.doppler(
                self.receiver, p, v, self.context.search
            ).reshape(count, len(self.rows))
            raw = self.y[None, :] - prediction
            total = np.zeros(count, float)
            for index, mask in enumerate(self.track_masks):
                error = raw[:, mask] - np.mean(raw[:, mask], axis=1)[:, None]
                z = error / ROBUST_SCALE_HZ
                total += np.sum(np.sqrt(1.0 + z * z) - 1.0, axis=1)
                if numerators is not None:
                    rms2 = np.mean(error * error, axis=1)
                    loss = np.minimum(rms2 / CAP_HZ**2, 1.0)
                    numerators[start : start + count, self.track_sessions[index]] += (
                        self.track_weights[index] * loss
                    )
            energy[start : start + count] = total + 0.5 * (local / SIGMA) ** 2
        return energy, numerators

    def modes(self) -> list[dict[str, float]]:
        bound = 16.0 * SIGMA
        intervals = max(64, int(np.ceil(2 * bound * self.maximum_age_h / 0.05)))
        if intervals % 2:
            intervals += 1
        grid = np.linspace(-bound, bound, intervals + 1)
        values, _ = self.evaluate(grid, losses=False)
        candidates = []
        for index in range(1, len(grid) - 1):
            if values[index] <= values[index - 1] and values[index] <= values[index + 1]:
                result = minimize_scalar(
                    lambda rate: float(self.evaluate(np.asarray([rate]), losses=False)[0][0]),
                    bounds=(float(grid[index - 1]), float(grid[index + 1])),
                    method="bounded",
                    options={"xatol": 2e-8, "maxiter": 100},
                )
                candidates.append({"rate_s_h": float(result.x), "energy": float(result.fun)})
        if not candidates:
            index = int(np.argmin(values[1:-1])) + 1
            candidates.append({"rate_s_h": float(grid[index]), "energy": float(values[index])})
        candidates.sort(key=lambda row: (row["energy"], abs(row["rate_s_h"]), row["rate_s_h"]))
        distinct = []
        for row in candidates:
            if all(abs(row["rate_s_h"] - old["rate_s_h"]) > 1e-6 for old in distinct):
                distinct.append(row)
        return distinct

    def integrate(self, radius_sigma: float, phase_step_s: float) -> dict[str, Any]:
        bound = radius_sigma * SIGMA
        intervals = max(64, int(np.ceil(2 * bound * self.maximum_age_h / phase_step_s)))
        if intervals % 2:
            intervals += 1
        core_rates = np.linspace(-bound, bound, intervals + 1)
        step = float(core_rates[1] - core_rates[0])
        core_weights = np.full(len(core_rates), step)
        core_weights[[0, -1]] *= 0.5
        x, w = np.polynomial.legendre.leggauss(TAIL_ORDER)
        u, uw = (x + 1.0) / 2.0, w / 2.0
        extent = SIGMA * u / (1.0 - u)
        jacobian = SIGMA / (1.0 - u) ** 2
        tail_rates = np.concatenate((-bound - extent[::-1], bound + extent))
        tail_weights = np.concatenate(((uw * jacobian)[::-1], uw * jacobian))
        rates = np.concatenate((tail_rates[:TAIL_ORDER], core_rates, tail_rates[TAIL_ORDER:]))
        weights = np.concatenate(
            (tail_weights[:TAIL_ORDER], core_weights, tail_weights[TAIL_ORDER:])
        )
        energy, numerators = self.evaluate(rates)
        log_mass = np.log(weights) - energy
        log_z = float(logsumexp(log_mass))
        posterior = np.exp(log_mass - log_z)
        assert numerators is not None
        expected = posterior @ numerators
        tail_mask = np.abs(rates) > bound
        return {
            "rates": rates,
            "posterior": posterior,
            "expected_session_numerators": expected,
            "tail_mass": float(np.sum(posterior[tail_mask])),
            "posterior_mean_s_h": float(np.sum(posterior * rates)),
            "posterior_sd_s_h": float(
                np.sqrt(np.sum(posterior * (rates - np.sum(posterior * rates)) ** 2))
            ),
            "core_radius_sigma": radius_sigma,
            "maximum_phase_step_s": phase_step_s,
            "core_intervals": intervals,
            "log_normalizer": log_z,
        }


class ExactEvaluator:
    def __init__(self, context: GroupData):
        self.context = context
        self.replay = load_module(
            ROOT / "tools/replay_regional_doppler.py", f"i26_exact_{context.group}"
        )
        from leo.sky.propagation import parse_element_sets

        self.catalogues = {}
        for info in context.data.sources.values():
            key = info["snapshot_digest"]
            if key not in self.catalogues:
                payload = context.orbit.archive_payload(key)
                self.catalogues[key] = parse_element_sets(payload.decode("ascii"))

    def predictions(self, source_eval: SourceEvaluator, rates: np.ndarray) -> np.ndarray:
        data, context = self.context.data, self.context
        rates = np.asarray(rates, float)
        prediction = np.empty((len(rates), len(source_eval.rows)), float)
        local_positions = {row: index for index, row in enumerate(source_eval.rows)}
        for sid, info in data.sources.items():
            rows = np.flatnonzero(
                (data.session.astype(str) == sid) & (data.source.astype(str) == source_eval.source)
            )
            if not len(rows):
                continue
            catalogue = self.catalogues[info["snapshot_digest"]]
            catalogue_index = {
                str(norad): index for index, norad in enumerate(catalogue.satellite_numbers)
            }[source_eval.source]
            receive_ns = int(info["capture_start_utc_ns"]) + np.rint(
                (np.asarray(data.time_s[rows]) + context.tau_s) * 1e9
            ).astype(np.int64)
            correction_ns = np.rint(rates[:, None] * data.age_h[rows][None, :] * 1e9).astype(
                np.int64
            )
            orbit_ns = receive_ns[None, :] + correction_ns
            grid = self.replay.SamplingGrid(tuple(int(v) for v in orbit_ns.ravel()), 0, 1.0)
            state = self.replay.propagate_grid(catalogue, grid, [catalogue_index])
            repeated_receive = np.tile(receive_ns, len(rates))
            jd, fraction = self.replay.julian_day_from_utc_ns(repeated_receive)
            p, v = self.replay.teme_to_ecef(
                state.position_teme_km,
                state.velocity_teme_km_s,
                self.replay.greenwich_mean_sidereal_time_rad(jd, fraction),
            )
            if (
                np.any(state.error_code != 0)
                or not np.all(np.isfinite(p))
                or not np.all(np.isfinite(v))
            ):
                raise ValueError("exact propagation failure")
            local = [local_positions[int(row)] for row in rows]
            prediction[:, local] = context.orbit.doppler(
                source_eval.receiver,
                p[0],
                v[0],
                context.search,
            ).reshape(len(rates), len(rows))
        return prediction

    def audit(
        self,
        source_eval: SourceEvaluator,
        distribution: dict[str, Any],
        modes: list[dict[str, float]],
    ) -> dict[str, Any]:
        material = distribution["posterior"] >= MATERIAL_MASS
        material_rates = distribution["rates"][material]
        audit_rates = np.unique(
            np.concatenate(
                (
                    material_rates,
                    np.asarray([0.0]),
                    np.asarray([m["rate_s_h"] for m in modes]),
                )
            )
        )
        exact = self.predictions(source_eval, audit_rates)
        # Surrogate predictions and loss use the identical rates and profiled CFO rule.
        count = len(audit_rates)
        phase = (audit_rates[:, None] * source_eval.age[None, :]).reshape(-1)
        p = source_eval.context.orbit.quartic(np.tile(source_eval.p, (count, 1, 1)), phase)
        v = source_eval.context.orbit.quartic(np.tile(source_eval.v, (count, 1, 1)), phase)
        surrogate = source_eval.context.orbit.doppler(
            source_eval.receiver, p, v, source_eval.context.search
        ).reshape(count, len(source_eval.rows))
        error = surrogate - exact
        exact_num = np.zeros((count, len(source_eval.context.sessions)), float)
        surrogate_num = np.zeros_like(exact_num)
        for index, mask in enumerate(source_eval.track_masks):
            for prediction, output in ((exact, exact_num), (surrogate, surrogate_num)):
                raw = source_eval.y[None, :] - prediction
                residual = raw[:, mask] - np.mean(raw[:, mask], axis=1)[:, None]
                loss = np.minimum(np.mean(residual * residual, axis=1) / CAP_HZ**2, 1.0)
                output[:, source_eval.track_sessions[index]] += (
                    source_eval.track_weights[index] * loss
                )
        material_index = np.searchsorted(audit_rates, material_rates)
        # Exact expected score uses exact losses on every predeclared material
        # node and the surrogate value on sub-threshold nodes.  Thus the
        # reported delta is precisely the posterior-weighted exact correction
        # over all nodes required by the plan, without renormalizing them.
        _, all_surrogate_numerators = source_eval.evaluate(distribution["rates"])
        assert all_surrogate_numerators is not None
        exact_expected = distribution["posterior"] @ all_surrogate_numerators
        exact_expected += distribution["posterior"][material] @ (
            exact_num[material_index] - surrogate_num[material_index]
        )
        return {
            "audit_rate_count": len(audit_rates),
            "material_rate_count": len(material_rates),
            "material_posterior_mass": float(np.sum(distribution["posterior"][material])),
            "unmaterial_posterior_mass": float(np.sum(distribution["posterior"][~material])),
            "maximum_absolute_prediction_error_hz": float(np.max(np.abs(error))),
            "rms_prediction_error_hz": float(np.sqrt(np.mean(error * error))),
            "maximum_absolute_phase_s": float(
                np.max(np.abs(audit_rates[:, None] * source_eval.age[None, :]))
            ),
            "exact_expected_session_numerators": exact_expected,
            "surrogate_material_expected_session_numerators": distribution["posterior"]
            @ all_surrogate_numerators,
        }


def score_sessions(context: GroupData, supported_numerators: np.ndarray) -> dict[str, Any]:
    losses = (context.unsupported_numerators + supported_numerators) / context.session_denominators
    return {
        "group_score": float(np.mean(losses)),
        "sessions": [
            {
                "session_id": sid,
                "score": float(loss),
                "occupied_second_weight": float(denom),
                "unsupported_occupied_second_weight": float(unsupported),
            }
            for sid, loss, denom, unsupported in zip(
                context.sessions,
                losses,
                context.session_denominators,
                context.unsupported_numerators,
                strict=True,
            )
        ],
    }


def pool(group_scores: dict[str, dict[str, Any]]) -> float:
    return float(sum(GROUP_WEIGHTS[group] * group_scores[group]["group_score"] for group in GROUPS))


def run_smoke() -> dict[str, Any]:
    begun = time.perf_counter()
    contexts = {group: prepare_group(group) for group in GROUPS}
    variants = {
        "coarse_12sigma": (12.0, 0.025),
        "fine_12sigma": (12.0, 0.0125),
        "fine_16sigma": (16.0, 0.0125),
        "repeat_fine_16sigma": (16.0, 0.0125),
    }
    pooled_variants: dict[str, dict[str, Any]] = {}
    group_outputs = []
    maximum_tail = 0.0
    maximum_exact_error = 0.0
    sparse_explicit: dict[str, Any] = {}
    source_68739: dict[str, Any] | None = None
    exact_groups: dict[str, dict[str, Any]] = {}
    material_surrogate_groups: dict[str, dict[str, Any]] = {}
    for group, context in contexts.items():
        receiver, _up = context.search.receiver_ecef(*ANCHOR)
        sources = sorted(np.unique(context.data.source.astype(str)))
        accumulators = {name: np.zeros(len(context.sessions)) for name in variants}
        exact_accumulator = np.zeros(len(context.sessions))
        material_surrogate_accumulator = np.zeros(len(context.sessions))
        exact_engine = ExactEvaluator(context)
        summaries = []
        for source in sources:
            evaluator = SourceEvaluator(context, source, receiver)
            modes = evaluator.modes()
            integrations = {
                name: evaluator.integrate(radius, phase_step)
                for name, (radius, phase_step) in variants.items()
            }
            for name, result in integrations.items():
                accumulators[name] += result["expected_session_numerators"]
            fine = integrations["fine_16sigma"]
            exact = exact_engine.audit(evaluator, fine, modes)
            exact_accumulator += exact["exact_expected_session_numerators"]
            material_surrogate_accumulator += exact[
                "surrogate_material_expected_session_numerators"
            ]
            maximum_tail = max(maximum_tail, fine["tail_mass"])
            maximum_exact_error = max(
                maximum_exact_error, exact["maximum_absolute_prediction_error_hz"]
            )
            summary = {
                "source": source,
                "training_observations": len(evaluator.rows),
                "training_tracks": len(evaluator.tracks),
                "maximum_tle_age_h": evaluator.maximum_age_h,
                "modes": modes,
                "posterior_mean_s_h": fine["posterior_mean_s_h"],
                "posterior_sd_s_h": fine["posterior_sd_s_h"],
                "tail_mass": fine["tail_mass"],
                "core_intervals": fine["core_intervals"],
                "exact_audit": {
                    key: value
                    for key, value in exact.items()
                    if not key.endswith("session_numerators")
                },
            }
            summaries.append(summary)
            if source == "68739":
                source_68739 = {"group_id": group, **summary}
            if len(evaluator.rows) <= 4 or len(evaluator.tracks) == 1:
                sparse_explicit[f"{group}:{source}"] = {"group_id": group, **summary}
        scored = {name: score_sessions(context, value) for name, value in accumulators.items()}
        exact_scored = score_sessions(context, exact_accumulator)
        material_surrogate_scored = score_sessions(context, material_surrogate_accumulator)
        exact_groups[group] = exact_scored
        material_surrogate_groups[group] = material_surrogate_scored
        group_outputs.append(
            {
                "group_id": group,
                "tau_s": context.tau_s,
                "group_weight": GROUP_WEIGHTS[group],
                "training_observations": len(context.data.y),
                "supported_tracks": len(context.data.weights),
                "unsupported_tracks": sum(
                    row["candidate_id"] is None for row in context.data.assignments
                ),
                "source_count": len(sources),
                "variants": scored,
                "exact_material_score": exact_scored,
                "surrogate_material_score": material_surrogate_scored,
                "sources": summaries,
                "session_bindings": context.bindings,
            }
        )
        for name in variants:
            pooled_variants.setdefault(name, {})[group] = scored[name]
    pooled_scores = {name: pool(scores) for name, scores in pooled_variants.items()}
    exact_score = pool(exact_groups)
    material_surrogate_score = pool(material_surrogate_groups)
    gates = {
        "repeated_determinism": abs(
            pooled_scores["fine_16sigma"] - pooled_scores["repeat_fine_16sigma"]
        )
        <= 1e-12,
        "coarse_fine_convergence": abs(
            pooled_scores["coarse_12sigma"] - pooled_scores["fine_12sigma"]
        )
        <= 1e-6,
        "twelve_sixteen_sigma_convergence": abs(
            pooled_scores["fine_12sigma"] - pooled_scores["fine_16sigma"]
        )
        <= 1e-6,
        "tail_mass": maximum_tail <= 1e-4,
        "exact_sgp4_error": maximum_exact_error <= 0.2,
        "exact_surrogate_expected_score": abs(exact_score - pooled_scores["fine_16sigma"]) <= 1e-4,
    }
    elapsed = time.perf_counter() - begun
    return {
        "schema": "ds1-iteration26-rate-marginal-smoke/v1",
        "complete": True,
        "truth_used": False,
        "held_used": False,
        "geographic_search_run": False,
        "anchor": {"latitude_deg": ANCHOR[0], "longitude_deg": ANCHOR[1]},
        "pooled_scores": pooled_scores,
        "exact_material_expected_score": exact_score,
        "surrogate_material_expected_score": material_surrogate_score,
        "exact_minus_full_surrogate_expected_score": exact_score - pooled_scores["fine_16sigma"],
        "surrogate_material_minus_full_surrogate_expected_score": material_surrogate_score
        - pooled_scores["fine_16sigma"],
        "maximum_tail_mass": maximum_tail,
        "maximum_exact_sgp4_error_hz": maximum_exact_error,
        "groups": group_outputs,
        "explicit_source_68739": source_68739,
        "explicit_sparse_sources": sparse_explicit,
        "gate": {"criteria": gates, "passed": all(gates.values())},
        "elapsed_s": elapsed,
        "execution": {
            "workers_allowed": 4,
            "workers_used": 1,
            "single_thread_math": True,
            "hard_wall_s": 1800,
            "hard_wall_enforcement": "runner elapsed check plus caller process timeout",
        },
        "bindings": {
            "plan": digest(PLAN),
            "runner": digest(Path(__file__)),
            "iteration23_runner": digest(I23),
            "ds1_runner": digest(DS1),
            "orbit_runner": digest(ORBIT),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("smoke",), default="smoke")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = verified_json(PLAN)
    validate_plan(plan)
    begun = time.monotonic()
    result = run_smoke()
    if time.monotonic() - begun > float(plan["execution"]["hard_wall_s"]):
        raise TimeoutError("hard wall exceeded")
    write_sealed(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "passed": result["gate"]["passed"],
                "criteria": result["gate"]["criteria"],
                "elapsed_s": result["elapsed_s"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
