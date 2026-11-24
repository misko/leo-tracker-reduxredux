"""Screen a research-only full-layout position map with independently paid sentinels."""

import argparse
from collections import defaultdict
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from time import perf_counter, process_time

import numpy as np
from PIL import Image
from scipy.interpolate import RectBivariateSpline
from scipy.spatial import Delaunay, cKDTree

from leo.analysis.position_grid import ARMS
from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import PLOTS
from leo.storage.fast_scan import FastScanStore
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


HERE = Path(__file__).resolve().parent
PAIR = Path("/dev/shm/leo-cumulative-grid-projection-01")
SOUTH = Path("/dev/shm/leo-v3-named-south-transfer-01")
CASES = {
    "DS30-0008": (PAIR/"dense-pair/combined", "f378b41ceaf7a874aeb2b7cb02636647fa01b32c0ddc70efb65fd566a724182f"),
    "DS30-0016": (PAIR/"weak-pair/combined", "0c58ec99175dd6111255739386d958125de5b20f3358e6ac571dccccd0ed4fb1"),
    "south-containing": (SOUTH/"containing", "25a311334c51296e81176c23fe7609b78b1262c7a600da2e5a2a6eed0d029195"),
    "south-near-omitted": (SOUTH/"near-omitted", "d4e46271bf683017213c2c70df065e0bcb8192ef45ba7f09efb0cd840bf48cb0"),
}
LEVELS = (2.30, 4.50, 9.21)
ABS_LIMIT = .25
CONTOUR_LIMIT_KM = .15
DENSE_SAVING_GATE_S = 2.


def xy(row):
    return row["east_km"], row["north_km"]


def quadratic(points):
    p, q = np.asarray(points, dtype=float).T
    return np.column_stack((np.ones(len(p)), p, q, p*p, p*q, q*q))


def tensor_cubic(coarse, values, points):
    knots = coarse / abs(coarse[0])
    design = quadratic([(x, y) for x in knots for y in knots])
    targets = np.asarray(points) / abs(coarse[0])
    base = values.reshape(-1, len(ARMS))
    coef, _, rank, _ = np.linalg.lstsq(design, base, rcond=None)
    if rank != design.shape[1] or not np.isfinite(coef).all():
        raise ValueError("Unsupported quadratic trend support")
    confound = quadratic(targets) @ coef
    residual = (base - design @ coef).reshape(len(knots), len(knots), len(ARMS))
    for i in range(len(ARMS)):
        spline = RectBivariateSpline(knots, knots, residual[:, :, i], kx=3, ky=3, s=0)
        confound[:, i] += spline.ev(*targets.T)
    return confound


