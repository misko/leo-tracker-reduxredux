"""Qualify Schur BVLS on real, frozen native-joint owner sets and on AArch64."""

import argparse
import gzip
import json
import os
import resource
import shutil
import struct
import subprocess
from hashlib import sha256
from pathlib import Path
from statistics import median
from time import perf_counter
from unittest.mock import patch

import numpy as np

from .. import corpus
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km
from ..variants import embedded_solve as small
from ..variants import joint_orbits, native_lean
from ..variants import robust_em as lean
from ..variants import robust_orbit_fit as exact
from . import native_joint_trial, native_lean_eval, secant_full
from .native_lean_eval import _write_predictions
from .phase_confirmation import frozen_inputs

REPORT = native_joint_trial.REPORT.parent.parent / "factors/embedded-solve"
RUNNER = Path(__file__).with_name("embedded_solve_runner.c")
CASES = native_lean_eval.SMOKE
METHOD = "embedded_schur_fit"
STOCK = "native_joint_orbits"
BOUNDARY = "Recorded native-joint fixed orbit owners through the final bounded position fit"


def synthetic():
    """Exercise east/north, both signs of orbit bounds and inactive phases."""
    rng = np.random.default_rng(7295)
    phase = [23, -18, 2, -4, 1, 0, 3]
    rows = []
    for orbit in range(len(phase)):
        for lane in range(4):
            t = np.linspace(1 + lane * 2, 40 + lane, 41 + orbit)
            drift = (t - 20) / 100
            rf = (10.8 + 0.53 * lane + 0.01 * orbit) * 1e9
            xy = rng.normal(size=(len(t), 2)) * 85
            gradient = rng.normal(size=len(t)) * 200
            y = xy @ [4, -3] + gradient * phase[orbit] + 350 * (rf / 1e9 - 11.5)
            y += 40 * lane - 20 * drift + rng.normal(size=len(t)) * 15
            alias = orbit % 3 - 1
            track = lean.Track(t, y, rf, lane, True, drift, np.eye(len(t)) / 150)
            arc = lean.Arc(
                track,
                np.array([orbit]),
                (y + alias * lean.PERIOD)[None],
                xy[None],
                gradient[None],
                np.zeros(1),
                np.zeros(1),
            )
            rows.append(lean.Assignment(arc, 0, alias, lane / 3, 1))
    return rows, len(phase), 1.25


