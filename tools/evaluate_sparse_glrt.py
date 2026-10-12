"""Bounded existing-recording sparse likelihood replay; no RF collection.

Prepare uses public read-only storage ports. Run uses only the frozen local bundle.
The output is a research composite score, not a calibrated position posterior.
"""

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.glrt_frequency_input import frequency_evidence
from leo.analysis.sparse_glrt_likelihood import SparseConfig, fit_sparse
from leo.sky.frames import (
    ecef_to_enu_matrix,
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    look_angles,
    teme_to_ecef,
)
from leo.sky.propagation import ElementSetCatalogue, propagate_grid
from leo.sky.sampling import SamplingGrid


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def local_output(path):
    resolved = path.resolve()
    protected = Path("/mnt/qnap01")
    if resolved == protected or protected in resolved.parents:
        raise ValueError("research output must be local; QNAP is read-only")
    return path


def states(catalogue, utc_ns):
    grid = SamplingGrid(tuple(int(t) for t in utc_ns), 0, 1.0)
    result = propagate_grid(catalogue, grid)
    jd, fr = julian_day_from_utc_ns(utc_ns)
    p, v = teme_to_ecef(
        result.position_teme_km, result.velocity_teme_km_s, greenwich_mean_sidereal_time_rad(jd, fr)
    )
    return p, v, result.usable


def prepare(args):
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.short_window import ShortWindowReader

    local_output(args.output)
    started = time.monotonic()
    store = FastScanStore(args.bulk_root)
    report = store.detail(args.run_id)
    if report["session_id"] != args.session_id:
        raise ValueError("run does not belong to requested recording")
    payload = store.tracking_input_path(args.run_id).read_bytes()
    document = json.loads(payload)
    if document["source"]["session_id"] != args.session_id:
        raise ValueError("tracking export identity mismatch")
    evidence, rf, metadata = frequency_evidence(document)
    inventory = store.source(args.session_id, document["source"]["input_manifest_sha256"])
    manifest = ShortWindowReader(Path(inventory["segments"][0]["path"])).manifest
    targets = manifest.configuration["targets"]
    # The exported CFO includes any nominal pilot-center / actual tuner offset.
    target_by_key = {(t["channel"], t["edge"]): t for t in targets}
    nominal_corrections = [
        target_by_key[(p["channel"], p["edge"])]["rf_center_hz"] - p["actual_rf_hz"]
        for p in document["source"]["probes"]
    ]
    catalogue = causal_catalogue(TleArchiveReader(args.tle_root), metadata["causal_cutoff_utc_ns"])
    from leo.contracts.sky import ObserverSiteV1

    if getattr(args, "latitude", None) is None or getattr(args, "longitude", None) is None:
        raise ValueError("explicit latitude and longitude required for the search origin")
    site = ObserverSiteV1(
        latitude_deg=args.latitude,
        longitude_deg=args.longitude,
        altitude_m=args.altitude,
        label="Explicit recording reference / local search origin",
    )
    observer = geodetic_to_ecef_km(site.latitude_deg, site.longitude_deg, site.altitude_m)
    enu = ecef_to_enu_matrix(site.latitude_deg, site.longitude_deg)
    start = metadata["anchor_utc_ns"]
    coarse_t = start + np.arange(0, metadata["duration_s"] + 5, 5) * 1e9
    p, v, usable = states(catalogue.catalogue, coarse_t.astype(np.int64))
    _, elevation, _, _ = look_angles(p, v, observer, enu)
    coarse_unusable_count = int((~usable).sum())
    # 5 s knots, conservative 1.5 deg/s motion, plus 5 km regional/clock guard.
    keep = usable & (np.max(elevation, axis=1) >= -6.0)
    indexes = np.flatnonzero(keep)
    bank = catalogue.catalogue
    selected = ElementSetCatalogue(
        tuple(bank.names[i] for i in indexes),
        tuple(bank.satellite_numbers[i] for i in indexes),
        tuple(bank.satellites[i] for i in indexes),
    )
    unique_times, inverse = np.unique(evidence.time_s, return_inverse=True)
    times_ns = start + np.rint(unique_times * 1e9).astype(np.int64)
    p, v, usable = states(selected, times_ns)
    failed = [selected.satellite_numbers[i] for i in np.flatnonzero(~usable)]
    if failed:
        raise ValueError(f"selected satellite propagation failures: {failed}")
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "tracking-input.json").write_bytes(payload)
    np.savez_compressed(
        args.output / "orbit-bank.npz",
        position=p,
        velocity=v,
        time_s=unique_times,
        inverse=inverse,
        nominal_correction_hz=nominal_corrections,
        rf_hz=rf,
        norad=np.array(selected.satellite_numbers),
    )
    metadata.update(
        input_sha256=hashlib.sha256(payload).hexdigest(),
        site=site.model_dump(mode="json"),
        targets=targets,
        catalogue_count=len(bank),
        bank_count=len(selected),
        coarse_unusable_count=coarse_unusable_count,
        snapshot_count=catalogue.snapshot_count,
        satellite_provenance=[catalogue.provenance[i] for i in indexes],
        scope="fixed altitude; stationary receiver; recorded RF hypothesis; zero RF c; no drift",
        numerical_frame="TEME/ECEF: UTC approximates UT1; polar motion neglected",
        preparation_seconds=time.monotonic() - started,
    )
    metadata["orbit_bank_sha256"] = hashlib.sha256(
        (args.output / "orbit-bank.npz").read_bytes()
    ).hexdigest()
    write_json(args.output / "input-receipt.json", metadata)
    print(
        json.dumps(
            {
                k: metadata[k]
                for k in (
                    "receiver_factors",
                    "distinct_candidates",
                    "duplicate_candidates_removed",
                    "duration_s",
                    "catalogue_count",
                    "bank_count",
                    "snapshot_count",
                    "preparation_seconds",
                )
            }
        ),
        flush=True,
    )


