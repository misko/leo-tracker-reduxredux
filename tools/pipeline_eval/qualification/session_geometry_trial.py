"""Seal the search and run the whole-visit static-position Doppler trial."""

import argparse
import time
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json
from ..scoring import validate_result
from ..variants import prague_transfer
from ..variants import session_geometry as model
from ..variants.compact_tile_interior import margin
from . import prague_transfer_trial as archive
from . import session_geometry_simulation as simulation
from .full_v5_check import _sha

OUT = ROOT / "reports/2026_11_19_receiver_screening/native-receiver/session-geometry"
PRAGUE_ORIGIN = prague_transfer.CITY
PLAN = "study-plan.json"
PREFLIGHT = "trial-lock.json"
LOCK = "prediction-lock.json"
PREDICTIONS = "predictions.json"
INDIVIDUAL = "per-capture.json"
RESOURCES = "resources.json"
PURPOSE = {
    "prague": "Author-selected spectral peaks and paired CTU ECEF of unaudited availability",
    "simulation": "Independent spherical-inertial circular LEO, rotated into WGS84 ECEF",
}


def load_ctu(source):
    receipts = archive.source_receipts(source, ("outputs.zip",))
    captures, members = [], []
    with ZipFile(source / "outputs.zip") as document:
        selected = archive.recordings(document, archive.members(document))
    for stamp, (_, path, digest, arcs) in selected:
        ident = stamp.strftime("%Y%m%dT%H%M%SZ")
        captures.append(model.Capture(ident, stamp.date().isoformat(), arcs))
        members.append(dict(id=ident, sha256=digest, member=str(path)))
    return captures, members, receipts


def observation_hash(capture):
    digest = sha256()
    for arc in capture.arcs:
        for array in (arc.times_s, arc.frequency_hz, arc.position_km, arc.velocity_km_s):
            digest.update(np.asarray(array, dtype="<f8").tobytes())
    return digest.hexdigest()


def position_result(point, tile, boundary, training_gain_hz, center=False):
    point = point.tolist()
    face = margin(point, tile)
    reason = None
    if not center and face <= model.GRID_KM / 2:
        reason = "grid_fit_at_region_face"
    elif not center and training_gain_hz < model.BIN_HZ:
        reason = "training_gain_below_one_bin"
    arms = dict(
        c0=dict(latlon=point if reason is None else None, forced_latlon=point),
        fitted_c=dict(
            latlon=None,
            status="unavailable",
            reason="one_rf_calibration_column_in_free_intercept_span",
        ),
    )
    result = dict(
        status="ok" if reason is None else "withheld",
        reason=reason,
        boundary=boundary,
        metrics=dict(face_km=face, training_gain_hz=training_gain_hz),
        arms=arms,
    )
    validate_result(result)
    return result


def fit_visit(train_grids, points):
    pooled = {key: np.mean([grid[key] for grid in train_grids], axis=0) for key in train_grids[0]}
    matches = {method: points[np.argmin(cost)] for method, cost in pooled.items()}
    per_capture = [points[np.argmin(grid["phase-clock"])] for grid in train_grids]
    component_median = np.median(per_capture, axis=0)
    median_idx = np.argmin(np.sum((points - component_median) ** 2, axis=-1))
    center_idx = len(points) // 2
    matches.update(median=points[median_idx], center=points[center_idx])
    for method, point in matches.items():
        objective = pooled.get(method, pooled["phase-clock"])
        idx = np.flatnonzero(np.all(points == point, axis=1))[0]
        rms_hz = float(np.sqrt(objective[idx]))
        yield method, point, rms_hz, float(np.sqrt(objective[center_idx]) - rms_hz)


