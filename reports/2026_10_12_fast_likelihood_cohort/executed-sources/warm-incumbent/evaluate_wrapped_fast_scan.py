"""Bounded alias-aware all-candidate scan fitting and matched RF-c ablations."""

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.analysis.glrt_orbit_phase import OrbitPhasePort
from leo.analysis.wrapped_glrt_likelihood import (
    PILOT_ALIAS_HZ,
    WrappedConfig,
    circular,
    fit_wrapped,
    smooth_visibility,
)
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km, look_angles
from tools.evaluate_sparse_glrt import coordinates, local_output, write_json


def load_bundle(root):
    metadata = json.loads((root / "input-receipt.json").read_text())
    payload = (root / "tracking-input.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != metadata["input_sha256"]:
        raise ValueError("changed input export")
    if (
        hashlib.sha256((root / "orbit-bank.npz").read_bytes()).hexdigest()
        != metadata["orbit_bank_sha256"]
    ):
        raise ValueError("changed orbital bank")
    data, _, receipt = frequency_evidence(json.loads(payload), alias_period_hz=PILOT_ALIAS_HZ)
    return data, dict(np.load(root / "orbit-bank.npz")), metadata, receipt


def predictions(bank, site, point):
    lat, lon = coordinates(site, *point)
    receiver = geodetic_to_ecef_km(lat, lon, site["altitude_m"])
    _, el, _, rate = look_angles(
        bank["position"], bank["velocity"], receiver, ecef_to_enu_matrix(lat, lon)
    )
    inverse = bank["inverse"]
    frequency = -rate.T[inverse] * bank["rf_hz"][:, None] / 299792.458
    frequency += bank["nominal_correction_hz"][:, None]
    return frequency, smooth_visibility(el.T[inverse])


def load_phase_bank(bundle, bank):
    receipt = json.loads((bundle / "orbit-phase-receipt.json").read_text())
    payload = (bundle / "orbit-phase-bank.npz").read_bytes()
    if hashlib.sha256(payload).hexdigest() != receipt["digest"]:
        raise ValueError("changed phase ephemerides")
    phases = dict(np.load(bundle / "orbit-phase-bank.npz"))
    if not np.array_equal(phases["norad"], bank["norad"]):
        raise ValueError("phase bank changes candidate identity inventory")
    return phases, receipt


def phase_provider(phase_bank, bank, data, site, point):
    latitude, longitude = coordinates(site, *point)
    return OrbitPhasePort(
        phase_bank["position"],
        phase_bank["velocity"],
        phase_bank["nodes_s"],
        data.time_s,
        bank["rf_hz"],
        latitude,
        longitude,
        site["altitude_m"],
    )


def offset_seeds(data, prediction, opportunity):
    bins = np.linspace(-PILOT_ALIAS_HZ / 2, PILOT_ALIAS_HZ / 2, 457)
    modes = []
    for group in range(int(data.group.max()) + 1):
        rows = np.flatnonzero(data.group == group)
        hist = np.zeros(len(bins) - 1)
        for k in range(data.frequency_hz.shape[1]):
            delta = circular(data.frequency_hz[rows, k, None] - prediction[rows])
            weight = (
                data.candidate_weight[rows, k, None]
                * data.signal_probability[rows, None]
                * opportunity[rows]
            )
            hist += np.histogram(delta, bins, weights=weight)[0]
        smooth = np.convolve(hist, [1, 2, 3, 2, 1], mode="same")
        chosen = []
        for i in np.argsort(smooth)[::-1]:
            if all(abs(i - j) > 8 for j in chosen):
                chosen.append(int(i))
            if len(chosen) == 2:
                break
        modes.append([(bins[i] + bins[i + 1]) / 2 for i in chosen])
    seeds = [[m[k] for m in modes] for k in range(2)]
    aligned = seeds[0].copy()
    for lower in range(0, len(aligned) - 1, 2):
        aligned[lower + 1] = aligned[lower]
    seeds.append(aligned)
    return seeds


def restrict_candidates(bank, phase_bank, seeds, pool, metadata):
    """Restrict a diagnostic to one frozen, provenance-bound candidate pool."""
    if (
        pool["input_digest"] != metadata["input_sha256"]
        or pool["orbit_digest"] != metadata["orbit_bank_sha256"]
    ):
        raise ValueError("candidate pool belongs to a different recording or orbit bank")
    numbers = list(map(int, pool["norad"]))
    lookup = {int(n): i for i, n in enumerate(bank["norad"])}
    if not numbers or len(set(numbers)) != len(numbers) or any(n not in lookup for n in numbers):
        raise ValueError("distinct candidate identities from the original bank required")
    indices = np.array(sorted(lookup[n] for n in numbers))
    remap = {int(s): i for i, s in enumerate(indices)}
    converted = []
    for seed in seeds:
        if any(s not in remap for s in seed["active"]):
            raise ValueError("pool must retain every seeded satellite")
        delta = seed.get("satellite_phase_s")
        converted.append(
            dict(
                seed,
                active=[remap[s] for s in seed["active"]],
                satellite_phase_s=None if delta is None else np.asarray(delta)[indices].tolist(),
            )
        )
    local_bank = dict(bank)
    for key in ("position", "velocity", "norad"):
        local_bank[key] = bank[key][indices]
    local_phase = None if phase_bank is None else dict(phase_bank)
    if local_phase is not None:
        for key in ("position", "velocity", "norad"):
            local_phase[key] = phase_bank[key][indices]
    return local_bank, local_phase, converted, indices


def retain_nested_zero_fit(fitted, zero):
    """A free-c profile must retain every feasible zero-c solution without refitting."""
    if fitted["score"] >= zero["score"]:
        return fitted
    return dict(
        zero,
        beta=zero["beta"] + [0.0],
        labels=zero["labels"] + ["coefficient-hz-per-ghz"],
        coefficient_enabled=True,
        converged=False,
        inherited_zero_c_baseline=True,
        starts=fitted["starts"],
        attempted_free_c_score=fitted["score"],
    )


def validate_initialization_checkpoint(previous, expected):
    for key in ("config", "seeds", "input_digest", "orbit_digest", "source_digests"):
        if previous[key] != expected[key]:
            raise ValueError("initialization checkpoint protocol changed")
    if len(previous["completed_starts"]) > len(expected["seeds"]):
        raise ValueError("initialization checkpoint exceeds frozen starts")
    return previous


def initialize(args):
    data, bank, meta, receipt = load_bundle(args.bundle)
    pred, opp = predictions(bank, meta["site"], (0, 0))
    histogram_seeds = offset_seeds(data, pred, opp)
    from leo.analysis.glrt_shape_initialization import shape_seeds
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.application.scanner_trajectory import project_scanner_candidates
    from tools.fast_scan_standard_pipeline import load_tracking_input

    document = json.loads((args.bundle / "tracking-input.json").read_text())
    source = load_tracking_input(document)
    prepared = prepare_position_windows(source)
    points = {p.source_group_id: p for p in project_scanner_candidates(source)}
    lookup = {
        (p["visit_index"], p["receiver_id"], p["probe_index"]): i
        for i, p in enumerate(document["source"]["probes"])
    }
    tracks = []
    for track in prepared.bootstrap_tracks:
        track_points = [points[prepared.observations.window_ids[i]] for i in track]
        tracks.append([lookup[p.visit_index, p.receiver_id, p.probe_index] for p in track_points])
    provider = None
    phase_receipt = None
    timing = None
    if args.phase:
        phase_bank, phase_receipt = load_phase_bank(args.bundle, bank)
        provider = phase_provider(phase_bank, bank, data, meta["site"], (0, 0))
        if args.relative_phase_sigma_s is not None:
            pred, opp, timing, _ = provider.predict(0.0)
    shapes, proposals = shape_seeds(
        data, pred, opp, tracks, timing=timing, phase_sigma_s=args.relative_phase_sigma_s or 1.0
    )
    seeds = shapes + histogram_seeds[:1]
    if args.phase:
        seeds = [dict(seed, phase_s=phase) for seed in shapes for phase in args.phase_starts]
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=args.resume)
    if (args.output / "initialization.json").exists():
        raise FileExistsError("completed initialization already exists")
    config = WrappedConfig(
        scale_hz=1000.0,
        iterations=3,
        em_iterations=35,
        maximum_satellites=40,
        nuisance_iterations=30,
        relative_phase_sigma_s=args.relative_phase_sigma_s,
        nuisance_solver=args.nuisance_solver,
    )
    started = time.monotonic()
    checkpoint = dict(
        config=asdict(config),
        seeds=seeds,
        input_digest=meta["input_sha256"],
        orbit_digest=meta["orbit_bank_sha256"],
        completed_starts=[],
        source_digests={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path("src/leo/analysis/wrapped_glrt_likelihood.py"),
                Path("src/leo/analysis/glrt_orbit_phase.py"),
                Path("src/leo/analysis/glrt_shape_initialization.py"),
                Path("src/leo/analysis/sparse_glrt_likelihood.py"),
            )
        },
    )
    progress_path = args.output / "initialization-progress.json"
    if args.resume and progress_path.exists():
        previous = json.loads(progress_path.read_text())
        checkpoint = validate_initialization_checkpoint(previous, checkpoint)
    for seed in seeds[len(checkpoint["completed_starts"]) :]:
        fit = fit_wrapped(
            data, pred, opp, bank["rf_hz"], [seed], config=config, orbit_provider=provider
        )
        checkpoint["completed_starts"].append(fit)
        write_json(progress_path, checkpoint)
        print(
            json.dumps(
                dict(
                    completed_starts=len(checkpoint["completed_starts"]),
                    total_starts=len(seeds),
                    score=fit["score"],
                )
            ),
            flush=True,
        )
    if not checkpoint["completed_starts"]:
        raise ValueError("at least one initialization start required")
    result = dict(max(checkpoint["completed_starts"], key=lambda x: x["score"]))
    result["starts"] = [
        {
            k: fit[k]
            for k in ("score", "beta", "phase_s", "satellite_phase_s", "active", "converged")
        }
        for fit in checkpoint["completed_starts"]
    ]
    ranked = sorted(result["starts"], key=lambda x: -x["score"])[:2]
    write_json(
        args.output / "initialization.json",
        dict(
            config=asdict(config),
            seeds=seeds,
            result=result,
            selected_seeds=ranked,
            evidence_receipt=receipt,
            input_digest=meta["input_sha256"],
            orbit_digest=meta["orbit_bank_sha256"],
            elapsed_seconds=time.monotonic() - started,
            scope=(
                "response-dependent numerical starts at the common search origin; "
                "no reference error enters fitting"
            ),
            shape_proposals=proposals,
            bootstrap_tracks=tracks,
            phase_receipt=phase_receipt,
        ),
    )
    print(
        json.dumps(
            dict(
                initial_score=result["score"],
                beta=result["beta"],
                satellites=len(result["active"]),
                elapsed_seconds=time.monotonic() - started,
            )
        ),
        flush=True,
    )