def coordinates(site, east_m, north_m):
    lat = np.deg2rad(site["latitude_deg"])
    e2 = 6.6943799901413165e-3
    den = 1 - e2 * np.sin(lat) ** 2
    meridian = 6378137.0 * (1 - e2) / den**1.5
    prime = 6378137.0 / np.sqrt(den)
    return (
        site["latitude_deg"] + np.rad2deg(north_m / meridian),
        site["longitude_deg"] + np.rad2deg(east_m / (prime * np.cos(lat))),
    )


def prediction(bank, evidence, site, point, time_offset_s=0.0):
    lat, lon = coordinates(site, *point)
    receiver = geodetic_to_ecef_km(lat, lon, site["altitude_m"])
    # Small timing sensitivity only; main run uses direct SGP4 at recorded times.
    p = bank["position"] + time_offset_s * bank["velocity"]
    v = bank["velocity"]
    _, el, _, rate = look_angles(p, v, receiver, ecef_to_enu_matrix(lat, lon))
    inverse = bank["inverse"]
    predicted = -rate.T[inverse] * bank["rf_hz"][:, None] / 299792.458
    predicted += bank["nominal_correction_hz"][:, None]
    return predicted, el.T[inverse] >= 0


def nuisance_seeds(evidence, predicted, visible, count=2):
    """Deterministic broad offset modes from all candidate/satellite residuals.

    Used only to propose starts; all evidence enters the final score. Freeze this
    same seed inventory for the full spatial comparison.
    """
    bins = np.arange(-600000.0, 605000.0, 5000.0)
    modes = []
    for group in range(int(evidence.group.max()) + 1):
        rows = np.flatnonzero(evidence.group == group)
        hist = np.zeros(len(bins) - 1)
        for k in range(evidence.frequency_hz.shape[1]):
            delta = evidence.frequency_hz[rows, k, None] - predicted[rows]
            weight = (
                evidence.candidate_weight[rows, k, None]
                * evidence.signal_probability[rows, None]
                * visible[rows]
            )
            hist += np.histogram(delta, bins, weights=weight)[0]
        smooth = np.convolve(hist, [1, 2, 3, 2, 1], mode="same")
        chosen = []
        for i in np.argsort(smooth)[::-1]:
            if all(abs(i - j) >= 6 for j in chosen):
                chosen.append(int(i))
            if len(chosen) == count:
                break
        modes.append([float((bins[j] + bins[j + 1]) / 2) for j in chosen])
    seeds = [[row[k] for row in modes] for k in range(count)]
    # Independent band histograms can lock onto opposite orbital-Doppler modes.
    # Include equal-band starts for each receiver, but fit the offsets freely.
    for reference_band in (0, 1):
        aligned = seeds[0].copy()
        for lower in range(0, len(aligned) - 1, 2):
            aligned[lower : lower + 2] = [seeds[0][lower + reference_band]] * 2
        if aligned not in seeds:
            seeds.append(aligned)
    return seeds + [[0.0] * len(modes)]


