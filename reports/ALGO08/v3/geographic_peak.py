"""Interpolate the archived regional mixture maps independently of fitted fixes."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np
from scipy.spatial import ConvexHull, QhullError

from aperture_trial import read, write
from dense_geographic_trial import host


HERE = Path(__file__).resolve().parent
MAPS = HERE / "measurements/geographic-rf-fold.json.gz"
MAPS_PIN = "d9eb86dd1941255a3c1fe6cc5cd095dcf8e2789e8c16eae513bdb892d93e5acb"
LATTICE_PIN = "6e7ae57a5762be3028756e3033c070de587c461707dda059692aee5d7c717b96"
OFFERS = dict(india=("matched-tile", "omitted-tile"), north=("inside", "outside"), south=("inside", "outside"))
NEIGHBORS = 12


def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()


def frozen_json(path, expected):
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValueError(f"Public development input changed: {path.name}")
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def local_peak(coordinates, values, width):
    """Fit the fixed local quadratic and accept only an in-hull strict maximum."""
    xy, scores = np.asarray(coordinates, float), np.asarray(values, float)
    if (xy.ndim != 2 or xy.shape[1] != 2 or scores.shape != (len(xy),) or len(xy) < NEIGHBORS
            or not np.isfinite(xy).all() or not np.isfinite(scores).all() or not np.isfinite(width) or width <= 0
            or len(np.unique(xy, axis=0)) != len(xy)):
        raise ValueError("Expected distinct finite coordinates and pooled scores")
    winner = int(np.argmax(scores))
    anchor = xy[winner]
    discrete = dict(index=winner, xy_km=anchor.tolist(), score=float(scores[winner]))
    diagnostics = {}

    def invalid(reason):
        return dict(discrete=discrete, interpolated=None, status=reason, diagnostics=diagnostics)

    if np.count_nonzero(scores == scores[winner]) != 1:
        return invalid("tied_sample_maximum")
    normalized = (xy - anchor) / width
    distance = np.einsum("ij,ij->i", normalized, normalized)
    slots = np.lexsort((np.arange(len(xy)), distance))[:NEIGHBORS]
    diagnostics["neighbor_indices"] = slots.tolist()
    points = normalized[slots]
    x, y = points.T
    design = np.column_stack((np.ones(len(points)), x, y, x*x, x*y, y*y))
    target = scores[slots] - scores[winner]
    try:
        coeff, _, rank, singular = np.linalg.lstsq(design, target, rcond=None)
    except np.linalg.LinAlgError:
        return invalid("quadratic_solve_failed")
    diagnostics["design_rank"] = int(rank)
    if rank != 6 or not np.all(np.isfinite(coeff)) or singular[-1] == 0.:
        return invalid("invalid_quadratic_design")
    condition = singular[0] / singular[-1]
    diagnostics["design_condition"] = float(condition)
    diagnostics["fit_rms"] = float(np.sqrt(np.mean((design @ coeff - target)**2)))
    if not np.isfinite(condition) or condition > 1e6:
        return invalid("ill_conditioned_quadratic_design")

    hessian = np.array(((2 * coeff[3], coeff[4]), (coeff[4], 2 * coeff[5])))
    eigen = np.linalg.eigvalsh(hessian)
    limit = 32 * np.finfo(float).eps * max(1., np.max(abs(hessian)))
    diagnostics["hessian_eigenvalues"] = eigen.tolist()
    if eigen[-1] >= -limit:
        return invalid("nonconcave_quadratic")
    try:
        stationary = np.linalg.solve(hessian, -coeff[1:3])
        hull = ConvexHull(points)
    except (np.linalg.LinAlgError, QhullError):
        return invalid("invalid_stationary_or_hull")
    if not np.all(np.isfinite(stationary)):
        return invalid("nonfinite_stationary_point")
    largest = np.max(hull.equations[:, :-1] @ stationary + hull.equations[:, -1])
    diagnostics["max_hull_violation_scaled"] = float(largest)
    if largest > 1e-12:
        return invalid("stationary_outside_local_hull")

    point = anchor + width * stationary
    predicted_shift = coeff[0] + coeff[1:3] @ stationary + .5 * stationary @ hessian @ stationary
    return dict(discrete=discrete, interpolated=dict(xy_km=point.tolist(), predicted_score=float(scores[winner]+predicted_shift)),
                status="interpolated", diagnostics=diagnostics)


def bind_lattice(offer, archived, kernel):
    from leo.analysis.localization_v3.region import SearchRegion

    if archived["offer"] != offer or not archived["complete_score_match"]:
        raise ValueError("Expected the original score reconstruction on the offered square")
    region = SearchRegion(tuple(offer["center"]), width_km=offer["width_km"])
    fields = ("side", "xy_km", "latlon")
    points = archived["points"]
    expected = json.loads(json.dumps([{key: row[key] for key in fields} for row in kernel.probes(region)]))
    if len(expected) != 96 or [{key: row[key] for key in fields} for row in points] != expected:
        raise ValueError("Archived map differs from the released ordered 96-point lattice")
    return region, points


def estimate(offer, archived, kernel):
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

    region, points = bind_lattice(offer, archived, kernel)
    start = process_time_ns(), perf_counter_ns()
    result = local_peak([row["xy_km"] for row in points], [row["score"] for row in points], region.width_km)
    clocks = dict(cpu_s=(process_time_ns()-start[0])/1e9, elapsed_s=(perf_counter_ns()-start[1])/1e9)
    discrete = result["discrete"]
    original = points[discrete["index"]]
    discrete["latlon"] = original["latlon"]
    if result["interpolated"] is not None:
        point = result["interpolated"]
        point["latlon"] = list(map(float, region.latlon(np.asarray(point["xy_km"]))))
    terminal = evaluate_terminal(points, region.width_km, lambda row: row["receiver_scores"])
    return dict(**result, offer=offer, full_score_sha256=archived["full_score_sha256"], interpolation=clocks,
                full_probe_clock=archived["probe_clocks"], original_terminal=terminal,
                additional_scores=96-terminal["probes_evaluated"])


def run(output):
    from tools.pipeline_eval.variants.experimental import regional_reassignment as kernel

    current = host()
    if file_sha(Path(kernel.__file__)) != LATTICE_PIN:
        raise ValueError("The original regional score lattice changed")
    frozen = frozen_json(MAPS, MAPS_PIN)["sites"]
    if set(frozen) != set(OFFERS):
        raise ValueError("The prespecified three-site archive changed")
    data = {}
    for site, offers in OFFERS.items():
        archived = frozen[site]
        if archived["site"] != site or set(archived["offers"]) != set(offers):
            raise ValueError("Expected exactly the original public two-offer pair")
        rows = {}
        for offer in offers:
            page = archived["offers"][offer]
            rows[offer] = estimate(page["offer"], page, kernel)
        data[site] = dict(offers=rows, native_sha256=archived["native_sha256"])
    sources = {name: file_sha(HERE / name) for name in (Path(__file__).name, "geographic-peak-protocol.md")}
    write(output, dict(sites=data, input_sha256=MAPS_PIN, source_sha256=sources, host=current))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