def evaluate(name, captures, offers, origin, hashes):
    predictions, individuals, resources = [], [], []
    partitions = {
        visit: [i for i, capture in enumerate(captures) if capture.visit == visit]
        for visit in sorted({capture.visit for capture in captures})
    }
    if len(partitions) != 2:
        raise ValueError("the static-position trial needs two independent visits")
    for condition, tile in offers.items():
        points = model.candidates(tile)
        wall, cpu = time.perf_counter(), time.process_time()
        grids = [model.capture_grid(c, points, origin, 25110 + i) for i, c in enumerate(captures)]
        resources.append(
            dict(
                site=name,
                offer=condition,
                stage="build-matched-position-lattices",
                candidates=len(points),
                phases=len(model.PHASES_S),
                captures=len(captures),
                tracks=sum(len(c.arcs) for c in captures),
                cpu_s=time.process_time() - cpu,
                wall_s=time.perf_counter() - wall,
            )
        )
        for capture, grid in zip(captures, grids, strict=True):
            index = np.argmin(grid["phase-clock"])
            individuals.append(
                dict(
                    site=name,
                    offer=condition,
                    capture=capture.id,
                    visit=capture.visit,
                    point=points[index].tolist(),
                    objective_rms_hz=float(np.sqrt(grid["phase-clock"][index])),
                )
            )
        for visit, held in partitions.items():
            train = next(indices for day, indices in partitions.items() if day != visit)
            binding = sha256(
                encoded(
                    dict(
                        fit=[hashes[captures[i].id] for i in train],
                        test=[hashes[captures[i].id] for i in held],
                    )
                )
            ).hexdigest()
            for method, point, train_rms, train_gain in fit_visit(
                [grids[i] for i in train], points
            ):
                wall, cpu = time.perf_counter(), time.process_time()
                result = position_result(point, tile, PURPOSE[name], train_gain, method == "center")
                frequencies = []
                for index in held:
                    capture = captures[index]
                    common = model.predict(capture, point)
                    mode = method if method in model.MODES else "phase-clock"
                    native = (
                        model.predict(capture, point, mode) if mode != "phase-clock" else common
                    )
                    frequencies.append(
                        dict(
                            capture=capture.id,
                            tracks=len(capture.arcs),
                            **common,
                            native_tail_rms_hz=native["tail_forecast_rms_hz"],
                        )
                    )
                predictions.append(
                    dict(
                        id=f"{visit}-{condition}",
                        recording=visit,
                        site=name,
                        offer=condition,
                        method=method,
                        result=result,
                        tile=tile,
                        input_sha256=binding,
                        train_captures=[captures[i].id for i in train],
                        train_objective_rms_hz=train_rms,
                        held_frequency=frequencies,
                        score_cpu_s=time.process_time() - cpu,
                        score_wall_s=time.perf_counter() - wall,
                    )
                )
    return predictions, individuals, resources


def freeze(sources, out):
    if (out / PREFLIGHT).exists() or (out / LOCK).exists():
        raise FileExistsError("use a fresh report directory to preserve the prediction seal")
    real, roster, receipts = load_ctu(sources)
    datasets = {
        "prague": (PRAGUE_ORIGIN, real),
        "simulation": (simulation.ORIGIN, simulation.generate()),
    }
    membership = {
        name: [
            dict(
                id=c.id,
                visit=c.visit,
                tracks=len(c.arcs),
                samples=sum(len(a.times_s) for a in c.arcs),
                observation_sha256=observation_hash(c),
            )
            for c in captures
        ]
        for name, (_, captures) in datasets.items()
    }
    regions = {
        name: {k: model.offer(origin, k) for k in model.REGIONS_KM}
        for name, (origin, _) in datasets.items()
    }
    plan = dict(
        publication=archive.PUBLICATION,
        sources=receipts,
        ctu_members=roster,
        cases=membership,
        offers=regions,
        origins={name: origin for name, (origin, _) in datasets.items()},
        rf_hz=model.RF_HZ,
        height_m=model.HEIGHT_M,
        grid_spacing_km=model.GRID_KM,
        phase_grid_s=model.PHASES_S,
        phase_prior_s=model.PHASE_SIGMA_S,
        max_drift_hz_s=model.DRIFT_LIMIT_HZ_S,
        bin_hz=model.BIN_HZ,
        c_identifiability=(
            "For constant RF, adding c*x to model CFO is equivalent to an equal subtraction "
            "from every free track intercept. The optimum and predictions are invariant."
        ),
        holdout=(
            "Swap visits. Whole-capture curvature uses no fitted held-capture parameters. "
            "Conditional 40% prefix clock/phase calibration is scored on the last 60% only."
        ),
        controls=(
            "Same lattice and track observations across matched modes. Shuffle CFO order or "
            "rotate each training orbit 90 degrees around the city radial axis. "
            "Score all methods with the genuine held trajectory."
        ),
        availability="CTU Prague has author-selected tracks and orbit availability unaudited.",
    )
    save_json(out / PLAN, plan)
    sources = (
        Path(__file__),
        Path(model.__file__),
        Path(simulation.__file__),
        Path(archive.__file__),
        Path(prague_transfer.__file__),
    )
    source_locks = {str(path.relative_to(ROOT)): _sha(path) for path in sources}
    save_json(out / PREFLIGHT, dict(files={PLAN: _sha(out / PLAN)}, source_files=source_locks))
    return datasets, membership, regions, source_locks


def trial(sources, out):
    datasets, membership, regions, source_locks = freeze(sources, out)
    predictions, individuals, resources = [], [], []
    for name, (origin, captures) in datasets.items():
        hashes = {row["id"]: row["observation_sha256"] for row in membership[name]}
        p, i, r = evaluate(name, captures, regions[name], origin, hashes)
        predictions.extend(p)
        individuals.extend(i)
        resources.extend(r)
    for name, records in (
        (PREDICTIONS, predictions),
        (INDIVIDUAL, individuals),
        (RESOURCES, resources),
    ):
        save_json(out / name, records)
    save_json(
        out / LOCK,
        dict(
            files={
                name: _sha(out / name)
                for name in (PLAN, PREFLIGHT, PREDICTIONS, INDIVIDUAL, RESOURCES)
            },
            source_files=source_locks,
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=local_output)
    parser.add_argument("--out", type=local_output, default=OUT)
    args = parser.parse_args()
    trial(args.source, args.out)


if __name__ == "__main__":
    main()