def run(args):
    local_output(args.output)
    if not 0 <= args.points <= 1000 or not 0 <= args.refine <= 50 or args.seconds <= 0:
        raise ValueError("invalid bounded replay parameters")
    started = time.monotonic()
    metadata = json.loads((args.bundle / "input-receipt.json").read_text())
    payload = (args.bundle / "tracking-input.json").read_bytes()
    if hashlib.sha256(payload).hexdigest() != metadata["input_sha256"]:
        raise ValueError("input digest changed")
    if (
        hashlib.sha256((args.bundle / "orbit-bank.npz").read_bytes()).hexdigest()
        != metadata["orbit_bank_sha256"]
    ):
        raise ValueError("orbit digest changed")
    document = json.loads(payload)
    evidence, _, _ = frequency_evidence(document, uniform_marks=args.uniform_marks)
    bank = dict(np.load(args.bundle / "orbit-bank.npz"))
    site = metadata["site"]
    config = SparseConfig(
        scale_hz=args.scale_hz,
        satellite_penalty=args.penalty,
        maximum_satellites=args.satellites,
        iterations=args.iterations,
        em_iterations=args.em_iterations,
    )
    initial_prediction, initial_visible = prediction(bank, evidence, site, (0, 0))
    seeds = (
        json.loads(args.seed_file.read_text())
        if args.seed_file
        else nuisance_seeds(evidence, initial_prediction, initial_visible, count=args.seeds)
    )
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = dict(
        config=asdict(config),
        seeds=seeds,
        random_seed=args.seed,
        radius_m=5000,
        random_points=args.points,
        budget_seconds=args.seconds,
        input_digest=metadata["input_sha256"],
        orbit_digest=metadata["orbit_bank_sha256"],
        source_digests={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                Path(__file__),
                Path("src/leo/analysis/sparse_glrt_likelihood.py"),
                Path("src/leo/analysis/glrt_frequency_input.py"),
            ]
        },
        uniform_marks=args.uniform_marks,
        score_kind="penalized conditional composite log-likelihood ratio",
        rf_calibration_c=0,
        drift_hz_s=0,
        altitude_m=site["altitude_m"],
        time_offset_s=0,
        completed=False,
    )
    write_json(args.output / "protocol.json", receipt)
    rows, cache = [], {}

    def evaluate(point, kind):
        if time.monotonic() - started > args.seconds:
            raise TimeoutError("bounded replay budget exhausted")
        point = np.asarray(point, dtype=float)
        if np.linalg.norm(point) > 5000.0001:
            point *= 5000 / np.linalg.norm(point)
        key = tuple(np.round(point, 5))
        if key in cache:
            return cache[key]
        t = time.monotonic()
        predicted, visible = prediction(bank, evidence, site, point)
        result = fit_sparse(evidence, predicted, visible, seeds, config)
        result.update(
            east_m=float(point[0]),
            north_m=float(point[1]),
            distance_m=float(np.linalg.norm(point)),
            kind=kind,
            latitude_deg=coordinates(site, *point)[0],
            longitude_deg=coordinates(site, *point)[1],
            norad=[int(bank["norad"][i]) for i in result["active"]],
            runtime_s=time.monotonic() - t,
        )
        rows.append(result)
        cache[key] = result
        with (args.output / "evaluations.jsonl").open("a") as f:
            f.write(json.dumps(result, allow_nan=False) + "\n")
        print(
            json.dumps(
                {k: result[k] for k in ("kind", "distance_m", "score", "norad", "runtime_s")}
            ),
            flush=True,
        )
        return result

    try:
        evaluate((0, 0), "reference")
        rng = np.random.default_rng(args.seed)
        radii, angles = (
            5000 * np.sqrt(rng.random(args.points)),
            rng.uniform(0, 2 * np.pi, args.points),
        )
        for r, angle in zip(radii, angles, strict=True):
            evaluate((r * np.cos(angle), r * np.sin(angle)), "random")
        if args.points:
            for angle in np.arange(8) * np.pi / 4:
                evaluate((5000 * np.cos(angle), 5000 * np.sin(angle)), "boundary")
        # Bounded spatial pattern refinement of best sampled basin. Report the
        # achieved mesh, boundary status, and no claim of a global minimum.
        best = max(rows, key=lambda r: r["score"])
        step = 1000.0
        for _ in range(args.refine):
            origin = np.array([best["east_m"], best["north_m"]])
            neighbors = [
                evaluate(origin + step * np.array(direction), "refine")
                for direction in ((1, 0), (-1, 0), (0, 1), (0, -1))
            ]
            updated = max([best, *neighbors], key=lambda r: r["score"])
            if updated is best:
                step *= 0.5
            best = updated
        receipt.update(completed=True, refinement_mesh_m=step)
    except TimeoutError as error:
        receipt["stop_reason"] = str(error)
    receipt["elapsed_seconds"] = time.monotonic() - started
    receipt["evaluations"] = len(rows)
    if rows:
        best = max(rows, key=lambda r: r["score"])
        receipt.update(
            best=best,
            reference=rows[0],
            reference_rank=1 + sum(r["score"] > rows[0]["score"] for r in rows[1:]),
            best_on_boundary=best["distance_m"] > 4999.0,
            improvement_over_reference=best["score"] - rows[0]["score"],
        )
    write_json(args.output / "result.json", receipt)
    plot(args.output, rows)


