#!/usr/bin/env python3
# ruff: noqa: E501
"""Matched DS1 fixed-point causal per-NORAD phase-rate ablation.

For every already-visited DS1 geographic/time pair this tool freezes ordinary
catalogue identities using the original randomized TRAIN masks, then fits only
per-track CFO and a causal, bounded phase-rate per NORAD.  It never moves a
point, expands the pair union, uses held rows to select a nuisance, or reads
location truth.  The historical model uses a quartic local phase surrogate
through cached -2,-1,0,+1,+2-second nodes, then needs exact causal-SGP4 replay
before a result is qualified.  The global receive-time shift still needs the
actual cache's +/-2-second margin; this does not narrow the historical rate
prior itself.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

ROOT = Path(__file__).parents[2]
DS1 = ROOT / "reports/2026_09_24_ds1"
HERE = Path(__file__).parent
CAP = 800.0
NODES = np.asarray((-2.0, -1.0, 0.0, 1.0, 2.0))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest_bytes(value):
    return "sha256:" + hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class RateConfig:
    # Frozen historical FormalOrbitConfig settings, never tuned on DS1.
    phase_rate_sigma_s_h: float = 0.09176615913014215
    phase_rate_bound_s_h: float = 0.25
    measurement_sigma_hz: float = 250.0
    robust_df: float = 4.0
    ar1_rho: float = 0.65
    correlation_time_s: float = 1.0
    max_iterations: int = 40
    convergence: float = 1e-6


@dataclass
class Prepared:
    y: np.ndarray
    train: np.ndarray
    track: np.ndarray
    source: np.ndarray
    session: np.ndarray
    age_h: np.ndarray
    time_s: np.ndarray
    p_nodes: np.ndarray
    v_nodes: np.ndarray
    weights: dict
    assignments: list
    sources: dict


def whiten(values, track, time_s, cfg):
    x = np.asarray(values, float)
    one = x.ndim == 1
    if one:
        x = x[:, None]
    out = np.empty_like(x)
    for key in np.unique(track):
        rows = np.flatnonzero(track == key)
        rows = rows[np.argsort(time_s[rows], kind="stable")]
        out[rows[0]] = x[rows[0]]
        if len(rows) > 1:
            a = cfg.ar1_rho ** (np.maximum(np.diff(time_s[rows]), 0.0) / cfg.correlation_time_s)
            scale = np.sqrt(np.maximum(1 - a * a, 1e-12))
            out[rows[1:]] = (x[rows[1:]] - a[:, None] * x[rows[:-1]]) / scale[:, None]
    return out[:, 0] if one else out


def quartic(nodes, phase_s):
    """Historical five-node local phase surrogate; exact replay is mandatory."""
    phase_s = np.asarray(phase_s, float)
    out = np.zeros((len(phase_s), 3), float)
    for i, knot in enumerate(NODES):
        basis = np.ones(len(phase_s))
        for other in NODES:
            if other != knot:
                basis *= (phase_s - other) / (knot - other)
        out += nodes[:, i] * basis[:, None]
    return out


def doppler(receiver, p, v, search):
    delta = p - receiver
    return (
        -search.REFERENCE_RF_HZ
        / search.LIGHT_KM_S
        * np.sum(delta * v, axis=1)
        / np.linalg.norm(delta, axis=1)
    )


def archive_payload(snapshot_digest):
    """Read exactly the receipt-bound archive as leo; no archive writes occur."""
    program = """import base64,sys
