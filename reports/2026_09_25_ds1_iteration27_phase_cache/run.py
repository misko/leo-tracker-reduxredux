#!/usr/bin/env python3
# ruff: noqa: E402
"""DS1 iteration 27: exact phase-state atlas and sealed 48.828125 m stencil."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

for _name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_name] = "1"
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import logsumexp

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
I26 = ROOT / "reports/2026_09_25_ds1_iteration26_rate_marginal/run.py"
I23 = ROOT / "reports/2026_09_25_ds1_iteration23_widened_rate/run.py"
DS1 = ROOT / "reports/2026_09_24_ds1/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
REPLAY = ROOT / "tools/replay_regional_doppler.py"
ANCHOR = (37.85822833, -122.47896246)
GROUPS = ("20260921_00", "20260921_16")
TAUS = {"20260921_00": -0.75, "20260921_16": -0.50}
GROUP_WEIGHTS = {"20260921_00": 0.2742, "20260921_16": 0.7258}
SIGMA = 0.09176615913014215
ROBUST_SCALE_HZ = 250.0
CAP_HZ = 800.0
TAIL_ORDER = 64
MATERIAL_MASS = 1e-6
CACHE_ROOT = Path("/tmp/ds1-iteration27-phase-state-cache")
ATLAS_ERROR_HZ = 0.2


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def array_digest(value: np.ndarray) -> str:
    a = np.ascontiguousarray(value)
    return sha256_bytes(canonical({"dtype": a.dtype.str, "shape": list(a.shape)}) + a.tobytes())


def float_bits(values: np.ndarray | list[float]) -> list[str]:
    return [f"{int(v):016x}" for v in np.asarray(values, dtype="<f8").view("<u8")]


def bits_float(values: list[str]) -> np.ndarray:
    return np.asarray([int(v, 16) for v in values], dtype="<u8").view("<f8")


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
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )


def validate_plan(plan: dict[str, Any]) -> None:
    if (
        plan.get("schema") != "ds1-iteration27-phase-cache-plan/v1"
        or plan.get("status") != "sealed-before-output"
    ):
        raise ValueError("plan identity/status mismatch")
    if plan.get("anchor") != {
        "latitude_deg": ANCHOR[0],
        "longitude_deg": ANCHOR[1],
        "group_tau_s": TAUS,
        "group_weights": GROUP_WEIGHTS,
    }:
        raise ValueError("anchor plan mismatch")
    if plan.get("data_policy") != {
        "partition": "original randomized TRAIN rows only",
        "identity": "hard association selected once at the anchor from TRAIN and frozen",
        "unsupported_track_loss": 1.0,
        "truth_used": False,
        "held_used": False,
    }:
        raise ValueError("data policy mismatch")
    posterior = {
        "per_source": True,
        "profiled_nuisance": "per-track TRAIN mean CFO at every rate",
        "energy": "sum(sqrt(1+(error_hz/250)^2)-1)+0.5*(rate/sigma)^2",
        "robust_scale_hz": ROBUST_SCALE_HZ,
        "gaussian_rate_sigma_s_h": SIGMA,
        "mode_scan_maximum_phase_step_s": 0.05,
        "coarse_quadrature_maximum_phase_step_s": 0.025,
        "fine_quadrature_maximum_phase_step_s": 0.0125,
        "core_sigma_radii": [12.0, 16.0],
        "tail_rule": "64-point Gauss-Legendre rational transform on each infinite tail",
        "endpoints_are_fitted_candidates": False,
    }
    if plan.get("posterior") != posterior:
        raise ValueError("posterior plan mismatch")
    cache = plan.get("phase_state_cache", {})
    keys = [
        "group_id",
        "session_id",
        "snapshot_digest",
        "capture_start_utc_ns",
        "norad",
        "tau_ns",
        "train_time_vector_digest",
        "schedule_digest",
        "assignment_digest",
        "archive_payload_digest",
        "runner_digest",
        "rate_node_bits",
        "phase_node_bits",
        "per_row_correction_ns",
    ]
    if (
        cache.get("schema") != "ds1-phase-state-cache/v1"
        or cache.get("root") != str(CACHE_ROOT)
        or cache.get("key_fields") != keys
        or cache.get("chunk_payload") != "ECEF position/velocity state arrays only"
        or cache.get("initial_phase_spacing_s") != 1.0
        or "0.125 s" not in cache.get("refinement", "")
        or "four-knot barycentric cubic" not in cache.get("interpolation", "")
    ):
        raise ValueError("phase cache plan mismatch")
    gates = plan.get("smoke_gates", {})
    expected = {
        "repeated_score_absolute_tolerance": 1e-12,
        "coarse_fine_score_absolute_tolerance": 1e-6,
        "twelve_sixteen_sigma_score_absolute_tolerance": 1e-6,
        "maximum_tail_mass": 1e-4,
        "maximum_exact_sgp4_error_hz": ATLAS_ERROR_HZ,
        "maximum_exact_surrogate_expected_score_difference": 1e-4,
        "posterior_material_node_minimum_discrete_mass": MATERIAL_MASS,
        "maximum_atlas_validation_error_hz": ATLAS_ERROR_HZ,
    }
    if any(gates.get(k) != v for k, v in expected.items()):
        raise ValueError("smoke gates mismatch")
    stencil = {
        "spacing_m": 48.828125,
        "east_m": [-48.828125, 0.0, 48.828125],
        "north_m": [-48.828125, 0.0, 48.828125],
        "translation_or_refinement": False,
        "required_winner": "center",
        "minimum_winner_gap": 2e-6,
        "require_exact_surrogate_winner_match": True,
        "leave_one_session_reranks": 12,
        "require_all_leave_one_session_winners": "center",
    }
    if plan.get("sealed_stencil") != stencil:
        raise ValueError("stencil plan mismatch")
    if plan.get("execution") != {
        "hard_wall_s": 1800,
        "workers": 4,
        "single_thread_math": True,
        "smoke_must_pass_before_stencil": True,
    }:
        raise ValueError("execution plan mismatch")
    if plan.get("score") != {
        "track_loss": "min((TRAIN_RMS_hz/800)^2,1)",
        "within_session_weight": "occupied seconds",
        "session_weight": "equal within group",
        "group_weights": "frozen anchor weights",
    }:
        raise ValueError("score mismatch")


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
    i23 = load_module(I23, f"i27_i23_{group}")
    ds1 = load_module(DS1, f"i27_ds1_{group}")
    orbit = load_module(ORBIT, f"i27_orbit_{group}")
    _clock, engine = ds1.make_engine(i23.load_case(group))
    for session in engine.sessions:
        session["cache_path"] = str(ds1.CACHE_ROOTS[group] / session["session_id"])
    receiver, up = engine.search.receiver_ecef(*ANCHOR)
    fields = {k: [] for k in ("y", "track", "source", "session", "time")}
    weights = {}
    assignments = []
    source_info = {}
    unsupported = {}
    denominators = {}
    binding = {x["session_id"]: x for x in engine.bindings}
    for session in engine.sessions:
        sid = str(session["session_id"])
        receipt = json.loads((Path(session["cache_path"]) / "cache_receipt.json").read_text())
        evidence = receipt["prepared_evidence"]
        norads = set()
        unsupported[sid] = 0.0
        denominators[sid] = float(sum(t["weight"] for t in session["tracks"]))
        schedule = []
        for track in session["tracks"]:
            train = np.asarray(track["train"], bool)
            times = np.asarray(track["times"], float)[train]
            measured = np.asarray(track["measured"], float)[train]
            schedule.append(
                {
                    "track_id": str(track["track_id"]),
                    "train_time_bits": float_bits(times),
                    "train_mask_digest": array_digest(train),
                }
            )
            p, v = engine.interpolate(session, times, np.asarray([TAUS[group]]))
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
            "schedule_digest": sha256_bytes(canonical(schedule)),
            "receipt_digest": binding[sid]["receipt"],
            "input_manifest_digest": evidence["input_manifest_sha256"],
        }
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
    assignment_digest = sha256_bytes(canonical(assignments))
    for info in source_info.values():
        info["assignment_digest"] = assignment_digest
    data = orbit.Prepared(
        y=y,
        train=np.ones(len(y), bool),
        track=track,
        source=source,
        session=session_values,
        age_h=age_h,
        time_s=time_s,
        p_nodes=np.empty((len(y), 0, 3)),
        v_nodes=np.empty((len(y), 0, 3)),
        weights=weights,
        assignments=assignments,
        sources=source_info,
    )
    sessions = tuple(sorted(denominators))
    return GroupData(
        group,
        TAUS[group],
        data,
        engine.search,
        orbit,
        sessions,
        np.asarray([denominators[s] for s in sessions]),
        np.asarray([unsupported[s] for s in sessions]),
        engine.bindings,
    )


def barycentric_states(knots: np.ndarray, values: np.ndarray, query: np.ndarray) -> np.ndarray:
    knots = np.asarray(knots, float)
    query = np.asarray(query, float)
    if len(knots) < 4 or np.any(query < knots[0]) or np.any(query > knots[-1]):
        raise ValueError("atlas interpolation outside support")
    output = np.empty((len(query),) + values.shape[1:], float)
    starts = np.clip(np.searchsorted(knots, query, side="right") - 2, 0, len(knots) - 4)
    for start in np.unique(starts):
        selected = np.flatnonzero(starts == start)
        x = knots[start : start + 4]
        y = values[start : start + 4]
        q = query[selected]
        exact = q[:, None] == x[None, :]
        weights = np.asarray([1 / np.prod(x[j] - np.delete(x, j)) for j in range(4)])
        safe = np.where(exact, 1.0, q[:, None] - x[None, :])
        terms = weights[None, :] / safe
        coeff = terms / np.sum(terms, axis=1)[:, None]
        for row, col in zip(*np.nonzero(exact), strict=True):
            coeff[row] = 0
            coeff[row, col] = 1
        output[selected] = np.einsum("qk,k...->q...", coeff, y)
    return output


@dataclass
class AtlasEntry:
    metadata: dict[str, Any]
    knots: np.ndarray
    position: np.ndarray
    velocity: np.ndarray


class PhaseStateCache:
    def __init__(self, contexts: dict[str, GroupData], *, create: bool):
        self.contexts = contexts
        self.replay = load_module(REPLAY, "i27_replay")
        from leo.sky.propagation import parse_element_sets

        self.catalogues = {}
        self.payload_digests = {}
        for context in contexts.values():
            for info in context.data.sources.values():
                snap = info["snapshot_digest"]
                if snap not in self.catalogues:
                    payload = context.orbit.archive_payload(snap)
                    pd = sha256_bytes(payload)
                    if pd != snap:
                        raise ValueError("archive/snapshot digest mismatch")
                    self.catalogues[snap] = parse_element_sets(payload.decode("ascii"))
                    self.payload_digests[snap] = pd
        self.entries = {}
        self.manifest_path = CACHE_ROOT / "manifest.json"
        if create and not self.manifest_path.exists():
            CACHE_ROOT.mkdir(parents=True, exist_ok=True)
            self._build()
        else:
            self._load()

    def relation_rows(self, c: GroupData, sid: str, source: str) -> np.ndarray:
        return np.flatnonzero(
            (c.data.session.astype(str) == sid) & (c.data.source.astype(str) == source)
        )

    def exact_states(
        self, c: GroupData, sid: str, source: str, phase_s: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        info = c.data.sources[sid]
        rows = self.relation_rows(c, sid, source)
        times = np.asarray(c.data.time_s[rows], float)
        receive = int(info["capture_start_utc_ns"]) + np.rint((times + c.tau_s) * 1e9).astype(
            np.int64
        )
        phase = np.asarray(phase_s, float)
        correction = np.broadcast_to(
            np.rint(phase[:, None] * 1e9).astype(np.int64), (len(phase), len(rows))
        ).copy()
        orbit_ns = receive[None, :] + correction
        catalogue = self.catalogues[info["snapshot_digest"]]
        index = {str(n): i for i, n in enumerate(catalogue.satellite_numbers)}[source]
        grid = self.replay.SamplingGrid(tuple(int(v) for v in orbit_ns.ravel()), 0, 1.0)
        state = self.replay.propagate_grid(catalogue, grid, [index])
        repeated = np.tile(receive, len(phase))
        jd, fraction = self.replay.julian_day_from_utc_ns(repeated)
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
        shape = (len(phase), len(rows), 3)
        return p[0].reshape(shape), v[0].reshape(shape), correction

    def _metadata(
        self, c: GroupData, sid: str, source: str, knots: np.ndarray, correction: np.ndarray
    ) -> dict[str, Any]:
        info = c.data.sources[sid]
        rows = self.relation_rows(c, sid, source)
        times = np.asarray(c.data.time_s[rows], dtype="<f8")
        ages = np.asarray(c.data.age_h[rows], float)
        rate_nodes = knots / float(ages[0])
        key = {
            "group_id": c.group,
            "session_id": sid,
            "snapshot_digest": info["snapshot_digest"],
            "capture_start_utc_ns": int(info["capture_start_utc_ns"]),
            "norad": source,
            "tau_ns": int(round(c.tau_s * 1e9)),
            "train_time_vector_digest": array_digest(times),
            "schedule_digest": info["schedule_digest"],
            "assignment_digest": info["assignment_digest"],
            "archive_payload_digest": self.payload_digests[info["snapshot_digest"]],
            "runner_digest": digest(Path(__file__)),
            "rate_node_bits": float_bits(rate_nodes),
            "phase_node_bits": float_bits(knots),
            "per_row_correction_ns": correction.tolist(),
        }
        return {
            "key": key,
            "key_digest": sha256_bytes(canonical(key)),
            "phase_node_bits": float_bits(knots),
            "phase_node_count": len(knots),
            "per_row_correction_ns_digest": array_digest(correction),
            "training_row_count": len(rows),
            "input_manifest_digest": info["input_manifest_digest"],
            "receipt_digest": info["receipt_digest"],
        }

    def _initial_knots(self, age_h: float) -> np.ndarray:
        extent = 16 * SIGMA * abs(age_h)
        interior = np.arange(math.ceil(-extent), math.floor(extent) + 1, dtype=float)
        knots = np.unique(np.concatenate(([-extent, 0.0, extent], interior)))
        return (
            np.unique(np.concatenate((knots, np.linspace(-extent, extent, 4))))
            if len(knots) < 4
            else knots
        )

    def _build(self) -> None:
        records = []
        receivers = {g: c.search.receiver_ecef(*ANCHOR)[0] for g, c in self.contexts.items()}
        maximum = 0.0
        midpoint_count = 0
        for group in GROUPS:
            c = self.contexts[group]
            for sid, info in sorted(c.data.sources.items()):
                for source in info["norads"]:
                    rows = self.relation_rows(c, sid, source)
                    if not len(rows):
                        continue
                    ages = np.asarray(c.data.age_h[rows], float)
                    if np.ptp(ages) > 1e-12:
                        raise ValueError("nonconstant causal age")
                    knots = self._initial_knots(float(ages[0]))
                    p, v, correction = self.exact_states(c, sid, source, knots)
                    refinements = 0
                    while True:
                        mids = (knots[:-1] + knots[1:]) / 2
                        ep, ev, _ = self.exact_states(c, sid, source, mids)
                        ip = barycentric_states(knots, p, mids)
                        iv = barycentric_states(knots, v, mids)
                        exact = np.asarray(
                            [
                                c.orbit.doppler(receivers[group], ep[i], ev[i], c.search)
                                for i in range(len(mids))
                            ]
                        )
                        interp = np.asarray(
                            [
                                c.orbit.doppler(receivers[group], ip[i], iv[i], c.search)
                                for i in range(len(mids))
                            ]
                        )
                        errors = np.max(np.abs(exact - interp), axis=1)
                        midpoint_count += len(mids)
                        maximum = max(maximum, float(np.max(errors)))
                        split = (errors > ATLAS_ERROR_HZ) & (np.diff(knots) > 0.125 + 1e-15)
                        if not np.any(split):
                            if np.any(errors > ATLAS_ERROR_HZ):
                                raise ValueError("midpoint error above gate at 0.125 s")
                            break
                        knots = np.unique(np.concatenate((knots, mids[split])))
                        p, v, correction = self.exact_states(c, sid, source, knots)
                        refinements += int(np.sum(split))
                    metadata = self._metadata(c, sid, source, knots, correction)
                    chunk = CACHE_ROOT / f"{metadata['key_digest'].split(':', 1)[1]}.npz"
                    np.savez_compressed(chunk, position_ecef_km=p, velocity_ecef_km_s=v)
                    metadata.update(
                        {
                            "chunk": chunk.name,
                            "chunk_digest": digest(chunk),
                            "chunk_bytes": chunk.stat().st_size,
                            "refinement_knot_count": refinements,
                            "maximum_adjacent_midpoint_error_hz": float(np.max(errors)),
                        }
                    )
                    records.append(metadata)
        manifest = {
            "schema": "ds1-phase-state-cache/v1",
            "complete": True,
            "truth_used": False,
            "held_used": False,
            "payload_policy": "chunks contain ECEF position/velocity arrays only",
            "interpolation": "local four-knot barycentric cubic; no extrapolation",
            "records": records,
            "record_count": len(records),
            "chunk_bytes": sum(r["chunk_bytes"] for r in records),
            "maximum_adjacent_midpoint_error_hz": maximum,
            "adjacent_midpoint_validation_count": midpoint_count,
            "bindings": {
                "plan": digest(PLAN),
                "runner": digest(Path(__file__)),
                "iteration26_runner": digest(I26),
                "replay_runner": digest(REPLAY),
            },
        }
        write_sealed(self.manifest_path, manifest)
        self._install(manifest)

    def _load(self) -> None:
        self._install(verified_json(self.manifest_path))

    def _install(self, manifest: dict[str, Any]) -> None:
        if (
            manifest.get("schema") != "ds1-phase-state-cache/v1"
            or manifest.get("complete") is not True
            or manifest.get("truth_used") is not False
            or manifest.get("held_used") is not False
            or manifest.get("payload_policy") != "chunks contain ECEF position/velocity arrays only"
            or manifest.get("bindings", {}).get("plan") != digest(PLAN)
            or manifest.get("bindings", {}).get("runner") != digest(Path(__file__))
            or manifest.get("bindings", {}).get("iteration26_runner") != digest(I26)
            or manifest.get("bindings", {}).get("replay_runner") != digest(REPLAY)
            or manifest.get("record_count") != len(manifest.get("records", []))
            or manifest.get("chunk_bytes")
            != sum(row.get("chunk_bytes", -1) for row in manifest.get("records", []))
        ):
            raise ValueError("cache manifest mismatch")
        expected = set()
        for group, c in self.contexts.items():
            for sid, info in c.data.sources.items():
                expected.update(
                    (group, sid, s) for s in info["norads"] if len(self.relation_rows(c, sid, s))
                )
        for record in manifest["records"]:
            key = record["key"]
            identity = (key["group_id"], key["session_id"], key["norad"])
            c = self.contexts[identity[0]]
            knots = bits_float(record["phase_node_bits"])
            rows = self.relation_rows(c, identity[1], identity[2])
            correction = np.broadcast_to(
                np.rint(knots[:, None] * 1e9).astype(np.int64), (len(knots), len(rows))
            ).copy()
            current = self._metadata(c, identity[1], identity[2], knots, correction)
            for field in ("key", "key_digest", "phase_node_bits", "per_row_correction_ns_digest"):
                if current[field] != record[field]:
                    raise ValueError(f"cache provenance mismatch {identity} {field}")
            chunk = CACHE_ROOT / record["chunk"]
            if (
                chunk.stat().st_size != record["chunk_bytes"]
                or digest(chunk) != record["chunk_digest"]
            ):
                raise ValueError("chunk seal mismatch")
            with np.load(chunk, allow_pickle=False) as arrays:
                if set(arrays.files) != {"position_ecef_km", "velocity_ecef_km_s"}:
                    raise ValueError("non-state cache payload")
                p, v = arrays["position_ecef_km"], arrays["velocity_ecef_km_s"]
            expected_shape = (len(knots), len(rows), 3)
            if (
                p.dtype != np.dtype("float64")
                or v.dtype != np.dtype("float64")
                or p.shape != expected_shape
                or v.shape != expected_shape
                or not np.all(np.isfinite(p))
                or not np.all(np.isfinite(v))
            ):
                raise ValueError("cache state dtype/shape/finite mismatch")
            self.entries[identity] = AtlasEntry(record, knots, p, v)
        if set(self.entries) != expected:
            raise ValueError("cache coverage mismatch")

    def states(
        self, c: GroupData, sid: str, source: str, phase: np.ndarray, *, direct: bool = False
    ) -> tuple[np.ndarray, np.ndarray]:
        if direct:
            p, v, _ = self.exact_states(c, sid, source, phase)
            return p, v
        entry = self.entries[(c.group, sid, source)]
        return barycentric_states(entry.knots, entry.position, phase), barycentric_states(
            entry.knots, entry.velocity, phase
        )

    def provenance(self) -> dict[str, Any]:
        m = verified_json(self.manifest_path)
        return {
            "root": str(CACHE_ROOT),
            "manifest": str(self.manifest_path),
            "manifest_digest": digest(self.manifest_path),
            "record_count": m["record_count"],
            "chunk_bytes": m["chunk_bytes"],
            "maximum_adjacent_midpoint_error_hz": m["maximum_adjacent_midpoint_error_hz"],
            "adjacent_midpoint_validation_count": m["adjacent_midpoint_validation_count"],
        }

    def validate_midpoints(
        self, context: GroupData, receivers: list[np.ndarray]
    ) -> tuple[float, int]:
        maximum, count = 0.0, 0
        for (group, sid, source), entry in self.entries.items():
            if group != context.group:
                continue
            mids = (entry.knots[:-1] + entry.knots[1:]) / 2.0
            exact_p, exact_v = self.states(context, sid, source, mids, direct=True)
            atlas_p, atlas_v = self.states(context, sid, source, mids)
            for receiver in receivers:
                exact = np.asarray(
                    [
                        context.orbit.doppler(receiver, exact_p[i], exact_v[i], context.search)
                        for i in range(len(mids))
                    ]
                )
                atlas = np.asarray(
                    [
                        context.orbit.doppler(receiver, atlas_p[i], atlas_v[i], context.search)
                        for i in range(len(mids))
                    ]
                )
                maximum = max(maximum, float(np.max(np.abs(exact - atlas))))
                count += int(exact.size)
        return maximum, count


class SourceEvaluator:
    def __init__(
        self, context: GroupData, source: str, receiver: np.ndarray, cache: PhaseStateCache
    ):
        self.context = context
        self.source = source
        self.receiver = receiver
        self.cache = cache
        data = context.data
        self.rows = np.flatnonzero(data.source.astype(str) == source)
        self.y = np.asarray(data.y[self.rows], float)
        self.age = np.asarray(data.age_h[self.rows], float)
        self.track = data.track[self.rows].astype(str)
        self.session = data.session[self.rows].astype(str)
        self.tracks = tuple(np.unique(self.track))
        self.track_masks = [self.track == t for t in self.tracks]
        self.track_weights = np.asarray([data.weights[t] for t in self.tracks], float)
        session_index = {s: i for i, s in enumerate(context.sessions)}
        self.track_sessions = np.asarray(
            [session_index[str(self.session[np.flatnonzero(m)[0]])] for m in self.track_masks]
        )
        self.maximum_age_h = float(np.max(np.abs(self.age)))
        self.local = {int(row): i for i, row in enumerate(self.rows)}
        self._prediction_cache: dict[tuple[str, bool], np.ndarray] = {}

    def predictions(
        self,
        rates: np.ndarray,
        *,
        force_direct: bool = False,
        direct_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        rates = np.asarray(rates, float)
        requested = (
            np.zeros(len(rates), bool) if direct_mask is None else np.asarray(direct_mask, bool)
        )
        cache = getattr(self, "_prediction_cache", None)
        if cache is None:
            cache = self._prediction_cache = {}
        keys = [
            (float_bits([float(rate)])[0], bool(force_direct or requested[index]))
            for index, rate in enumerate(rates)
        ]
        missing = [index for index, key in enumerate(keys) if key not in cache]
        if missing:
            missing_rates = rates[missing]
            missing_direct = requested[missing]
            computed = self._predictions_uncached(
                missing_rates, force_direct=force_direct, direct_mask=missing_direct
            )
            for row, index in enumerate(missing):
                cache[keys[index]] = computed[row]
        return np.asarray([cache[key] for key in keys])

    def _predictions_uncached(
        self,
        rates: np.ndarray,
        *,
        force_direct: bool = False,
        direct_mask: np.ndarray | None = None,
    ) -> np.ndarray:
        rates = np.asarray(rates, float)
        requested = (
            np.zeros(len(rates), bool) if direct_mask is None else np.asarray(direct_mask, bool)
        )
        out = np.empty((len(rates), len(self.rows)), float)
        data = self.context.data
        for sid in self.context.sessions:
            global_rows = np.flatnonzero(
                (data.session.astype(str) == sid) & (data.source.astype(str) == self.source)
            )
            if not len(global_rows):
                continue
            local = np.asarray([self.local[int(row)] for row in global_rows])
            ages = np.asarray(data.age_h[global_rows], float)
            if np.ptp(ages) > 1e-12:
                raise ValueError(
                    "session/source causal age must be constant by iteration-26 convention"
                )
            phase = rates * float(ages[0])
            entry = self.cache.entries[(self.context.group, sid, self.source)]
            inside = (phase >= entry.knots[0]) & (phase <= entry.knots[-1]) & ~requested
            prediction = np.empty((len(rates), len(global_rows)), float)
            for direct, mask in (
                ((False, inside), (True, ~inside))
                if not force_direct
                else ((True, np.ones(len(rates), bool)),)
            ):
                if not np.any(mask):
                    continue
                p, v = self.cache.states(self.context, sid, self.source, phase[mask], direct=direct)
                prediction[mask] = np.asarray(
                    [
                        self.context.orbit.doppler(self.receiver, p[i], v[i], self.context.search)
                        for i in range(len(p))
                    ]
                )
            out[:, local] = prediction
        return out

    def numerators(self, prediction: np.ndarray) -> np.ndarray:
        output = np.zeros((len(prediction), len(self.context.sessions)), float)
        raw = self.y[None, :] - prediction
        for index, mask in enumerate(self.track_masks):
            error = raw[:, mask] - np.mean(raw[:, mask], axis=1)[:, None]
            loss = np.minimum(np.mean(error * error, axis=1) / CAP_HZ**2, 1.0)
            output[:, self.track_sessions[index]] += self.track_weights[index] * loss
        return output

    def evaluate(
        self, rates: np.ndarray, *, losses: bool = True, direct_mask: np.ndarray | None = None
    ) -> tuple[np.ndarray, np.ndarray | None]:
        rates = np.asarray(rates, float)
        energy = np.empty(len(rates))
        numerators = np.zeros((len(rates), len(self.context.sessions))) if losses else None
        for start in range(0, len(rates), 256):
            local = rates[start : start + 256]
            local_direct = (
                None
                if direct_mask is None
                else np.asarray(direct_mask, bool)[start : start + len(local)]
            )
            prediction = self.predictions(local, direct_mask=local_direct)
            raw = self.y[None, :] - prediction
            total = np.zeros(len(local))
            for index, mask in enumerate(self.track_masks):
                error = raw[:, mask] - np.mean(raw[:, mask], axis=1)[:, None]
                z = error / ROBUST_SCALE_HZ
                total += np.sum(np.sqrt(1 + z * z) - 1, axis=1)
                if numerators is not None:
                    numerators[start : start + len(local), self.track_sessions[index]] += (
                        self.track_weights[index]
                        * np.minimum(np.mean(error * error, axis=1) / CAP_HZ**2, 1.0)
                    )
            energy[start : start + len(local)] = total + 0.5 * (local / SIGMA) ** 2
        return energy, numerators

    def modes(self) -> list[dict[str, float]]:
        bound = 16 * SIGMA
        intervals = max(64, int(np.ceil(2 * bound * self.maximum_age_h / 0.05)))
        intervals += intervals % 2
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
            candidates = [{"rate_s_h": float(grid[index]), "energy": float(values[index])}]
        candidates.sort(key=lambda row: (row["energy"], abs(row["rate_s_h"]), row["rate_s_h"]))
        distinct = []
        for row in candidates:
            if all(abs(row["rate_s_h"] - old["rate_s_h"]) > 1e-6 for old in distinct):
                distinct.append(row)
        return distinct

    def integrate(self, radius_sigma: float, phase_step_s: float) -> dict[str, Any]:
        bound = radius_sigma * SIGMA
        intervals = max(64, int(np.ceil(2 * bound * self.maximum_age_h / phase_step_s)))
        intervals += intervals % 2
        core = np.linspace(-bound, bound, intervals + 1)
        step = float(core[1] - core[0])
        core_w = np.full(len(core), step)
        core_w[[0, -1]] *= 0.5
        x, w = np.polynomial.legendre.leggauss(TAIL_ORDER)
        u, uw = (x + 1) / 2, w / 2
        extent = SIGMA * u / (1 - u)
        jac = SIGMA / (1 - u) ** 2
        tails = np.concatenate((-bound - extent[::-1], bound + extent))
        tail_w = np.concatenate(((uw * jac)[::-1], uw * jac))
        rates = np.concatenate((tails[:TAIL_ORDER], core, tails[TAIL_ORDER:]))
        weights = np.concatenate((tail_w[:TAIL_ORDER], core_w, tail_w[TAIL_ORDER:]))
        direct = np.abs(rates) > bound
        energy, numerators = self.evaluate(rates, direct_mask=direct)
        log_mass = np.log(weights) - energy
        log_z = float(logsumexp(log_mass))
        posterior = np.exp(log_mass - log_z)
        assert numerators is not None
        mean = float(posterior @ rates)
        return {
            "rates": rates,
            "posterior": posterior,
            "expected_session_numerators": posterior @ numerators,
            "tail_mass": float(np.sum(posterior[np.abs(rates) > bound])),
            "posterior_mean_s_h": mean,
            "posterior_sd_s_h": float(np.sqrt(np.sum(posterior * (rates - mean) ** 2))),
            "core_radius_sigma": radius_sigma,
            "maximum_phase_step_s": phase_step_s,
            "core_intervals": intervals,
            "log_normalizer": log_z,
        }


def deterministic_nonmaterial(
    group: str, source: str, rates: np.ndarray, material: np.ndarray
) -> np.ndarray:
    chosen = []
    for i, rate in enumerate(rates):
        if material[i]:
            continue
        token = f"{group}:{source}:{float_bits([float(rate)])[0]}".encode()
        if int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 100 == 0:
            chosen.append(i)
    return np.asarray(chosen, dtype=int)


def audit_distribution(
    e: SourceEvaluator,
    distribution: dict[str, Any],
    modes: list[dict[str, float]],
    extra_rates: np.ndarray | None = None,
) -> dict[str, Any]:
    material = distribution["posterior"] >= MATERIAL_MASS
    material_rates = distribution["rates"][material]
    nonmaterial_idx = deterministic_nonmaterial(
        e.context.group, e.source, distribution["rates"], material
    )
    parts = [
        material_rates,
        np.asarray([0.0]),
        np.asarray([m["rate_s_h"] for m in modes]),
        distribution["rates"][nonmaterial_idx],
    ]
    if extra_rates is not None:
        parts.append(np.asarray(extra_rates, float))
    audit_rates = np.unique(np.concatenate(parts))
    surrogate = e.predictions(audit_rates)
    exact = e.predictions(audit_rates, force_direct=True)
    error = surrogate - exact
    exact_num = e.numerators(exact)
    surrogate_num = e.numerators(surrogate)
    material_index = np.searchsorted(audit_rates, material_rates)
    _, all_num = e.evaluate(distribution["rates"])
    assert all_num is not None
    actual = distribution["posterior"] @ all_num
    actual += distribution["posterior"][material] @ (
        exact_num[material_index] - surrogate_num[material_index]
    )
    correction = []
    for sid in e.context.sessions:
        rows = np.flatnonzero(e.session == sid)
        if not len(rows):
            continue
        phases = audit_rates * float(e.age[rows[0]])
        correction.append(
            {
                "session_id": sid,
                "rate_bits": float_bits(audit_rates),
                "phase_bits": float_bits(phases),
                "per_row_correction_ns_digest": array_digest(
                    np.broadcast_to(
                        np.rint(phases[:, None] * 1e9).astype(np.int64), (len(phases), len(rows))
                    ).copy()
                ),
            }
        )
    return {
        "audit_rate_count": len(audit_rates),
        "material_rate_count": len(material_rates),
        "hash_selected_nonmaterial_rate_count": len(nonmaterial_idx),
        "material_posterior_mass": float(np.sum(distribution["posterior"][material])),
        "unmaterial_posterior_mass": float(np.sum(distribution["posterior"][~material])),
        "maximum_absolute_prediction_error_hz": float(np.max(np.abs(error))),
        "rms_prediction_error_hz": float(np.sqrt(np.mean(error * error))),
        "maximum_absolute_phase_s": float(np.max(np.abs(audit_rates[:, None] * e.age[None, :]))),
        "actual_material_session_numerators": actual,
        "surrogate_session_numerators": distribution["posterior"] @ all_num,
        "direct_node_identity": correction,
        "audit_rates": audit_rates,
    }


def score_sessions(context: GroupData, supported: np.ndarray) -> dict[str, Any]:
    losses = (context.unsupported_numerators + supported) / context.session_denominators
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


def pool(scores: dict[str, dict[str, Any]]) -> float:
    return float(sum(GROUP_WEIGHTS[g] * scores[g]["group_score"] for g in GROUPS))


VARIANTS = {
    "coarse_12sigma": (12.0, 0.025),
    "fine_12sigma": (12.0, 0.0125),
    "fine_16sigma": (16.0, 0.0125),
    "repeat_fine_16sigma": (16.0, 0.0125),
}


def evaluate_anchor(contexts: dict[str, GroupData], cache: PhaseStateCache) -> dict[str, Any]:
    pooled_variants = {}
    groups = []
    maximum_tail = 0.0
    maximum_error = cache.provenance()["maximum_adjacent_midpoint_error_hz"]
    exact_groups = {}
    surrogate_groups = {}
    sparse = {}
    source_68739 = None
    for group, c in contexts.items():
        receiver, _ = c.search.receiver_ecef(*ANCHOR)
        accum = {name: np.zeros(len(c.sessions)) for name in VARIANTS}
        actual_acc = np.zeros(len(c.sessions))
        surrogate_acc = np.zeros(len(c.sessions))
        summaries = []
        for source in sorted(np.unique(c.data.source.astype(str))):
            e = SourceEvaluator(c, source, receiver, cache)
            modes = e.modes()
            integrations = {name: e.integrate(*spec) for name, spec in VARIANTS.items()}
            for name, result in integrations.items():
                accum[name] += result["expected_session_numerators"]
            fine = integrations["fine_16sigma"]
            audit = audit_distribution(e, fine, modes)
            actual_acc += audit["actual_material_session_numerators"]
            surrogate_acc += audit["surrogate_session_numerators"]
            maximum_tail = max(maximum_tail, fine["tail_mass"])
            maximum_error = max(maximum_error, audit["maximum_absolute_prediction_error_hz"])
            summary = {
                "source": source,
                "training_observations": len(e.rows),
                "training_tracks": len(e.tracks),
                "maximum_tle_age_h": e.maximum_age_h,
                "modes": modes,
                "posterior_mean_s_h": fine["posterior_mean_s_h"],
                "posterior_sd_s_h": fine["posterior_sd_s_h"],
                "tail_mass": fine["tail_mass"],
                "core_intervals": fine["core_intervals"],
                "exact_audit": {
                    k: v
                    for k, v in audit.items()
                    if k
                    not in (
                        "actual_material_session_numerators",
                        "surrogate_session_numerators",
                        "audit_rates",
                    )
                },
            }
            summaries.append(summary)
            if source == "68739":
                source_68739 = {"group_id": group, **summary}
            if len(e.rows) <= 4 or len(e.tracks) == 1:
                sparse[f"{group}:{source}"] = {"group_id": group, **summary}
        scored = {name: score_sessions(c, value) for name, value in accum.items()}
        actual = score_sessions(c, actual_acc)
        surrogate = score_sessions(c, surrogate_acc)
        exact_groups[group] = actual
        surrogate_groups[group] = surrogate
        for name in VARIANTS:
            pooled_variants.setdefault(name, {})[group] = scored[name]
        groups.append(
            {
                "group_id": group,
                "tau_s": c.tau_s,
                "group_weight": GROUP_WEIGHTS[group],
                "training_observations": len(c.data.y),
                "supported_tracks": len(c.data.weights),
                "unsupported_tracks": sum(a["candidate_id"] is None for a in c.data.assignments),
                "source_count": len(summaries),
                "variants": scored,
                "actual_material_score": actual,
                "surrogate_material_score": surrogate,
                "sources": summaries,
                "session_bindings": c.bindings,
            }
        )
    pooled = {name: pool(scores) for name, scores in pooled_variants.items()}
    actual_score = pool(exact_groups)
    surrogate_score = pool(surrogate_groups)
    gates = {
        "repeated_determinism": abs(pooled["fine_16sigma"] - pooled["repeat_fine_16sigma"])
        <= 1e-12,
        "coarse_fine_convergence": abs(pooled["coarse_12sigma"] - pooled["fine_12sigma"]) <= 1e-6,
        "twelve_sixteen_sigma_convergence": abs(pooled["fine_12sigma"] - pooled["fine_16sigma"])
        <= 1e-6,
        "tail_mass": maximum_tail <= 1e-4,
        "exact_sgp4_error": maximum_error <= ATLAS_ERROR_HZ,
        "exact_surrogate_expected_score": abs(actual_score - pooled["fine_16sigma"]) <= 1e-4,
    }
    return {
        "pooled_scores": pooled,
        "actual_material_expected_score": actual_score,
        "surrogate_material_expected_score": surrogate_score,
        "actual_minus_full_surrogate_expected_score": actual_score - pooled["fine_16sigma"],
        "maximum_tail_mass": maximum_tail,
        "maximum_atlas_validation_error_hz": maximum_error,
        "groups": groups,
        "explicit_source_68739": source_68739,
        "explicit_sparse_sources": sparse,
        "gate": {"criteria": gates, "passed": all(gates.values())},
    }


def stencil_cells() -> list[dict[str, Any]]:
    cells = []
    for north in (-48.828125, 0.0, 48.828125):
        for east in (-48.828125, 0.0, 48.828125):
            lat = ANCHOR[0] + (north / 1000) / 111.32
            lon = ANCHOR[1] + (east / 1000) / (111.32 * math.cos(math.radians(ANCHOR[0])))
            cells.append(
                {
                    "cell_id": f"E{east:+.6f}_N{north:+.6f}",
                    "east_m": east,
                    "north_m": north,
                    "latitude_deg": lat,
                    "longitude_deg": lon,
                }
            )
    return cells


def run_stencil(contexts: dict[str, GroupData], cache: PhaseStateCache) -> dict[str, Any]:
    cells = stencil_cells()
    per_group = {}
    maximum_error = cache.provenance()["maximum_adjacent_midpoint_error_hz"]
    maximum_tail = 0.0
    union_counts = {}
    midpoint_validation_count = 0
    for group, c in contexts.items():
        receivers = {
            cell["cell_id"]: c.search.receiver_ecef(cell["latitude_deg"], cell["longitude_deg"])[0]
            for cell in cells
        }
        midpoint_error, midpoint_count = cache.validate_midpoints(c, list(receivers.values()))
        maximum_error = max(maximum_error, midpoint_error)
        midpoint_validation_count += midpoint_count
        work = {cell["cell_id"]: {} for cell in cells}
        surrogate_acc = {cell["cell_id"]: np.zeros(len(c.sessions)) for cell in cells}
        actual_acc = {cell["cell_id"]: np.zeros(len(c.sessions)) for cell in cells}
        for source in sorted(np.unique(c.data.source.astype(str))):
            union = [np.asarray([0.0])]
            for cell in cells:
                cid = cell["cell_id"]
                e = SourceEvaluator(c, source, receivers[cid], cache)
                modes = e.modes()
                fine = e.integrate(16.0, 0.0125)
                surrogate_acc[cid] += fine["expected_session_numerators"]
                maximum_tail = max(maximum_tail, fine["tail_mass"])
                material = fine["posterior"] >= MATERIAL_MASS
                union.extend((np.asarray([m["rate_s_h"] for m in modes]), fine["rates"][material]))
                work[cid][source] = (e, modes, fine)
            union_rates = np.unique(np.concatenate(union))
            union_counts[f"{group}:{source}"] = len(union_rates)
            for cell in cells:
                cid = cell["cell_id"]
                e, modes, fine = work[cid][source]
                audit = audit_distribution(e, fine, modes, union_rates)
                actual_acc[cid] += audit["actual_material_session_numerators"]
                maximum_error = max(maximum_error, audit["maximum_absolute_prediction_error_hz"])
        per_group[group] = {}
        for cell in cells:
            cid = cell["cell_id"]
            per_group[group][cid] = {
                "surrogate": score_sessions(c, surrogate_acc[cid]),
                "actual": score_sessions(c, actual_acc[cid]),
            }
    rows = []
    for cell in cells:
        cid = cell["cell_id"]
        actual_groups = {g: per_group[g][cid]["actual"] for g in GROUPS}
        surrogate_groups = {g: per_group[g][cid]["surrogate"] for g in GROUPS}
        rows.append(
            {
                **cell,
                "surrogate_score": pool(surrogate_groups),
                "actual_material_score": pool(actual_groups),
                "groups": {g: per_group[g][cid] for g in GROUPS},
            }
        )
    surrogate_winner = min(rows, key=lambda r: (r["surrogate_score"], r["cell_id"]))
    actual_order = sorted(rows, key=lambda r: (r["actual_material_score"], r["cell_id"]))
    actual_winner = actual_order[0]
    gap = float(actual_order[1]["actual_material_score"] - actual_order[0]["actual_material_score"])
    leaveouts = []
    for group, c in contexts.items():
        for excluded_index, sid in enumerate(c.sessions):
            reranks = []
            for row in rows:
                scores = {}
                for g, _other in contexts.items():
                    values = np.asarray(
                        [s["score"] for s in row["groups"][g]["actual"]["sessions"]]
                    )
                    scores[g] = {
                        "group_score": float(np.mean(np.delete(values, excluded_index)))
                        if g == group
                        else float(np.mean(values))
                    }
                reranks.append((pool(scores), row["cell_id"]))
            reranks.sort()
            leaveouts.append(
                {
                    "excluded_group_id": group,
                    "excluded_session_id": sid,
                    "winner_cell_id": reranks[0][1],
                    "winner_score": reranks[0][0],
                    "center_won": reranks[0][1] == "E+0.000000_N+0.000000",
                }
            )
    center = "E+0.000000_N+0.000000"
    gates = {
        "atlas_validation": maximum_error <= ATLAS_ERROR_HZ,
        "tail_mass": maximum_tail <= 1e-4,
        "exact_surrogate_winner_match": actual_winner["cell_id"] == surrogate_winner["cell_id"],
        "center_winner": actual_winner["cell_id"] == center,
        "minimum_winner_gap": gap >= 2e-6,
        "all_leave_one_session_center_reranks": len(leaveouts) == 12
        and all(r["center_won"] for r in leaveouts),
    }
    return {
        "cells": rows,
        "actual_winner_cell_id": actual_winner["cell_id"],
        "surrogate_winner_cell_id": surrogate_winner["cell_id"],
        "winner_gap": gap,
        "maximum_atlas_validation_error_hz": maximum_error,
        "maximum_tail_mass": maximum_tail,
        "per_cell_adjacent_midpoint_validation_count": midpoint_validation_count,
        "cell_union_direct_node_counts": union_counts,
        "leave_one_session_reranks": leaveouts,
        "gate": {"criteria": gates, "passed": all(gates.values())},
    }


def base_output(schema: str, begun: float, cache: PhaseStateCache) -> dict[str, Any]:
    return {
        "schema": schema,
        "complete": True,
        "truth_used": False,
        "held_used": False,
        "elapsed_s": time.perf_counter() - begun,
        "execution": {
            "workers_allowed": 4,
            "workers_used": 1,
            "single_thread_math": True,
            "hard_wall_s": 1800,
            "hard_wall_enforcement": "runner elapsed check plus caller process timeout",
            "external_timeout_invocation": "timeout --signal=TERM 1800s",
        },
        "cache": cache.provenance(),
        "bindings": {
            "plan": digest(PLAN),
            "runner": digest(Path(__file__)),
            "iteration26_runner": digest(I26),
            "iteration23_runner": digest(I23),
            "ds1_runner": digest(DS1),
            "orbit_runner": digest(ORBIT),
            "replay_runner": digest(REPLAY),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("smoke", "stencil"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", type=Path)
    args = parser.parse_args()
    plan = verified_json(PLAN)
    validate_plan(plan)
    begun = time.perf_counter()
    contexts = {g: prepare_group(g) for g in GROUPS}
    if args.stage == "smoke":
        cache = PhaseStateCache(contexts, create=True)
        result = {
            **base_output("ds1-iteration27-phase-cache-smoke/v1", begun, cache),
            "geographic_search_run": False,
            "sealed_stencil_run": False,
            "anchor": {"latitude_deg": ANCHOR[0], "longitude_deg": ANCHOR[1]},
            **evaluate_anchor(contexts, cache),
        }
    else:
        if args.smoke is None:
            raise ValueError("--smoke sealed anchor artifact is required")
        smoke = verified_json(args.smoke)
        if (
            smoke.get("schema") != "ds1-iteration27-phase-cache-smoke/v1"
            or smoke.get("gate", {}).get("passed") is not True
            or smoke.get("bindings", {}).get("plan") != digest(PLAN)
            or smoke.get("bindings", {}).get("runner") != digest(Path(__file__))
            or smoke.get("geographic_search_run") is not False
        ):
            raise ValueError("stencil is locked until this runner's sealed anchor smoke passes")
        cache = PhaseStateCache(contexts, create=False)
        if smoke.get("cache", {}).get("manifest_digest") != cache.provenance()["manifest_digest"]:
            raise ValueError("smoke/cache binding mismatch")
        result = {
            **base_output("ds1-iteration27-phase-cache-stencil/v1", begun, cache),
            "geographic_search_run": True,
            "sealed_stencil_run": True,
            "translation_or_refinement": False,
            "anchor_smoke_digest": digest(args.smoke),
            **run_stencil(contexts, cache),
        }
    result["elapsed_s"] = time.perf_counter() - begun
    if result["elapsed_s"] > float(plan["execution"]["hard_wall_s"]):
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