def sweep(args):
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    data, bank, meta, receipt = load_bundle(args.bundle)
    initial = json.loads(args.initial.read_text())
    if (
        initial["input_digest"] != meta["input_sha256"]
        or initial["orbit_digest"] != meta["orbit_bank_sha256"]
    ):
        raise ValueError("initialization belongs to different scan")
    common_seeds = [
        dict(
            beta=x["beta"],
            active=x["active"],
            phase_s=x.get("phase_s", 0.0),
            satellite_phase_s=x.get("satellite_phase_s"),
            weights=x.get("weights"),
            coefficient_hz_ghz=x.get("coefficient_hz_ghz", 0.0),
        )
        for x in initial["selected_seeds"]
    ]
    phase_bank = None
    phase_receipt = None
    if args.phase:
        phase_bank, phase_receipt = load_phase_bank(args.bundle, bank)
    full_indices = np.arange(len(bank["norad"]))
    catalogue_count = len(full_indices)
    pool_digest = None
    if args.candidate_pool is not None:
        payload = args.candidate_pool.read_bytes()
        pool_digest = hashlib.sha256(payload).hexdigest()
        bank, phase_bank, common_seeds, full_indices = restrict_candidates(
            bank, phase_bank, common_seeds, json.loads(payload), meta
        )
    config = WrappedConfig(
        scale_hz=args.scale_hz,
        iterations=args.iterations,
        maximum_satellites=40,
        em_iterations=60,
        nuisance_iterations=args.nuisance_iterations,
        relative_phase_sigma_s=args.relative_phase_sigma_s,
        nuisance_solver=args.nuisance_solver,
    )
    protocol = dict(
        config=asdict(config),
        seeds=common_seeds,
        random_seed=args.seed,
        input_digest=meta["input_sha256"],
        orbit_digest=meta["orbit_bank_sha256"],
        evidence_receipt=receipt,
        site=meta["site"],
        phase_receipt=phase_receipt,
        completed=False,
        catalogue_count=catalogue_count,
        candidate_norad=bank["norad"].tolist(),
        candidate_pool_digest=pool_digest,
        candidate_scope=(
            "conditional local diagnostic on a frozen candidate pool"
            if pool_digest is not None
            else "complete prepared visible catalogue"
        ),
        model=(
            "wrapped Cauchy / uniform circular clutter; smooth horizon opportunity; "
            "band offsets and receiver drift"
        ),
        ablation=(
            "same observations, candidate universe, nuisance priors and budgets; c=0 vs fitted-c"
        ),
        budget_seconds=args.seconds,
        source_digests={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path("src/leo/analysis/wrapped_glrt_likelihood.py"),
                Path("src/leo/analysis/sparse_glrt_likelihood.py"),
            )
        },
    )
    write_json(args.output / "protocol.json", protocol)
    rows = []
    cache = {}

    def evaluate(point, kind):
        if time.monotonic() - started > args.seconds:
            raise TimeoutError("bounded scan slice exhausted")
        point = np.asarray(point, float)
        if np.linalg.norm(point) > 5000:
            point *= 5000 / np.linalg.norm(point)
        key = tuple(np.round(point, 6))
        if key in cache:
            return cache[key]
        pred, opp = predictions(bank, meta["site"], point)
        provider = (
            phase_provider(phase_bank, bank, data, meta["site"], point)
            if phase_bank is not None
            else None
        )
        arms = {}
        for enabled in (False, True):
            seeds = []
            for seed in common_seeds:
                beta = list(seed["beta"])
                if enabled:
                    beta.append(seed["coefficient_hz_ghz"])
                seeds.append(
                    dict(
                        beta=beta,
                        active=seed["active"],
                        phase_s=seed["phase_s"],
                        satellite_phase_s=seed["satellite_phase_s"],
                        weights=seed["weights"],
                    )
                )
            fit = fit_wrapped(
                data,
                pred,
                opp,
                bank["rf_hz"],
                seeds,
                coefficient=enabled,
                config=config,
                orbit_provider=provider,
            )
            if enabled:
                fit = retain_nested_zero_fit(fit, arms["zero-c"])
            fit["norad"] = [int(bank["norad"][i]) for i in fit["active"]]
            fit["full_catalogue_indices"] = [int(full_indices[i]) for i in fit["active"]]
            arms["fitted-c" if enabled else "zero-c"] = fit
        row = dict(
            east_m=float(point[0]),
            north_m=float(point[1]),
            distance_m=float(np.linalg.norm(point)),
            latitude_deg=coordinates(meta["site"], *point)[0],
            longitude_deg=coordinates(meta["site"], *point)[1],
            kind=kind,
            arms=arms,
        )
        rows.append(row)
        cache[key] = row
        with (args.output / "evaluations.jsonl").open("a") as f:
            f.write(json.dumps(row) + "\n")
        print(
            json.dumps(
                dict(
                    kind=kind,
                    distance_m=row["distance_m"],
                    scores={k: v["score"] for k, v in arms.items()},
                    counts={k: len(v["active"]) for k, v in arms.items()},
                )
            ),
            flush=True,
        )
        return row

    try:
        evaluate((0, 0), "reference")
        if args.positions_json is not None:
            for point in json.loads(args.positions_json.read_text()):
                if len(point) != 2 or not np.isfinite(point).all():
                    raise ValueError("finite east/north pairs required")
                evaluate(point, "specified-audit")
        if args.probe_grid:
            for east, north in (
                (1, 0),
                (-1, 0),
                (0, 1),
                (0, -1),
                (1, 1),
                (1, -1),
                (-1, 1),
                (-1, -1),
            ):
                evaluate((1000 * east, 1000 * north), "local-grid-probe")
        rng = np.random.default_rng(args.seed)
        radii = 5000 * np.sqrt(rng.random(args.points))
        angles = rng.uniform(0, 2 * np.pi, args.points)
        for radius, angle in zip(radii, angles, strict=True):
            evaluate((radius * np.cos(angle), radius * np.sin(angle)), "random")
        if args.points:
            for angle in np.arange(8) * np.pi / 4:
                evaluate((5000 * np.cos(angle), 5000 * np.sin(angle)), "boundary")
        for arm in ("zero-c", "fitted-c"):
            best = max(rows, key=lambda x: x["arms"][arm]["score"])
            step = 1000.0
            for _ in range(args.refine):
                origin = np.array([best["east_m"], best["north_m"]])
                neighbors = [
                    evaluate(origin + step * np.array(d), f"refine-{arm}")
                    for d in ((1, 0), (-1, 0), (0, 1), (0, -1))
                ]
                new = max([best, *neighbors], key=lambda x: x["arms"][arm]["score"])
                if new is best:
                    step *= 0.5
                best = new
        protocol["completed"] = True
    except TimeoutError as error:
        protocol["stop_reason"] = str(error)
    protocol.update(elapsed_seconds=time.monotonic() - started, evaluations=len(rows))
    if rows:
        protocol["reference"] = rows[0]
        protocol["best"] = {
            k: max(rows, key=lambda x: x["arms"][k]["score"]) for k in ("zero-c", "fitted-c")
        }
    write_json(args.output / "result.json", protocol)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("initialize")
    a.add_argument("--bundle", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--phase", action="store_true")
    a.add_argument("--phase-starts", type=float, nargs="+", default=[-2.0, 0.0, 2.0])
    a.add_argument("--resume", action="store_true")
    a.add_argument("--relative-phase-sigma-s", type=float)
    a.add_argument("--nuisance-solver", choices=("irls", "lbfgs"), default="irls")
    b = sub.add_parser("sweep")
    b.add_argument("--bundle", type=Path, required=True)
    b.add_argument("--initial", type=Path, required=True)
    b.add_argument("--output", type=Path, required=True)
    b.add_argument("--points", type=int, default=12)
    b.add_argument("--refine", type=int, default=3)
    b.add_argument("--iterations", type=int, default=5)
    b.add_argument("--nuisance-iterations", type=int, default=50)
    b.add_argument("--scale-hz", type=float, default=250.0)
    b.add_argument("--seconds", type=float, default=900.0)
    b.add_argument("--seed", type=int, default=20261012)
    b.add_argument("--phase", action="store_true")
    b.add_argument("--relative-phase-sigma-s", type=float)
    b.add_argument("--candidate-pool", type=Path)
    b.add_argument("--nuisance-solver", choices=("irls", "lbfgs"), default="irls")
    b.add_argument("--positions-json", type=Path)
    b.add_argument("--probe-grid", action="store_true")
    args = p.parse_args()
    (initialize if args.command == "initialize" else sweep)(args)


if __name__ == "__main__":
    main()