def prepare(ident, item, archive):
    packet, files = native_lean_eval.request(item, "native")
    inputs = {key: dict(packet[key], path=str(path)) for key, path in files.items()}
    proj_start = perf_counter()
    clock, lanes, _ = native_lean.peak_lanes(
        inputs["native"], packet["probe_limit"], packet["cutoff"]
    )
    config = json.loads(native_lean._load(inputs["track_config"], native_lean.BLOCK_BYTES))[
        "config"
    ]
    document = dict(
        clock,
        tracks=native_lean.graph_projection(lanes, config),
        catalog_timestamp_ns=packet["catalog_timestamp"],
    )
    observation = native_lean.projection_digest(document)
    catalogue = native_lean._load(inputs["catalogue"], native_lean.CATALOGUE_LIMIT).decode("ascii")
    if any(archive[f"{kind}_sha256"] != item[kind]["sha256"] for kind in ("native", "catalog")):
        raise ValueError(f"{ident} differs from the sealed native-joint inputs")
    if archive["observation_sha256"] != observation or archive["tile"] != packet["offer"]:
        raise ValueError(f"{ident} did not reproduce the native-joint observation or tile")
    captured = {}
    original = exact.refine

    def lock_owners(owners, start, tile, region, half, arm):
        fitted, details = original(owners, start, tile, region, half, arm)
        captured[arm] = (owners, start, tile, region, half, fitted, details)
        return fitted, details

    with patch.object(exact, "refine", lock_owners):
        result = joint_orbits.infer(document, packet["offer"], catalogue)
    if tuple(captured) != ARMS or result["status"] != archive["result"]["status"]:
        raise ValueError(f"{ident} has no comparable measured owner set")
    for arm in ARMS:
        new, old = result["arms"][arm], archive["result"]["arms"][arm]
        if distance_km(new["forced_latlon"], old["forced_latlon"]) > 1e-7:
            raise ValueError(f"{ident}/{arm} changed the stock joint endpoint")
        if abs(new["rf_rms_hz"] - old["rf_rms_hz"]) > 1e-5:
            raise ValueError(f"{ident}/{arm} changed the stock RF prediction")
    owners = captured["c0"][0]
    if owners is not captured["fitted_c"][0]:
        raise ValueError("calibration must share the exact final selected owner rows")
    inventory = []
    for owner in owners:
        tr = owner.arc.track
        inventory.append(
            dict(
                orbit_index=owner.orbit,
                alias=owner.alias,
                chosen=owner.winner,
                rf_hz=tr.rf,
                lane=tr.lane,
                t0=float(tr.t[0]),
                t1=float(tr.t[-1]),
                count=len(tr.t),
                loss=owner.loss,
                margin=owner.margin,
                basis_sha256=sha256(small._design(owner, 11).tobytes()).hexdigest(),
                whitening_sha256=sha256(tr.whiten.tobytes()).hexdigest(),
            )
        )
    lock = dict(
        id=ident,
        native_sha256=item["native"]["sha256"],
        catalog_sha256=item["catalog"]["sha256"],
        observation_sha256=observation,
        tile=packet["offer"],
        owners=inventory,
    )
    return captured, result, lock, perf_counter() - proj_start


def refinement(case, arm, solve):
    owners, _, tile, region, half, _, _ = case
    n = len(tile.positions_km)
    fits = []

    def linear(rows):
        stats = small.statistics(rows, half, arm)
        estimate = solve(stats)
        fits.append(dict(rows=rows, stats=stats, estimate=estimate, alpha=0.0))
        return small.fit(rows, stats, estimate, n)

    start = linear(owners)
    fits[-1]["alpha"] = 1.0
    chosen, radius = start.state, start.radius_km
    score, rms = exact._loss(owners, tile, region, chosen)
    for _ in range(exact.RELINEARIZATIONS):
        proposal = linear(exact._recenter(owners, tile, region, chosen))
        radius = proposal.radius_km
        for alpha in exact.BACKTRACK:
            trial = exact._blend(chosen, proposal.state, alpha)
            loss, error = exact._loss(owners, tile, region, trial)
            if loss + 1e-8 < score:
                chosen, score, rms = trial, loss, error
                fits[-1]["alpha"] = alpha
                break
        else:
            break
    return lean.Fit(chosen, rms, score, radius), fits


def packet(region, fits):
    first = fits[0]["stats"]
    width, n = len(first.rhs), len(first.orbit_ids)
    header = struct.pack("<III9d", width, n, len(fits), *region.origin, *region.frame[:2].flat)
    matrices = []
    for entry in fits:
        s = entry["stats"]
        if first.orbit_ids != s.orbit_ids:
            raise ValueError("fixed ownership changed between bounded solves")
        arrays = (s.gram, s.rhs, s.orbits, s.bounds)
        matrices.append(
            struct.pack("<d", entry["alpha"])
            + b"".join(a.astype("<f8", copy=False).tobytes() for a in arrays)
        )
    return header + b"".join(matrices)


def runners(work):
    qemu, cross = shutil.which("qemu-aarch64"), shutil.which("aarch64-linux-gnu-gcc")
    result = {}
    for arch, cc, launch in (("host", "cc", []), ("aarch64", cross, [qemu])):
        if cc is None or None in launch:
            continue
        exe = work / arch
        subprocess.run(
            [
                cc,
                *small.BUILD_FLAGS,
                "-fstack-usage",
                "-static",
                str(small.SOURCE),
                str(RUNNER),
                "-lm",
                "-o",
                str(exe),
            ],
            check=True,
            cwd=work,
        )
        result[arch] = [*launch, str(exe)]
    return result


