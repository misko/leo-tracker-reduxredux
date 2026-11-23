"""Audit whether already paid proof owners can safely reduce dense cold nomination."""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, solve, write


HERE = Path(__file__).resolve().parent
CASE = "DS30-0008"
SOURCE_SHA = "f9e61aa3c37a1a62bd708185feb39e6a7c9706326f3819aba2e892cb57061f06"


def admissible(probes, components, catalogue):
    """Use live proof votes only, with full cold search on an ambiguous track."""
    admitted, per_track = {}, {}
    catalogue = set(catalogue)
    for component in components:
        counts = Counter(row["owners"].get(component) for row in probes)
        counts.pop(None, None)
        per_track[component] = counts
        ranked = sorted(counts, key=lambda label: (-counts[label], label))
        top = ranked[:2]
        if (not top or 5 * sum(counts[label] for label in top) < 4 * len(probes)
                or any(label not in catalogue for label in top)
                or len(ranked) >= 3 and counts[ranked[1]] == counts[ranked[2]]):
            continue
        admitted[component] = top
    return admitted, per_track


def now():
    return process_time(), perf_counter()


def clocks(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def projections(probes, track_points, catalogue, signatures):
    slates, votes = admissible(probes, track_points, catalogue)
    all_winners = {value for row in probes for value in row["owners"].values() if value is not None}
    global_pool = all_winners & set(catalogue)
    cells = len(catalogue) * sum(track_points.values())
    narrowed = sum(track_points[key] * len(slates.get(key, catalogue)) for key in track_points)
    results = []
    for rank, signature in enumerate(signatures, 1):
        misses = dict(track_union=[], capped_with_fallback=[], global_union=[])
        for component, _, label, alias in signature:
            row = dict(component=component, norad=label, alias=alias, points=track_points[component])
            if label not in votes[component]:
                misses["track_union"].append(row)
            if component in slates and label not in slates[component]:
                misses["capped_with_fallback"].append(row)
            if label not in global_pool:
                misses["global_union"].append(row)
        total = sum(track_points[row[0]] for row in signature)
        results.append(dict(rank=rank, tracks=len(signature), points=total, misses=misses,
                            hits={key: len(signature)-len(rows) for key, rows in misses.items()},
                            hit_points={key: total-sum(r["points"] for r in rows) for key, rows in misses.items()}))
    return dict(slates=slates, votes={k: sorted(v.items()) for k, v in votes.items()}, baseline_cells=cells,
                capped_cells=narrowed, global_pool=len(global_pool), global_pool_cells=len(global_pool)*sum(track_points.values()),
                global_pool_outside_cold_catalogue=sorted(all_winners-set(catalogue)),
                fallback_tracks=len(track_points)-len(slates), ranks=results,
                warrants_trial=(4 * narrowed <= 3 * cells
                                and all(not row["misses"]["capped_with_fallback"] for row in results)))


def shared_geometry(scan, tracks, live, region, probe_rows, positions):
    import numpy as np
    from tools.pipeline_eval.variants.experimental import regional_reassignment as geographic

    causal = live.catalogue
    if causal is None or scan.origin_utc_ns != tracks["metadata"]["anchor_utc_ns"]:
        raise ValueError("The two projections use different prepared archives or time origins")
    cold = {int(norad): i for i, norad in enumerate(scan.norads)}
    cold_times = scan.sky["time_s"]
    propagate = geographic.ecef_states
    checks = []

    def inspect(catalogue, epoch, times):
        start = now()
        position, velocity, usable = propagate(catalogue, epoch, times)
        propagation = clocks(start)
        common = [(j, cold[n]) for j, n in enumerate(catalogue.satellite_numbers) if n in cold]
        indexes = np.searchsorted(cold_times, times)
        if epoch != scan.origin_utc_ns or np.any(indexes >= len(cold_times)) or not np.array_equal(cold_times[indexes], times):
            raise ValueError("The fixed dense proof no longer uses matching nominal propagation knots")
        exact = sum(bool(usable[j] and np.array_equal(position[j], scan.sky["position_km"][k, indexes])
                         and np.array_equal(velocity[j], scan.sky["velocity_km_s"][k, indexes]))
                    for j, k in common)
        checks.append(dict(catalogue_rows=len(catalogue), shared_rows=len(common), exact_shared_rows=exact,
                           knots=len(times), propagation=propagation, original_cells=len(catalogue)*len(times),
                           exact_shared_cells=exact*len(times)))
        return position, velocity, usable

    locations = [row["latlon"] for row in geographic.probes(region)]
    starts = np.unique([track["times"][0] for track in tracks["tracks"]])
    with patch.object(geographic, "ecef_states", inspect):
        grid, labels = geographic.orbit_geometry(causal.catalogue, scan.origin_utc_ns, scan.times, starts,
                                                  region.center, locations)
    common = {int(n) for n in labels} & cold.keys()
    if grid is None or not np.array_equal(scan.geometry.positions, scan.sky["position_km"]) or not np.array_equal(
            scan.geometry.velocities, scan.sky["velocity_km_s"]):
        raise ValueError("The nominal cold stencil did not retain the original knots")
    # Cold projection consumes the compact native interpolation stencil. The geographic
    # bank materializes full event positions, so there are no two phase arrays to alias.
    at = scan.times + np.array([0., scan.geometry.step, -scan.geometry.step])[:, None]
    bracketing = scan.geometry.index[0]
    fractions = (at-cold_times[bracketing])/(cold_times[bracketing+1]-cold_times[bracketing])
    matching_fraction = bool(scan.geometry.index.shape[0] == 1 and scan.geometry.step == .05
                             and np.array_equal(scan.geometry.fraction[0], fractions)
                             and np.array_equal(bracketing, np.searchsorted(cold_times, at, side="right")-1))
    clock = now()
    track = scan.tracks[scan.curved[0]]
    observed = np.asarray(track["values"])
    predicted = observed[None, :] + np.linspace(0., 140., len(observed))[None, :]
    tangent = np.linspace(-200., 300., len(observed))[None, :]
    scores = [float(geographic.contrast_log_ratio(observed, predicted+j*geographic.PERIOD, tangent)[0])
              for j in (-1, 0, 1)]
    return dict(propagation=checks, phase_grid_rows=len(labels), phase_grid_common=len(common),
                cold_geometry_type=type(scan.geometry).__name__, cold_exact_source_knots=True,
                cold_nominal_stencil_matches_phase_queries=matching_fraction,
                event_times=len(scan.times), phase_grid_only_cold=len(cold)-len(common),
                cold_projection_latlon=sorted(positions), exact_proof_coordinate_overlap=len(
                    set(positions) & {tuple(row["latlon"]) for row in probe_rows}),
                alias_demo=dict(rf_hz=track["rf_hz"], period_hz=geographic.PERIOD, rolls=[-1, 0, 1], scores=scores,
                                max_change=max(scores)-min(scores), clocks=clocks(clock)))


def run(output):
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(value != "1" for value in host["threads"].values())):
        raise ValueError("Expected the shared low-priority Gauss slot")
    publication, spec = configuration()
    from blind_joint_finish import digest
    from dense_quadratic_proxy import GraphAudit
    from joint_publication import full_catalogue_route
    from leo.analysis.localization_v3 import discovery
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    body = (HERE / "measurements/dense-quadratic-fused.json.gz").read_bytes()
    if sha256(body).hexdigest() != SOURCE_SHA:
        raise ValueError("The sealed paid proof changed")
    sealed = json.loads(gzip.decompress(body))
    native, archive, offered, _, identity = inputs(CASE)
    if (identity != sealed["identity"] or len(sealed["visited_probes"]) != 25
            or identity["detector_sha256"] != "sha256:" + spec["detector_sha256"]):
        raise ValueError("The saved graph or paid proof belongs to another input")
    seen = sealed["visited_probes"]
    graph = GraphAudit()
    recovered = {}
    stock = algo08_position.solve
    rank_share = run_path(str(HERE.parents[2] / "tools/pipeline_eval/variants/algo08_blind_rank.py"))["shared_rank_preparation"]

    def solver(document, reader, assets, region):
        if document is not native or reader.root != archive or region.document() != offered:
            raise ValueError("The saved acquisition authority or region changed")
        with ExitStack() as scope:
            live, _, _ = scope.enter_context(handoff(reader))
            scope.enter_context(graph.configure(assets, full_catalogue_route))

            def inspect(prepared, view, bound, _stages, **_options):
                start = now()
                scan = v5_core.scan_context(prepared, view, digest(prepared["noise"]), bound, "previous")
                recovered["scan_setup"] = clocks(start)
                coords = set()
                project = discovery.phase_linear_frequency

                def record(geometry, latitude, longitude, **kwargs):
                    coords.add((float(latitude), float(longitude)))
                    return project(geometry, latitude, longitude, **kwargs)

                start = now()
                with patch.object(discovery, "phase_linear_frequency", record), rank_share(scan) as shared:
                    ranked = v5_core.ranked_initial_nodes(scan)
                recovered.update(rank=clocks(start), sharing=shared, hypotheses=len(ranked))
                signatures = [discovery.signature(node) for node in ranked[:3]]
                sealed_overlap = sealed["attempts"][0]["cold"]["overlap"]
                from cold_finalist_race import audit_overlap

                if len(signatures) != 3 or audit_overlap(ranked[:3]) != sealed_overlap:
                    raise ValueError("Recovered cold shortlist differs from the sealed three-finalist structure")
                points = {key: len(group[0]["times"]) for key, group in scan.groups}
                recovered.update(signatures=signatures, track_points=points, cold_catalogue=len(scan.norads))
                recovered["selection"] = projections(seen, points, scan.norads, signatures)
                recovered["geometry"] = shared_geometry(scan, prepared["tracks"], live, view, seen, coords)
                return dict(status="withheld", reason="rank_only_audit", arms={arm: {"latlon": None} for arm in ARMS})

            scope.enter_context(patch.object(v5_core, "infer", inspect))
            return stock(document, reader, assets, region)

    with patch.object(algo08_position, "solve", solver):
        result = solve(publication, spec, native, archive, offered)
    new = graph.report()["graph"]
    if (new["graph_sha256"] != sealed["graph"]["graph_sha256"]
            or json.loads(json.dumps(new["quadratic"])) != sealed["graph"]["quadratic"]
            or result["reason"] != "rank_only_audit" or archive_identity(archive) != identity["archive"]):
        raise ValueError("Original solver state or intentional rank-only exit changed")
    write(output, dict(source_sha256=SOURCE_SHA, identity=identity, graph_sha256=new["graph_sha256"], host=host,
                       proof_visits=len(seen), proof_sides=Counter(row["side"] for row in seen),
                       sealed_full_cold_cpu_s=sealed["attempts"][0]["cold_clocks"]["cpu_s"], **recovered))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