def position_map(points, endpoints, width, score):
    """An original exact pair is available only through the charged callback."""
    paid, sources = {}, {}
    available = set(points)

    def query(point, purpose):
        if point not in paid:
            values = tuple(score(point))
            if len(values) != len(ARMS):
                raise ValueError("Each request must pay both calibration arms")
            paid[point] = values
            sources[point] = purpose
        return paid[point]

    def finish(estimated):
        return dict(paid=paid, sources=sources, estimated=estimated)

    def exact_fallback():
        for point in points:
            query(point, "exact_fallback")
        return finish({})

    half = width/2.
    coarse = np.asarray([-half + width*i/8 for i in range(9)])
    corners = [(e, n) for e in coarse for n in coarse]
    if (width <= 0. or len(available) != len(points) or not set(corners + list(endpoints)).issubset(available)
            or not all(np.isfinite(p).all() and max(map(abs, p)) <= half for p in points)):
        return exact_fallback()
    for point in endpoints:
        query(point, "endpoint")
    anchors = coarse[::2]
    known = np.array([[query((e, n), "coarse_training") for n in anchors] for e in anchors], dtype=float)
    if not np.isfinite(known).all():
        return exact_fallback()

    inspection = [[(coarse[2*i+1], coarse[2*j+1]) for j in range(4)] for i in range(4)]
    seams = {(i, j): (coarse[4*(i//2)+2], coarse[2*j+1]) for i in range(4) for j in range(4)}
    try:
        guess = dict(zip(points, tensor_cubic(anchors, known, points), strict=True))
    except (ValueError, np.linalg.LinAlgError):
        return exact_fallback()

    radii = np.empty((4, 4, len(ARMS)), dtype=float)
    for i, centres in enumerate(inspection):
        for j, mid in enumerate(centres):
            edge = seams[i, j]
            observed = np.array([query(mid, "cell_sentinel"), query(edge, "edge_sentinel")], dtype=float)
            reference = np.asarray([guess[mid], guess[edge]])
            errors = np.abs(observed-reference)
            radii[i, j] = 4.*np.max(np.where(np.isfinite(errors), errors, np.inf), axis=0) + .001
    anchor_scores = np.array(list(paid.values()), dtype=float)
    best = np.min(np.where(np.isfinite(anchor_scores), anchor_scores, np.inf), axis=0)

    def incident(value):
        eligible, = np.nonzero((anchors[:-1] <= value) & (anchors[1:] >= value))
        return eligible

    estimated = {}
    for point in points:
        if point in paid:
            continue
        east, north = map(incident, point)
        if not len(east) or not len(north):
            query(point, "out_of_support")
            continue
        risk = radii[np.ix_(east, north)].max(axis=(0, 1))
        value = guess[point]
        if np.any(risk > ABS_LIMIT) or not np.isfinite(value).all():
            query(point, "unresolved_interpolation")
        elif np.any(value - risk <= best + LEVELS[-1]):
            query(point, "near_paid_low_loss")
        else:
            estimated[point] = (tuple(map(float, value)), tuple(map(float, risk)))
    return finish(estimated)


def mesh_edges(triangles):
    return sorted({tuple(sorted((int(t[i]), int(t[(i+1) % 3])))) for t in triangles for i in range(3)})


def modes(values, edges):
    worst = ~np.isfinite(values)
    for a, b in edges:
        worst[a] |= values[a] > values[b]
        worst[b] |= values[b] > values[a]
    return set(np.flatnonzero(~worst))


def contour_samples(points, values, level, triangles):
    segments = []
    for tri in triangles:
        scores = values[tri]
        if not np.isfinite(scores).all() or scores.min() > level or scores.max() <= level:
            continue
        sites = points[tri]
        crossings = []
        for i in range(3):
            j = (i+1) % 3
            if (scores[i] <= level) != (scores[j] <= level):
                alpha = (level-scores[i])/(scores[j]-scores[i])
                crossings.append(sites[i]+alpha*(sites[j]-sites[i]))
        if len(crossings) == 2:
            a, b = crossings
            segments.append(np.linspace(a, b, 25))
    return np.concatenate(segments) if segments else np.empty((0, 2))


def contour_error(original, candidate):
    if len(original) == len(candidate) == 0:
        return 0.
    if not len(original) or not len(candidate):
        return None
    return float(max(cKDTree(original).query(candidate)[0].max(), cKDTree(candidate).query(original)[0].max()))


def audit(points, reference, result):
    """Open the omitted original scores only after the research map is fixed."""
    xy = np.asarray(points)
    mesh = Delaunay(xy).simplices
    edges = mesh_edges(mesh)
    exact = np.array([reference[p] for p in points], dtype=float)
    estimates = np.array([result["paid"][p] if p in result["paid"] else result["estimated"][p][0]
                          for p in points], dtype=float)
    rows = [i for i, p in enumerate(points) if p in result["estimated"]]
    per_arm = {}
    for index, name in enumerate(ARMS):
        a, b = exact[:, index], estimates[:, index]
        if not np.isfinite(a).any() or not np.isfinite(b).any():
            raise ValueError("A useful complete map requires a finite scoring domain")
        base, candidate = np.nanmin(a), np.nanmin(b)
        error = np.abs(a[rows]-b[rows])
        envelope = np.asarray([result["estimated"][points[i]][1][index] for i in rows])
        modes_a, modes_b = modes(a, edges), modes(b, edges)
        low_a = {i for i in modes_a if a[i]-base <= LEVELS[-1]}
        low_b = {i for i in modes_b if b[i]-candidate <= LEVELS[-1]}
        checks = {}
        for level in LEVELS:
            original = contour_samples(xy, a-base, level, mesh)
            predicted = contour_samples(xy, b-candidate, level, mesh)
            checks[str(level)] = dict(changed_membership=int(np.count_nonzero(((a-base) <= level) != ((b-candidate) <= level))),
                                      sampled_hausdorff_km=contour_error(original, predicted),
                                      original_contour_samples=len(original), estimated_contour_samples=len(predicted))
        scored = error[np.isfinite(error)]
        maxima = float(scored.max()) if len(scored) else 0.
        per_arm[name] = dict(max_estimated_score_error=maxima,
                             median_estimated_score_error=float(np.median(scored)) if len(scored) else 0.,
                             unexplained_errors=int(np.count_nonzero(error > envelope)),
                             errors_above_tolerance=int(np.count_nonzero(error > ABS_LIMIT)),
                             changed_failure=int(np.count_nonzero(np.isfinite(a) != np.isfinite(b))),
                             minima_match=set(np.flatnonzero(a == base)) == set(np.flatnonzero(b == candidate)),
                             low_modes_removed=[points[i] for i in sorted(low_a-low_b)],
                             low_modes_added=[points[i] for i in sorted(low_b-low_a)],
                             higher_modes_removed=[points[i] for i in sorted((modes_a-modes_b)-low_a)],
                             higher_modes_added=[points[i] for i in sorted((modes_b-modes_a)-low_b)],
                             contours=checks)
    return per_arm


def preserves_fidelity(row):
    return (row["changed_failure"] == row["errors_above_tolerance"] == 0 and row["minima_match"]
            and not (row["low_modes_removed"] or row["low_modes_added"])
            and all(c["changed_membership"] == 0 and c["sampled_hausdorff_km"] is not None
                    and c["sampled_hausdorff_km"] <= CONTOUR_LIMIT_KM for c in row["contours"].values()))


def interpolation_readout(points, reference, result, width):
    """Price unguarded errors after the frozen schedule. This never asks the callback."""
    initial = {p: result["paid"][p] for p, source in result["sources"].items()
               if source in ("endpoint", "coarse_training", "edge_sentinel", "cell_sentinel")}
    if len(initial) < 49:
        return None
    coarse = np.asarray([-width/2. + width*i/8 for i in range(0, 9, 2)])
    training = np.asarray([[initial[(x, y)] for y in coarse] for x in coarse], dtype=float)
    guess = dict(zip(points, tensor_cubic(coarse, training, points), strict=True))
    held = [p for p in points if p not in initial]
    if not held:
        return None
    raw = dict(paid=initial, estimated={p: (guess[p], (0., 0.)) for p in held})
    checks = audit(points, reference, raw)
    errors = np.abs(np.array([guess[p] for p in held]) - np.array([reference[p] for p in held], dtype=float))
    sentinels = [p for p, purpose in result["sources"].items() if purpose in ("edge_sentinel", "cell_sentinel")]
    for index, arm in enumerate(ARMS):
        sentinel_error = [abs(float(guess[p][index])-initial[p][index]) for p in sentinels
                          if initial[p][index] is not None]
        checks[arm]["raw_sentinel_errors"] = dict(finite=len(sentinel_error), min=min(sentinel_error, default=None),
                                                  median=float(np.median(sentinel_error)) if sentinel_error else None,
                                                  max=max(sentinel_error, default=None))
    return dict(paid_locations=len(initial), raw_predictions=len(held), arms=checks,
                lucky_joint_scores_within_tolerance=int(np.count_nonzero(np.all(errors <= ABS_LIMIT, axis=1))),
                all_original_errors_read_after_schedule=True)


def archived_case(root, pin):
    if not root.resolve(strict=True).is_relative_to(Path("/dev/shm")):
        raise ValueError("Use only original staged publication metadata")
    body = (root/"joint-research-receipt.json").read_bytes()
    if sha256(body).hexdigest() != pin:
        raise ValueError("Original scientific evidence receipt changed")
    source = json.loads(body)
    receipt = source["receipt"]
    evidence = source["evidence"]
    run_id = receipt["run_id"]
    store = FastStandardAnalysisStore(root)
    grid, path = store.position_grid(run_id), store.position_path(run_id)
    terminal = json.loads((FastScanStore(root).automatic_workspace(run_id, create=False)/"terminal.json").read_bytes())
    if (canonical_digest(terminal) != receipt["terminal_sha256"] or receipt["decision"] != "complete"
            or canonical_digest(grid) != evidence["grid"] or canonical_digest(path) != evidence["path"]
            or not grid["complete"] or (grid["coarse_size"], grid["local_size"]) != (9, 7)
            or set(evidence["images"]) != set(PLOTS)):
        raise ValueError("The exact grid, terminal or original figures changed")
    for name, recorded in evidence["images"].items():
        image = store.artifact(run_id, name, recorded["sha256"])
        with Image.open(BytesIO(image)) as png:
            if png.format != "PNG" or list(png.size) != recorded["size"]:
                raise ValueError("Verified archived PNG dimensions changed")
            png.verify()
    return grid, terminal, source


def screen_case(root, pin):
    grid, terminal, source = archived_case(root, pin)
    points = [xy(row) for row in grid["points"]]
    exact = {xy(row): tuple(row["scores"][arm] for arm in ARMS) for row in grid["points"]}
    order = []

    def charged(point):
        order.append(point)
        return exact[point]

    start = process_time(), perf_counter()
    research = position_map(points, [tuple(grid["endpoints"][arm]) for arm in ARMS], grid["box_width_km"], charged)
    cost_cpu, cost_wall = process_time()-start[0], perf_counter()-start[1]
    if len(set(order)) != len(order) or set(order) != set(research["paid"]) or set(research["estimated"]) & set(order):
        raise ValueError("The research estimator touched a hidden exact work oracle")
    # The original ordered schema geometry is replicated in a separate research
    # document; the immutable official score sidecar and binding are untouched.
    out, sources = [], defaultdict(int)
    for row in grid["points"]:
        point = xy(row)
        if point in research["paid"]:
            purpose = research["sources"][point]
            values, radius = research["paid"][point], (None, None)
        else:
            purpose = "estimated"
            values, radius = research["estimated"][point]
        sources[purpose] += 1
        out.append(dict(east_km=point[0], north_km=point[1], latlon=row["latlon"],
                        scores=dict(zip(ARMS, values, strict=True)), origin=purpose,
                        failures=row["failures"] if point in research["paid"] else {},
                        empirical_error_radius=dict(zip(ARMS, radius, strict=True))))
    checks = audit(points, exact, research)
    unchecked = interpolation_readout(points, exact, research, grid["box_width_km"])
    cost = source["route_details"]["standard_evidence_clocks"]["cpu_s"]
    posterior = source["receipt"]["posterior_grid_handoff"]
    count = len(research["estimated"])
    candidate_budget = cost*count/(len(points)-1) - cost_cpu
    return dict(source_sha256=pin, exact_grid_binding=grid["binding"], exact_grid_digest=source["evidence"]["grid"],
                exact_path_digest=source["evidence"]["path"], original_figures=source["evidence"]["images"],
                original_terminal_arms=terminal["arms"], region=source["receipt"]["region"],
                original_terminal=source["receipt"]["terminal_sha256"], original_points=len(points), paid_locations=len(order),
                estimated_locations=count, paid_sources=dict(sources), charged_order=order,
                archive_standard_evidence_cpu_s=cost, archive_native_grid_calls=posterior.get("factor_calls", 0),
                archive_curved_cpu_s=posterior.get("curved_cpu_ns", 0)/1e9,
                archive_predictive_cpu_s=posterior.get("predictive_kernel_cpu_ns", 0)/1e9,
                proportional_saved_cpu_less_schedule_s=candidate_budget,
                interpolation_schedule=dict(cpu_s=cost_cpu, elapsed_s=cost_wall), arms=checks,
                unguarded_for_analysis_only=unchecked,
                fidelity=all(preserves_fidelity(row) for row in checks.values()),
                research_map=dict(kind="research-only position score estimates", original_planned_points=grid["planned_points"],
                                  endpoints=grid["endpoints"], region_center=grid["region_center"],
                                  box_width_km=grid["box_width_km"], points=out))


def run(output):
    if not output.parent.resolve(strict=True).is_relative_to(Path("/dev/shm")):
        raise ValueError("Write the archive screen in tmpfs")
    start = process_time(), perf_counter()
    results = {name: screen_case(*case) for name, case in CASES.items()}
    gate = all(row["fidelity"] for row in results.values()) and results["DS30-0008"]["proportional_saved_cpu_less_schedule_s"] >= DENSE_SAVING_GATE_S
    with output.open("x") as stream:
        json.dump(dict(results=results, live_case_gate=gate, official_output_changes=0, additional_solves=0, waveform_reads=0,
                       protocol_sha256=sha256((HERE/"grid-control-variate-protocol.md").read_bytes()).hexdigest(),
                       source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                       cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1]), stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