def plot(output, rows):
    if not rows:
        return
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 7), constrained_layout=True)
    x, y = np.array([(r["east_m"], r["north_m"]) for r in rows]).T / 1000
    loss = np.array([rows[0]["score"] - r["score"] for r in rows])
    scatter = ax.scatter(x, y, c=loss, cmap="coolwarm", s=48)
    best = int(np.argmin(loss))
    ax.scatter([0], [0], marker="*", s=230, color="black", label="Sausalito reference")
    ax.scatter(
        [x[best]],
        [y[best]],
        marker="x",
        s=160,
        color="limegreen",
        linewidths=3,
        label="Best evaluated point",
    )
    ax.add_patch(plt.Circle((0, 0), 5, fill=False, color="gray", linestyle="--"))
    ax.set(
        xlabel="East of reference (km)",
        ylabel="North of reference (km)",
        title="Sparse GLRT frequency score: 5 km neighborhood",
        aspect="equal",
    )
    ax.legend(loc="upper left")
    fig.colorbar(scatter, ax=ax, label="Penalized loss relative to reference (lower is better)")
    fig.savefig(output / "position-score.png", dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    p.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    p.add_argument("--session-id", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--latitude", type=float, required=True)
    p.add_argument("--longitude", type=float, required=True)
    p.add_argument("--altitude", type=float, default=0.0)
    r = sub.add_parser("run")
    r.add_argument("--bundle", type=Path, required=True)
    r.add_argument("--output", type=Path, required=True)
    r.add_argument("--points", type=int, default=32)
    r.add_argument("--seed", type=int, default=20261012)
    r.add_argument("--seeds", type=int, default=1)
    r.add_argument("--seed-file", type=Path)
    r.add_argument("--penalty", type=float, default=8.0)
    r.add_argument("--iterations", type=int, default=5)
    r.add_argument("--em-iterations", type=int, default=20)
    r.add_argument("--satellites", type=int, default=8)
    r.add_argument("--scale-hz", type=float, default=1500.0)
    r.add_argument("--seconds", type=float, default=900.0)
    r.add_argument("--refine", type=int, default=6)
    r.add_argument("--uniform-marks", action="store_true")
    args = parser.parse_args()
    (prepare if args.command == "prepare" else run)(args)


if __name__ == "__main__":
    main()