from pathlib import Path
from leo.operations.tle_archive import TleArchiveReader
a=TleArchiveReader(Path('/var/lib/leo/tle'))
s=next((v for v in a.list_snapshots() if v.digest==sys.argv[1]),None)
if s is None: raise ValueError('snapshot absent')
print(base64.b64encode(a.read(s).encode()).decode())"""
    response = subprocess.run(
        ["sudo", "-n", "-u", "leo", sys.executable, "-c", program, snapshot_digest],
        check=True,
        text=True,
        capture_output=True,
    )
    value = base64.b64decode(response.stdout)
    if digest_bytes(value) != snapshot_digest:
        raise ValueError("receipt-bound causal archive digest mismatch")
    return value


def causal_ages(source_info):
    """Find each selected NORAD's physical TLE epoch, not snapshot collection time."""
    from leo.sky.propagation import parse_element_sets

    answer, loaded = {}, {}
    for sid, info in source_info.items():
        text = loaded.setdefault(info["snapshot_digest"], archive_payload(info["snapshot_digest"]))
        catalogue = parse_element_sets(text.decode("ascii"))
        epochs = dict(
            zip(
                map(str, catalogue.satellite_numbers), catalogue.element_epoch_utc_ns(), strict=True
            )
        )
        for norad in info["norads"]:
            if norad not in epochs:
                raise ValueError(f"{sid} NORAD {norad} is absent from causal snapshot")
            answer[(sid, norad)] = int(epochs[norad])
    return answer


def exact_phase_nodes(session, source, time_s, source_info, tau):
    """Construct formal phase nodes with orbit time shifted but Earth fixed.

    The ordinary DS1 cache is valid for global receive-time tau, but cannot be
    reused for this nuisance: advancing the cache also advances Earth rotation.
    These nodes instead use the receipt-bound causal TLE and historical
    `state_arrays` convention for every selected NORAD.
    """
    replay = load(ROOT / "tools/replay_regional_doppler.py", "ds1_orbit_exact_nodes")
    from leo.sky.propagation import parse_element_sets

    p_nodes = np.empty((len(time_s), len(NODES), 3))
    v_nodes = np.empty_like(p_nodes)
    payloads = {}
    for sid, info in source_info.items():
        payload = payloads.setdefault(
            info["snapshot_digest"], archive_payload(info["snapshot_digest"])
        )
        catalogue = parse_element_sets(payload.decode("ascii"))
        index = {str(n): i for i, n in enumerate(catalogue.satellite_numbers)}
        for norad in info["norads"]:
            rows = np.flatnonzero((session == sid) & (source == norad))
            if not len(rows):
                continue
            for node_index, phase_s in enumerate(NODES):
                p, v, valid = replay.state_arrays(
                    catalogue,
                    [index[norad]],
                    info["capture_start_utc_ns"],
                    time_s[rows],
                    orbit_time_s=float(phase_s),
                    clock_s=float(tau),
                )
                if len(valid) != 1:
                    raise ValueError("causal exact phase-node propagation failed")
                p_nodes[rows, node_index] = p[0]
                v_nodes[rows, node_index] = v[0]
    return p_nodes, v_nodes


def prepare(engine, lat, lon, tau):
    """Obtain ordinary candidate identity only from the DS1 TRAIN scorer."""
    _, _, all_assignments = engine.profile(lat, lon, np.asarray([tau]), False, True)
    selected = {(a["session_id"], a["track_id"]): a for a in all_assignments[0]}
    fields = {key: [] for key in ("y", "train", "track", "source", "session", "time")}
    weights, assignments, source_info = {}, [], {}
    for session in engine.sessions:
        receipt_path = Path(session["cache_path"]) / "cache_receipt.json"
        receipt = json.loads(receipt_path.read_text())
        evidence = receipt["prepared_evidence"]
        norads = set()
        for track in session["tracks"]:
            choice = selected[(session["session_id"], track["track_id"])]
            candidate = choice["candidate_id"]
            if candidate is None:
                continue
            name = f"{session['session_id']}:{track['track_id']}"
            fields["y"].append(track["measured"])
            fields["train"].append(track["train"])
            fields["track"].append(np.full(len(track["times"]), name, object))
            fields["source"].append(np.full(len(track["times"]), candidate, object))
            fields["session"].append(np.full(len(track["times"]), session["session_id"], object))
            fields["time"].append(track["times"])
            weights[name] = track["weight"]
            assignments.append(
                {
                    "session_id": session["session_id"],
                    "track_id": track["track_id"],
                    "candidate_id": candidate,
                }
            )
            norads.add(candidate)
        source_info[session["session_id"]] = {
            "snapshot_digest": evidence["snapshot_digest"],
            "capture_start_utc_ns": int(evidence["start_utc_ns"]),
            "norads": sorted(norads),
        }
    if not fields["y"]:
        raise ValueError("no ordinary TRAIN-supported candidates")
    source = np.concatenate(fields["source"])
    track = np.concatenate(fields["track"])
    ages = causal_ages(source_info)
    age_h = np.empty(len(source))
    for sid, info in source_info.items():
        session_mask = np.char.startswith(track.astype(str), sid + ":")
        for norad in info["norads"]:
            age_h[session_mask & (source == norad)] = (
                info["capture_start_utc_ns"] - ages[(sid, norad)]
            ) / 3.6e12
    if np.any(age_h < 0) or not np.all(np.isfinite(age_h)):
        raise ValueError("causal TLE age is invalid")
    all_time = np.concatenate(fields["time"])
    all_session = np.concatenate(fields["session"])
    p_nodes, v_nodes = exact_phase_nodes(all_session, source, all_time, source_info, tau)
    return Prepared(
        np.concatenate(fields["y"]),
        np.concatenate(fields["train"]),
        track,
        source,
        all_session,
        age_h,
        all_time,
        p_nodes,
        v_nodes,
        weights,
        assignments,
        source_info,
    )