def execute(work, commands, payload, repeat):
    for arch, cmd in commands.items():
        rss = work / f"{arch}.rss"
        receipts = []
        for _ in range(5):
            process = subprocess.run(
                ["/usr/bin/time", "-f", "%M", "-o", str(rss), *cmd, str(repeat)],
                input=payload,
                capture_output=True,
                check=True,
                timeout=30,
            )
            value = json.loads(process.stdout)
            value["process_max_rss_kib"] = int(rss.read_text())
            receipts.append(value)
        final = receipts[0]
        if any(trial["coefficients"] != final["coefficients"] for trial in receipts):
            raise ValueError(f"{arch} runs did not reproduce coefficients")
        final["median_solve_wall_s"] = median(trial["mean_solve_wall_s"] for trial in receipts)
        final["max_process_rss_kib"] = max(trial["process_max_rss_kib"] for trial in receipts)
        final["repetitions_per_process_per_linearization"] = repeat
        final["process_trials"] = len(receipts)
        yield arch, final


def benchmark(rows, n, half, arm, solve, repeat=31):
    times = {"scipy_full_fit": [], "schur_full_fit": []}

    def compact():
        stats = small.statistics(rows, half, arm)
        return small.fit(rows, stats, solve(stats), n)

    modes = (("scipy_full_fit", lambda: lean.fit(rows, n, half, arm)), ("schur_full_fit", compact))
    for index in range(repeat):
        for key, call in modes if index % 2 == 0 else modes[::-1]:
            started = perf_counter()
            call()
            times[key].append(perf_counter() - started)
    return {key: median(samples) for key, samples in times.items()} | {"paired_trials": repeat}


def comparison(rows, n, half, arm, stats, solution):
    control = lean.fit(rows, n, half, arm)
    result = small.fit(rows, stats, solution, n)
    basis = small.coefficients(control.state, stats)
    actual = solution.coefficients
    if not np.allclose(actual, basis, rtol=1e-7, atol=1e-6):
        raise ValueError(f"Schur coefficient parity failed for {arm}: {actual - basis}")
    return dict(
        rows=stats.row_count,
        orbit_count=len(stats.orbit_ids),
        receiver_width=len(stats.rhs),
        maximum_coefficient_delta=float(max(abs(actual - basis))),
        active_lower=np.flatnonzero(actual == -stats.bounds).tolist(),
        active_upper=np.flatnonzero(actual == stats.bounds).tolist(),
        scipy_active_lower=np.flatnonzero(basis == -stats.bounds).tolist(),
        scipy_active_upper=np.flatnonzero(basis == stats.bounds).tolist(),
        rms_delta_hz=result.rms_hz - control.rms_hz,
        score_delta=result.score - control.score,
        radius_delta_km=result.radius_km - control.radius_km,
        scaled_kkt=solution.optimality,
        bound_updates=solution.bound_updates,
        dense_whitened_matrix_bytes=8 * (stats.row_count + len(actual)) * len(actual),
        arrowhead_bytes=sum(a.nbytes for a in (stats.gram, stats.rhs, stats.orbits, stats.bounds)),
    )


