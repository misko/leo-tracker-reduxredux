"""Run the frozen exterior scout on the authenticated saved DS30-0016 omission."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from math import cos, hypot, isfinite, radians
from pathlib import Path
import signal
import subprocess
import sys
from time import perf_counter, process_time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from empty_bootstrap import RELEASE, checked
from history_risk_0016_omitted import HERE, input_binding, packet
from history_risk_weak_physical import deny_original


CPU_CAP = 3.5
RADII = (4, 8)
EXPECTED_PIN = "fd8cfe8a08ba896922c148e5050d3561e1f30cc875a9cf5dc7b942f55874d2cf"
TRACK_CONFIG_PIN = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
SCORE_PIN = "6e7ae57a5762be3028756e3033c070de587c461707dda059692aee5d7c717b96"
AUDIT_PIN = "667105870a1add0f2f5930617469cf31f1fef301"
REFERENCE_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
GAP_S = 0.96


def now():
    return process_time(), perf_counter()


def clocks(start):
    return dict(cpu_s=process_time() - start[0], elapsed_s=perf_counter() - start[1])


def write(path, value):
    body = (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()
    scratch = path.with_suffix(".tmp")
    scratch.write_bytes(body)
    scratch.replace(path)
    return sha256(body).hexdigest()


def axial_points(region, normals):
    points = []
    for radius in RADII:
        for x, y in normals:
            xy = [x * radius * region.width_km, y * radius * region.width_km]
            latitude, longitude = map(float, region.latlon(xy))
            if not (-90 < latitude < 90 and -180 <= longitude <= 180):
                raise ValueError("The wider probes exceed the local geographic domain")
            points.append(dict(side="exterior", xy_km=xy, latlon=(latitude, longitude)))
    return points


def maxima(points, width_km, wider=()):
    """Use the original receiver denominators and independent exterior maxima."""
    inside = [p for p in points if p["side"] == "inside"]
    outside = [p for p in points if p["side"] == "exterior"]
    receivers = sorted(inside[0]["receiver_scores"])
    if len(receivers) != 2 or any(
        set(p["receiver_scores"]) != set(receivers) or not all(map(isfinite, p["receiver_scores"].values()))
        for p in (*inside, *outside, *wider)
    ):
        raise ValueError("Expected matching finite scores for two receivers")
    result = {}
    for receiver in receivers:
        def score(point):
            return point["receiver_scores"][receiver]

        best_in = max(inside, key=score)
        first, second, *_ = sorted(outside + list(wider), key=score, reverse=True)
        result[receiver] = dict(inside_xy_km=best_in["xy_km"], inside_score=score(best_in),
                                exterior_xy_km=first["xy_km"], exterior_score=score(first),
                                gain=score(first) - score(best_in), margin=score(first) - score(second),
                                clearance_km=max(map(abs, first["xy_km"])) - width_km / 2,
                                wider=any(first is p for p in wider))
    first, second = (row["exterior_xy_km"] for row in result.values())
    separation = hypot(first[0] - second[0], first[1] - second[1])
    positive = separation <= width_km and all(row["margin"] > 0 and row["gain"] > 0
                                             and row["clearance_km"] >= width_km for row in result.values())
    return dict(receivers=result, separation_km=separation, bilateral=positive,
                bilateral_wider=positive and all(row["wider"] for row in result.values()))


def graph_membership(graph):
    tracks = graph["tracks"]
    all_rows = {str(rx): [r["observation_id"] for r in graph["observations"] if r["receiver"] == rx]
                for rx in sorted({r["receiver"] for r in graph["observations"]})}
    members = [{k: t[k] for k in ("key", "receiver", "channel", "rf_hz", "observation_ids")} for t in tracks]
    counts = {rx: sum(len(t["observation_ids"]) for t in tracks if str(t["receiver"]) == rx) for rx in all_rows}
    return dict(observation_ids=all_rows, tracks=members, graph_points_by_receiver=counts,
                missing_points_by_receiver={rx: len(ids) - counts[rx] for rx, ids in all_rows.items()})


def probe_bank(kernel, graph, catalogue, region, *, points=None, original_order=None):
    """Observe the original geometry and scorer without changing its arithmetic."""
    import numpy as np

    propagation, horizon, terms = [], [], []
    state, envelope = kernel.ecef_states, kernel.possible_horizon
    track, contrast = kernel.score_track, kernel.contrast_log_ratio
    ratios = None
    capture_cpu = 0.0

    def states(*args):
        result = state(*args)
        propagation.append((args[0].satellite_numbers, result[2]))
        return result

    def possible(*args):
        mask = envelope(*args)
        horizon.append(mask.any(axis=1))
        return mask

    def ratio(*args):
        nonlocal ratios
        ratios = contrast(*args)
        return ratios

    def term(observed, predicted, elevation, derivative, labels, catalogue_size):
        nonlocal ratios, capture_cpu
        ratios = None
        result = track(observed, predicted, elevation, derivative, labels, catalogue_size)
        start = process_time()
        visible = (elevation >= 0).all(axis=1)
        terms.append((labels, visible, ratios, *result))
        capture_cpu += process_time() - start
        return result

    start = now()
    chosen = kernel.probes if points is None else lambda _: iter(points)
    with (patch.object(kernel, "probes", chosen), patch.object(kernel, "ecef_states", states),
          patch.object(kernel, "possible_horizon", possible)):
        rows, score, meta = kernel._prepare_probe_scores(graph, catalogue, region)
    geometry_clock = clocks(start)
    order = [list(range(len(rows)))] if original_order is None else original_order(rows, region.width_km)
    phases, by_point = [], [None] * len(rows)
    with patch.object(kernel, "score_track", term), patch.object(kernel, "contrast_log_ratio", ratio):
        for batch in order:
            start = now()
            for index in batch:
                terms.clear()
                score(rows[index])
                if len(terms) != len(graph["tracks"]) or any(
                    entry[-1] != rows[index]["owners"][t["key"]]
                    for entry, t in zip(terms, graph["tracks"], strict=True)
                ):
                    raise ValueError("Measured scorer did not expose one original term per track")
                by_point[index] = terms.copy()
            phases.append(clocks(start))
    if len(propagation) != 2 or len(horizon) != 1 or any(t is None for t in by_point):
        raise ValueError("Expected both propagation stages and all original scores")
    (first, good), (second, usable) = propagation
    first = np.asarray(first)
    second = np.asarray(second)
    if not np.array_equal(first[good][horizon[0]], second):
        raise ValueError("Recorded horizon mask no longer matches the geometry candidate bank")
    bank = dict(first_propagation=first[good].tolist(), horizon_candidates=second.tolist(),
                usable=second[usable].tolist())
    return dict(points=rows, meta=meta, propagation=bank, geometry_clock=geometry_clock,
                score_clocks=phases, visibility_capture_cpu_s=capture_cpu), by_point


def compact_terms(all_terms):
    """Pack exact visibility and retain the leading mixture terms in track order."""
    import numpy as np

    result = []
    for terms in all_terms:
        row = []
        for labels, visible, ratios, value, owner in terms:
            top = None
            if ratios is not None:
                k = int(np.argmax(ratios))
                top = (int(labels[visible][k]), float(ratios[k]))
            row.append(dict(visible_count=int(visible.sum()), visible_packbits_hex=np.packbits(visible).tobytes().hex(),
                            top_log_ratio=top, mixture_term=value, owner=owner))
        result.append(row)
    return result


def family_terms(terms, families):
    result = []
    for labels, visible, ratios, _, _ in terms:
        ids = labels[visible].tolist()
        result.append({str(n): float(ratios[ids.index(n)]) for n in families if ratios is not None and n in ids})
    return result


def gate_replay(original, width, expected, snapshots, evaluate, execute):
    points = original["points"]
    terminal = execute(points, width, lambda point: point["receiver_scores"])
    complete = evaluate(points, width)
    observed = {**original["meta"], **terminal, "snapshots": snapshots}
    if json.loads(json.dumps(observed)) != {k: v for k, v in expected.items() if k not in ("bound_arms", "evaluated")}:
        raise ValueError("Original exact terminal or geometry no longer matches the sealed physical omission")
    if not complete["complete"] or terminal["would_withhold"] != complete["would_withhold"]:
        raise ValueError("Completing the original lattice changed the archived terminal")
    return dict(terminal=terminal, complete=complete)


def archive_admission(request, reader_class, identity):
    from exact_named_raw import staged_path

    path = staged_path(Path(request["archive"]["root"]))
    refs = reader_class(path).list_snapshots("space-track")
    if (len(refs) != 46 or identity(path) != request["archive"]
            or any(ref.collected_utc_ns >= request["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("Original causal input inventory changed")
    census = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE",
                                *(staged_path(ref.path, root=path) for ref in refs)]))["fincore"]
    if len(census) != len(refs) or any(row["res"] < row["size"] for row in census):
        raise ValueError("Original causal archive is not entirely resident")
    return path, refs, sum(row["size"] for row in census)


def site_reference():
    path = HERE.parent.parent/"2026_11_21_ds30_full/reference-audit.json"
    rows = json.loads(checked(path, REFERENCE_PIN))["cases"]
    (survey,) = (r["reference"] for r in rows if r["dataset_label"] == "DS30-0016" and r["authority_eligible"])
    return [survey["latitude_deg"], survey["longitude_deg"]]


def run(output, started):
    import empty_bootstrap as boot

    _, _, _, _, _ = boot.load_runtime()
    from aperture_trial import archive_identity, machine
    from exact_named_raw import staged_path
    from held_adaptive_0160 import catalogue_scope
    from leo.analysis.localization_v3.elements import ElementParser
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.tracks import prepare_tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.operations.causal_tle_catalogue import causal_catalogue
    from leo.operations.tle_archive import TleArchiveReader
    from tools.pipeline_eval.variants.experimental import regional_reassignment as kernel
    from tools.pipeline_eval.variants.experimental.regional_exterior_veto import evaluate
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal, probe_layout

    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected the shared single-core Gauss slot")
    checked(Path(kernel.__file__), SCORE_PIN)
    staged_path(output.parent)
    output.mkdir()
    phase = now()
    bound = input_binding()
    req = bound["request"]
    _, native = packet(bound)
    checked(Path(bound["saved_inventory"]), req["inventory"][7:])
    control = json.loads(gzip.decompress(checked(HERE/"measurements/history-risk-0016-omitted.json.gz", EXPECTED_PIN)))
    previous = control["result"]["route"]["history_risk"]
    expected = previous["boundary_checks"][0]["result"]
    path, refs, ref_bytes = archive_admission(req, TleArchiveReader, archive_identity)
    config = json.loads(checked(RELEASE/"assets/tracks.json", TRACK_CONFIG_PIN))["config"]
    offer = bound["omitted_offer"]
    region = SearchRegion(tuple(offer["center"]), width_km=offer["width_km"])
    write(output/"admission.json", dict(input={k: req[k] for k in ("native", "inventory", "authority", "detector",
                                                                  "archive", "cutoff_utc_ns", "recording")},
          offer=offer, offer_sha256=bound["omitted_offer_sha256"], prior_scout_commit=AUDIT_PIN, host=host,
          source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), scorer_sha256=SCORE_PIN,
          archive_snapshots=len(refs), archive_bytes=ref_bytes, radii=RADII, cpu_cap_s=CPU_CAP))
    parts = dict(admission=clocks(phase), startup_and_admission=clocks(started))
    phase = now()
    graph = prepare_tracks(native, TrackConfig(**config))
    if graph["metadata"]["causal_cutoff_utc_ns"] != req["cutoff_utc_ns"]:
        raise ValueError("Graph preparation moved the original causal cutoff")
    parts["graph"] = clocks(phase)
    write(output/"progress.json", parts)
    phase = now()
    archive_reads = Counter()
    reader = TleArchiveReader(path)
    parse = ElementParser()
    use = catalogue_scope(path, refs, req["cutoff_utc_ns"], TleArchiveReader.read, archive_reads)
    with patch.object(TleArchiveReader, "read", use):
        causal = causal_catalogue(reader, req["cutoff_utc_ns"], element_parser=parse)
    snapshots = sorted({row["snapshot_digest"] for row in causal.provenance})
    if snapshots != expected["snapshots"]:
        raise ValueError("Causal catalogue provenance changed")
    parts["catalogue"] = clocks(phase)
    write(output/"progress.json", parts)
    original, orig_terms = probe_bank(kernel, graph, causal.catalogue, region, original_order=probe_layout)
    terminal = gate_replay(original, region.width_km, expected, snapshots, evaluate, evaluate_terminal)
    parts["original"] = clocks(started)
    write(output/"progress.json", parts)
    broad, broad_terms = probe_bank(kernel, graph, causal.catalogue, region, points=axial_points(region, kernel.NORMALS))
    old = maxima(original["points"], region.width_km)
    extended = maxima(original["points"], region.width_km, broad["points"])
    wide_only = maxima([p for p in original["points"] if p["side"] == "inside"], region.width_km, broad["points"])
    cost = broad["geometry_clock"]["cpu_s"] + broad["score_clocks"][0]["cpu_s"]
    result = dict(admission_sha256=sha256((output/"admission.json").read_bytes()).hexdigest(),
                  clocks=parts, archive_reads=dict(archive_reads), parser=parse.statistics(),
                  active_snapshots=snapshots, membership=graph_membership(graph), original=original, broad=broad,
                  archived_terminal=terminal, original_maxima=old, augmented_maxima=extended, wider_only_maxima=wide_only,
                  broad_add_cpu_s=cost, paid_gap_s=GAP_S, broad_add_within_gap=cost <= GAP_S,
                  original_archived_guard_cpu_s=previous["lean_attempts"][0]["exterior_clocks"]["cpu_s"],
                  evaluated_points=len(original["points"])+len(broad["points"]), cap_s=CPU_CAP)
    original["terms"] = compact_terms(orig_terms)
    broad["terms"] = compact_terms(broad_terms)
    result["through_main_score"] = clocks(started)
    sealed = write(output/"blind-scout.json", result)
    write(output/"blind-seal.json", dict(sha256=sealed, through_main_seal=clocks(started)))
    if process_time() > CPU_CAP - 0.12:
        return

    # Reference coordinates and earlier owners are diagnostic inputs only after the blind score seal.
    truth = site_reference()
    site_xy = [(truth[1] - region.center[1]) * 111.32 * cos(radians(region.center[0])),
               (truth[0] - region.center[0]) * 111.]
    families = sorted({int(row[1]) for row in control["result"]["owner_changes"]["c0"]["changed"]})
    oracle, terms = probe_bank(kernel, graph, causal.catalogue, region,
                               points=[dict(side="exterior", xy_km=site_xy, latlon=truth)])
    oracle_point = oracle["points"][0]
    replacements = []
    for bank, detail in ((original, orig_terms), (broad, broad_terms), (oracle, terms)):
        replacements.append(dict(
            presence={stage: [n for n in families if n in values] for stage, values in bank["propagation"].items()},
            tracks=[family_terms(track_terms, families) for track_terms in detail]))
    gains = {rx: score - old["receivers"][rx]["inside_score"] for rx, score in oracle_point["receiver_scores"].items()}
    distances = {rx: hypot(*(a-b for a, b in zip(row["exterior_xy_km"], site_xy, strict=True)))
                 for rx, row in extended["receivers"].items()}
    write(output/"reference-diagnostic.json", dict(blind_scout_sha256=sealed, reference_sha256=REFERENCE_PIN,
          containing_owner_families=families, family_terms=replacements, score=oracle,
          gain_vs_original_inside=gains, augmented_exterior_distance_to_reference_km=distances,
          total_scored_points=result["evaluated_points"] + 1, total=clocks(started)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_original)
    started_at = (0.0, perf_counter())
    signal.setitimer(signal.ITIMER_PROF, max(1e-6, CPU_CAP-process_time()))
    run(args.output, started_at)