def fit_fixed_rates(data, receiver, search, cfg=None):
    """Fixed-point version of historical formal per-NORAD phase-rate profile."""
    if cfg is None:
        cfg = RateConfig()
    fitting = np.flatnonzero(data.train)
    src_labels, src = np.unique(data.source, return_inverse=True)
    trk_labels, trk = np.unique(data.track, return_inverse=True)

    def robust_profile(rates):
        """Profile CFO at a rate vector in the historical AR(1)-t geometry."""
        phase = data.age_h * rates[src]
        base = doppler(receiver, quartic(data.p_nodes, phase), quartic(data.v_nodes, phase), search)
        residual = data.y[fitting] - base[fitting]
        whitened = whiten(residual, data.track[fitting], data.time_s[fitting], cfg)
        white_one = whiten(np.ones(len(fitting)), data.track[fitting], data.time_s[fitting], cfg)
        offsets = np.asarray(
            [
                np.dot(
                    white_one[data.track[fitting] == label], whitened[data.track[fitting] == label]
                )
                / np.dot(
                    white_one[data.track[fitting] == label], white_one[data.track[fitting] == label]
                )
                for label in trk_labels
            ]
        )
        innovation = whitened - white_one * offsets[trk[fitting]]
        z = innovation / cfg.measurement_sigma_hz
        return 0.5 * (cfg.robust_df + 1) * np.sum(np.log1p(z * z / cfg.robust_df)) + 0.5 * np.sum(
            (rates / cfg.phase_rate_sigma_s_h) ** 2
        )

    optimized = minimize(
        robust_profile,
        np.zeros(len(src_labels)),
        method="L-BFGS-B",
        bounds=[(-cfg.phase_rate_bound_s_h, cfg.phase_rate_bound_s_h)] * len(src_labels),
        options={"maxiter": cfg.max_iterations * 20, "ftol": 1e-12, "gtol": cfg.convergence},
    )
    rates = np.asarray(optimized.x, float)

    def score(scored_rates):
        phase = data.age_h * scored_rates[src]
        base = doppler(receiver, quartic(data.p_nodes, phase), quartic(data.v_nodes, phase), search)
        # Re-profile a plain TRAIN mean CFO.  This is precisely the DS1
        # evaluation basis, rather than the robust optimizer's internal CFO.
        cfo = np.asarray(
            [np.mean((data.y - base)[(data.track == label) & data.train]) for label in trk_labels]
        )
        error = data.y - base - cfo[trk]

        def rms(mask, label):
            values = error[(data.track == label) & mask]
            return float(np.sqrt(np.mean(values**2)))

        train = {label: rms(data.train, label) for label in trk_labels}
        held = {label: rms(~data.train, label) for label in trk_labels}
        denom = sum(data.weights.values())
        train_loss = (
            sum(data.weights[key] * min((train[key] / CAP) ** 2, 1) for key in data.weights) / denom
        )
        held_loss = (
            sum(data.weights[key] * min((held[key] / CAP) ** 2, 1) for key in data.weights) / denom
        )
        return train_loss, held_loss, cfo, phase

    train_loss, held_loss, scored_offsets, phase = score(rates)
    null_train, null_held, null_offsets, null_phase = score(np.zeros_like(rates))
    # The rate nuisance is selected on TRAIN only.  Keeping its null value when
    # it cannot improve the DS1 objective preserves the matched baseline arm.
    rejected_by_train = train_loss > null_train + 1e-12
    if rejected_by_train:
        rates, train_loss, held_loss, scored_offsets, phase = (
            np.zeros_like(rates),
            null_train,
            null_held,
            null_offsets,
            null_phase,
        )
    return {
        "training_capped_loss": float(train_loss),
        "held_capped_loss": float(held_loss),
        "training_capped_rms_hz": float(CAP * np.sqrt(train_loss)),
        "held_capped_rms_hz": float(CAP * np.sqrt(held_loss)),
        "iterations": int(optimized.nit),
        "converged": bool(optimized.success),
        "optimizer_message": str(optimized.message),
        "optimizer_objective": float(optimized.fun),
        "source_count": len(src_labels),
        "track_count": len(trk_labels),
        "historical_rate_boundary_count": int(
            np.sum(np.abs(rates) >= cfg.phase_rate_bound_s_h - 1e-8)
        ),
        "max_surrogate_phase_s": float(np.max(np.abs(phase))),
        "exact_replay_required": True,
        "rate_fit_rejected_by_train": rejected_by_train,
        "track_offsets_hz": {
            str(k): float(v) for k, v in zip(trk_labels, scored_offsets, strict=True)
        },
        "rate_corrections_s_h": {str(k): float(v) for k, v in zip(src_labels, rates, strict=True)},
    }