def run_case(ident, item, stock, work, out, solve, commands, repeat):
    captured, stock_result, owners, upstream_s = prepare(ident, item, stock)
    save_json(out / f"{ident}-owners.json", owners)
    result = dict(stock_result, arms={})
    result["boundary"] = BOUNDARY
    report = dict(upstream_wall_s=upstream_s, arms={})
    for arm, case in captured.items():
        rows, _, tile, region, half, expected, details = case
        n = len(tile.positions_km)
        started = perf_counter()
        fit, fits = refinement(case, arm, solve)
        elapsed = perf_counter() - started
        checks = [comparison(e["rows"], n, half, arm, e["stats"], e["estimate"]) for e in fits]
        final = small.coefficients(fit.state, fits[0]["stats"])
        basis = small.coefficients(expected.state, fits[0]["stats"])
        if not np.allclose(final, basis, atol=1e-6, rtol=1e-7):
            raise ValueError(f"{ident}/{arm} changes the final nonlinear solution")
        if sum(e["alpha"] > 0 for e in fits[1:]) != details["accepted_steps"]:
            raise ValueError(f"{ident}/{arm} changes the number of accepted refinements")
        at = region.site(fit.state.xy)[1]
        result["arms"][arm] = dict(
            stock_result["arms"][arm],
            forced_latlon=at,
            latlon=at if result["status"] == "ok" else None,
            rf_rms_hz=fit.rms_hz,
            frequency_score=fit.score,
            radius_km=fit.radius_km,
            c_hz_per_ghz=fit.state.c_hz_per_ghz,
        )
        raw = packet(region, fits)
        name = f"{ident}-{arm}-stats.bin.gz"
        write(out / name, gzip.compress(raw, mtime=0))
        platforms = dict(execute(work, commands, raw, repeat))
        for value in platforms.values():
            if not np.allclose(value["coefficients"], final, atol=1e-7, rtol=1e-9):
                raise ValueError(f"{ident}/{arm} compiled replay differs from host fixed-owner fit")
            state = small.state(fits[0]["stats"], np.array(value["coefficients"]), n)
            score, rms = exact._loss(rows, tile, region, state)
            value.update(
                postscored_rms_hz=rms,
                postscored_frequency_score=score,
                endpoint_shift_from_stock_m=1000
                * distance_km(value["latlon"], stock_result["arms"][arm]["forced_latlon"]),
            )
        report["arms"][arm] = dict(
            linearizations=checks,
            accepted_step_fractions=[e["alpha"] for e in fits],
            platforms=platforms,
            stats_file=name,
            fixed_owner_fit_wall_s=elapsed,
            fitted_coefficients=final.tolist(),
            scipy_coefficients=basis.tolist(),
            rms_delta_hz=fit.rms_hz - expected.rms_hz,
            score_delta=fit.score - expected.score,
            benchmark_initial_fit=benchmark(rows, n, half, arm, solve),
        )
    digest = sha256(encoded(owners)).hexdigest()
    row = {
        k: owners[k]
        for k in ("id", "native_sha256", "catalog_sha256", "observation_sha256", "tile")
    }
    common = dict(row, input_sha256=digest)
    return (
        dict(common, method=METHOD, result=result),
        dict(common, method=STOCK, result=stock_result),
        report,
    )


def score(candidates, stocks, report):
    refs = {row["id"]: row for row in corpus.references("roof16")}
    for new, old in zip(candidates, stocks, strict=True):
        ident = new["id"]
        ref = refs[ident]
        for arm in ARMS:
            at = new["result"]["arms"][arm]["forced_latlon"]
            stock = old["result"]["arms"][arm]["forced_latlon"]
            arm_report = report[ident]["arms"][arm]
            arm_report.update(
                horizontal_error_km=distance_km(at, ref["truth"]),
                stock_error_km=distance_km(stock, ref["truth"]),
                stock_endpoint_delta_m=1000 * distance_km(at, stock),
                original_v5_error_km={
                    role: (ref["reference"][role].get(arm) or ref["reference"][role]["shape"])[
                        "error_km"
                    ]
                    for role in ROLES
                },
            )


