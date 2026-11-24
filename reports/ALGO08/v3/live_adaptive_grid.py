"""The archived point rule on the actual post-fit two-arm score port."""

from collections import Counter
import math
from time import monotonic, process_time


class IncompleteAdaptiveGrid(RuntimeError):
    """An incomplete research layout cannot become a publication."""


def locations(sampler, endpoints, width, local_half, coarse, local):
    """Read the original coordinate plan without making any objective call."""
    ordered = []

    def hold(_, chunks):
        ordered.extend(point for chunk in chunks for point in chunk)
        return [[] for _ in chunks]

    def deny(*_):
        raise AssertionError("Planning must not evaluate an objective")

    sampler(deny, endpoints, box_width_km=width, local_half_width_km=local_half,
            coarse_size=coarse, local_size=local, map_batches=hold)
    return ordered


def adaptive_sampler(score, endpoints, *, box_width_km=25., coarse_size=9,
                     local_size=7, local_half_width_km=1.5, maximum_seconds=30.,
                     clock=monotonic, map_batches=None):
    from leo.analysis.position_grid import ARMS, sample_position_grid
    from reports.ALGO08.v3.adaptive_grid_screen import choose_nodes

    if (coarse_size, local_size) != (9, 7) or map_batches is not None or maximum_seconds <= 0:
        raise ValueError("Adaptive research layout requires the serial released 9/7 reference plan")
    began, cpu = clock(), process_time()
    original = locations(sample_position_grid, endpoints, box_width_km, local_half_width_km, 9, 7)
    initial = locations(sample_position_grid, endpoints, box_width_km, local_half_width_km, 5, 4)
    if len(initial) < 3 or not set(initial) <= set(original):
        raise IncompleteAdaptiveGrid("First-pass points must be a genuine subset of the released coordinate plan")
    by_point, calls = {}, Counter()

    def measure(points):
        for xy in points:
            if clock()-began >= maximum_seconds:
                raise IncompleteAdaptiveGrid("Adaptive sampling reached the shared deadline")
            values, failures = {}, {}
            for arm in ARMS:
                calls[arm] += 1
                try:
                    value = float(score(arm, xy))
                    if not math.isfinite(value):
                        raise ValueError("Non-finite objective")
                    values[arm] = value
                except (ValueError, ArithmeticError) as error:
                    values[arm], failures[arm] = None, type(error).__name__
            by_point[xy] = dict(east_km=xy[0], north_km=xy[1], scores=values, failures=failures)

    measure(initial)
    planner_cpu = process_time()
    selected = choose_nodes(original, initial, [[by_point[p]["scores"][a] for a in ARMS] for p in initial])
    planner_cpu = process_time()-planner_cpu
    measure([point for point in original if point in selected and point not in by_point])
    if clock()-began >= maximum_seconds:
        raise IncompleteAdaptiveGrid("Adaptive sampling reached the shared deadline")
    rows = [by_point[p] for p in original if p in selected]
    return dict(schema_version=1, kind="research-adaptive-conditional-position-sample",
                conditioning="published satellite ownership and phase linearization fixed",
                nuisance_model="unchanged published marginal likelihood", matched_c_grid=True,
                box_width_km=box_width_km, local_half_width_km=local_half_width_km,
                maximum_seconds=maximum_seconds, elapsed_seconds=clock()-began, sample_cpu_s=process_time()-cpu,
                refinement_cpu_s=planner_cpu, initial_layout=dict(coarse_size=5, local_size=4, points=len(initial)),
                reference_layout=dict(coarse_size=9, local_size=7, candidates=len(original)),
                planned_points=len(selected), evaluated_points=len(rows), objective_calls=dict(calls), complete=True,
                endpoints={a: list(endpoints[a]) for a in ARMS}, points=rows)


def quality(grid, reference):
    from leo.analysis.position_grid import ARMS

    def rows(document):
        return {(x["east_km"], x["north_km"]): x for x in document["points"]}

    active, full = rows(grid), rows(reference)
    if (len(active) != grid["evaluated_points"] or len(full) != grid["reference_layout"]["candidates"]
            or active.keys()-full.keys() or not all(x == full[p] for p, x in active.items())):
        raise ValueError("Measured research rows differ from the exact full-layout values")
    omitted = full.keys()-active.keys()
    summary = {}
    for arm in ARMS:
        minimum = min(row["scores"][arm] for row in full.values() if row["scores"][arm] is not None)
        lost = [full[p]["scores"][arm] for p in omitted]
        summary[arm] = dict(minimum=minimum, missed_minima=lost.count(minimum),
                            missed_low_nodes=sum(v is not None and v <= minimum+4.5 for v in lost),
                            missed_failed_nodes=lost.count(None))
    return dict(omitted=len(omitted), arms=summary,
                passed=all(not (r["missed_minima"] or r["missed_low_nodes"] or r["missed_failed_nodes"]) for r in summary.values()))