def exact_replay_gate(data, receiver, search, tau, rates, tolerance_hz=0.2):
    """Compare the local phase surrogate with exact causal SGP4 at fitted rates.

    Orbit phase changes SGP4 propagation time while Earth rotation remains at
    receive+global-tau time.  This is intentionally distinct from moving along
    the DS1 receive-time cache, and follows the historical formal verifier.
    """
    replay = load(ROOT / "tools/replay_regional_doppler.py", "ds1_orbit_exact_replay")
    from leo.sky.propagation import parse_element_sets

    approximate = np.empty(len(data.y))
    phase = np.empty(len(data.y))
    exact = np.empty(len(data.y))
    seen = np.zeros(len(data.y), bool)
    payloads = {}
    for sid, info in data.sources.items():
        payload = payloads.setdefault(
            info["snapshot_digest"], archive_payload(info["snapshot_digest"])
        )
        catalogue = parse_element_sets(payload.decode("ascii"))
        index = {str(n): i for i, n in enumerate(catalogue.satellite_numbers)}
        session_rows = np.char.startswith(data.track.astype(str), sid + ":")
        for norad in info["norads"]:
            rows = np.flatnonzero(session_rows & (data.source == norad))
            if not len(rows):
                continue
            rate = float(rates[norad])
            correction = float(data.age_h[rows[0]] * rate)
            p, v, valid = replay.state_arrays(
                catalogue,
                [index[norad]],
                info["capture_start_utc_ns"],
                data.time_s[rows],
                orbit_time_s=correction,
                clock_s=float(tau),
            )
            if len(valid) != 1:
                raise ValueError("exact fitted causal propagation failed")
            exact[rows] = doppler(receiver, p[0], v[0], search)
            phase[rows] = correction
            approximate[rows] = doppler(
                receiver,
                quartic(data.p_nodes[rows], np.full(len(rows), correction)),
                quartic(data.v_nodes[rows], np.full(len(rows), correction)),
                search,
            )
            seen[rows] = True
    if not np.all(seen):
        raise ValueError("exact replay did not cover every selected row")
    error = approximate - exact
    return {
        "schema": "ds1-causal-rate-exact-sgp4-gate/v1",
        "observations": int(len(error)),
        "tolerance_hz": float(tolerance_hz),
        "rms_hz": float(np.sqrt(np.mean(error**2))),
        "maximum_absolute_hz": float(np.max(np.abs(error))),
        "p99_absolute_hz": float(np.quantile(np.abs(error), 0.99)),
        "maximum_phase_s": float(np.max(np.abs(phase))),
        "passed": bool(np.max(np.abs(error)) <= tolerance_hz),
        "earth_rotation": "fixed at receive_time_plus_global_tau, not orbit-phase-shifted",
    }