def run(work, out, repeat):
    work, out = (local_output(path) for path in (work, out))
    for path in (work, out):
        path.mkdir(parents=True, exist_ok=True)
    library = work / "kernel.so"
    small.compile_library(library)
    solve, commands = small.Kernel(library), runners(work)
    src = tuple(
        map(
            Path,
            (
                small.SOURCE,
                small.__file__,
                RUNNER,
                __file__,
                joint_orbits.__file__,
                lean.__file__,
                exact.__file__,
                native_lean.__file__,
            ),
        )
    )
    sources = {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in src}
    origin = native_joint_trial.REPORT
    lock = json.loads((origin / "prediction-lock.json").read_bytes())
    secant_full._verify_files(origin, lock["files"])
    with gzip.open(origin / "positions.jsonl.gz", "rt") as stream:
        archive = {r["id"]: r for r in map(json.loads, stream) if r["id"] in CASES}
    if archive.keys() != set(CASES):
        raise ValueError("native-joint archive does not cover both predeclared recordings")
    inputs = frozen_inputs()
    candidates, stocks, measurements = [], [], {}
    for ident in CASES:
        candidate, stock, check = run_case(
            ident, inputs[ident], archive[ident], work, out, solve, commands, repeat
        )
        candidates.append(candidate)
        stocks.append(stock)
        measurements[ident] = check
        print(ident, candidate["result"]["status"], flush=True)
    rows, n, half = synthetic()
    synthetic_check = {}
    region = exact.Region(
        "synthetic", (0, 0), np.array([6378.137, 0, 0]), np.array([[0, 1, 0], [0, 0, 1]])
    )
    for arm in ARMS:
        stats = small.statistics(rows, half, arm)
        solution = solve(stats)
        check = comparison(rows, n, half, arm, stats, solution)
        name = f"synthetic-{arm}-stats.bin.gz"
        raw = packet(region, [dict(stats=stats, alpha=1.0)])
        write(out / name, gzip.compress(raw, mtime=0))
        for value in (platforms := dict(execute(work, commands, raw, repeat))).values():
            if not np.allclose(value["coefficients"], solution.coefficients, atol=1e-7, rtol=1e-9):
                raise ValueError(f"{arm} differing compiled replay on synthetic active-set stress")
        synthetic_check[arm] = dict(check, platforms=platforms, stats_file=name)
        width = len(stats.rhs)
        if not (
            any(i >= width for i in check["active_lower"])
            and any(i >= width for i in check["active_upper"])
            and any(i < 2 for i in (*check["active_lower"], *check["active_upper"]))
        ):
            raise ValueError("synthetic stress did not activate position and both phase limits")
    _write_predictions(out / "positions.jsonl.gz", candidates)
    _write_predictions(out / "stock-positions.jsonl.gz", stocks)
    score(candidates, stocks, measurements)
    save_json(
        out / "measurements.json",
        dict(
            recordings=measurements,
            synthetic=synthetic_check,
            process_max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            pinned_cpus=sorted(os.sched_getaffinity(0)),
            compiler={
                arch: subprocess.check_output([cc, "--version"], text=True).splitlines()[0]
                for arch, cc in (("host", "cc"), ("aarch64", "aarch64-linux-gnu-gcc"))
                if arch in commands
            },
            compiler_stack_records={p.name: p.read_text() for p in sorted(work.glob("*.su"))},
        ),
    )
    save_json(
        out / "source-lock.json",
        dict(
            files=sources,
            stock_prediction_lock_sha256=sha256(
                (origin / "prediction-lock.json").read_bytes()
            ).hexdigest(),
        ),
    )
    names = [
        "positions.jsonl.gz",
        "stock-positions.jsonl.gz",
        "measurements.json",
        "source-lock.json",
    ]
    names += [p.name for p in sorted(out.glob("*-stats.bin.gz"))]
    names += [f"{ident}-owners.json" for ident in CASES]
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=CASES,
            source_lock_sha256=sha256((out / "source-lock.json").read_bytes()).hexdigest(),
            files={name: sha256((out / name).read_bytes()).hexdigest() for name in names},
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--out", default=REPORT, type=Path)
    parser.add_argument("--repeat", default=5000, type=int)
    args = parser.parse_args()
    run(args.work, args.out, args.repeat)


if __name__ == "__main__":
    main()