def sealed(path):
    if (
        hashlib.sha256(path.read_bytes()).hexdigest()
        != path.with_suffix(".sha256").read_text().strip().split()[0]
    ):
        raise ValueError(f"unsealed input: {path}")
    return json.loads(path.read_text())


def run_case(case_id, prior, pair_limit=None):
    dataset = sealed(DS1 / "dataset.json")
    case = next(row for row in dataset["cases"] if row["case_id"] == case_id)
    arm_path = DS1 / "inference" / f"{case_id}__{prior}.json"
    arm = sealed(arm_path)
    if "failure" in arm:
        return {"case_id": case_id, "prior": prior, "failure": arm["failure"]}
    runner = load(DS1 / "run.py", "ds1_orbit_runner")
    _, engine = runner.make_engine(case)
    cache_root = runner.CACHE_ROOTS[case["group_id"]]
    for session in engine.sessions:
        session["cache_path"] = str(cache_root / session["session_id"])
    pairs = list(arm["visited_pairs"])
    if pair_limit is not None:
        pairs = sorted(
            pairs, key=lambda r: (r["training_capped_loss"], abs(r["tau_s"]), r["tau_s"])
        )[:pair_limit]
    begun, rows = time.monotonic(), []
    for pair in pairs:
        data = prepare(engine, pair["latitude_deg"], pair["longitude_deg"], pair["tau_s"])
        receiver, _ = engine.search.receiver_ecef(pair["latitude_deg"], pair["longitude_deg"])
        rows.append(
            {
                **pair,
                "status": "completed",
                "ordinary_train_assignments": data.assignments,
                "fit": fit_fixed_rates(data, receiver, engine.search),
            }
        )
    complete = [row for row in rows if row["status"] == "completed"]
    winner = (
        min(
            complete,
            key=lambda r: (
                r["fit"]["training_capped_loss"],
                abs(r["tau_s"]),
                r["tau_s"],
                r["latitude_deg"],
                r["longitude_deg"],
            ),
        )
        if complete
        else None
    )
    if winner is not None:
        # Replay uses the sealed TRAIN-selected winner only.  It does not feed
        # back into point, identity, rate, or held-observation selection.
        prepared = prepare(engine, winner["latitude_deg"], winner["longitude_deg"], winner["tau_s"])
        receiver, _ = engine.search.receiver_ecef(winner["latitude_deg"], winner["longitude_deg"])
        winner["exact_replay_gate"] = exact_replay_gate(
            prepared,
            receiver,
            engine.search,
            winner["tau_s"],
            winner["fit"]["rate_corrections_s_h"],
        )
        # Deliberately introduced after TRAIN-only pair/rate selection.
        reference = (37.84903264307456, -122.4856541910174)
        winner["reference_error_km"] = engine.search.haversine_km(
            (winner["latitude_deg"], winner["longitude_deg"]), reference
        )
    return {
        "schema": "ds1-fixed-point-causal-per-norad-rate/v1",
        "complete": True,
        "case_id": case_id,
        "prior": prior,
        "rows": rows,
        "winner": winner,
        "elapsed_s": time.monotonic() - begun,
        "configuration": asdict(RateConfig()),
        "geographic_pair_universe": "all frozen DS1 shared-time pairs"
        if pair_limit is None
        else "TRAIN-ranked deterministic DS1 smoke subset",
        "association": "ordinary catalogue selection at the same pair, using TRAIN only",
        "rate_definition": "per-NORAD TLE phase-rate correction in s/h, phase=causal_TLE_age_h*rate; bound +/-0.25 s/h",
        "not_an_epoch_shift": True,
        "held_used_for_fit": False,
        "truth_used_for_fit": False,
        "reference_role": "post-inference evaluation only",
        "bindings": {
            "dataset": digest(DS1 / "dataset.json"),
            "shared_time_arm": digest(arm_path),
            "source": digest(Path(__file__)),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--prior", required=True, choices=("sacramento", "reno"))
    parser.add_argument("--pair-limit", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("output already exists")
    result = run_case(args.case, args.prior, args.pair_limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
