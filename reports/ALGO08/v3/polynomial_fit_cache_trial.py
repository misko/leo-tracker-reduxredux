"""Price exact polynomial reuse on the saved DS30 physical Graph preparations."""

import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
from statistics import mean
from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import RELEASE, archive_identity, configuration, inputs, read, solve, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from local_future_policy import TRACKS_SHA256
from polynomial_fit_cache import MAX_ARRAY_ITEMS, MAX_ENTRIES, SOURCE_PINS, installed_sources, reuse


HERE = Path(__file__).resolve().parent
ORDER = ("stock", "best", "piece", "both", "both", "piece", "best", "stock")
CASES = ("DS30-0008", "DS30-0016")
WEAK_ROOT = Path("/var/tmp/leo-v3-weak-combined-warm-Nov23/stock")
WEAK_RECEIPT = "a704861e37e40e7364fbf97bcb74e98bb9c701ca474c12821e8ed7df86cab233"
DENSE_PACKET = "sha256:2df28e68ea845576ea5e8a02057bce32983dbafb469fa2c4f710a3d89729fa85"


def recorded(case):
    from leo.contracts.digests import canonical_digest

    if case == CASES[0]:
        native, archive, region, expected, identity = inputs(case)
        if identity["native_sha256"] != DENSE_PACKET:
            raise ValueError("Expected the original dense installed-v3 detector")
        return native, archive, region, expected, identity
    ledger = read(checked(HERE / "measurements/weak-combined-raw.json", WEAK_RECEIPT))
    request, baseline = ledger["binding"]["request"], ledger["runs"]["stock"]
    (native_path,) = (WEAK_ROOT / "fast-scan-automatic-work").glob("*/detections.json")
    (terminal_path,) = (WEAK_ROOT / "fast-scan-automatic-work").glob("*/terminal.json")
    native, terminal = read(checked(native_path, baseline["native_sha256"])), read(checked(terminal_path, baseline["terminal_sha256"]))
    archive = Path(request["archive"]["root"])
    identity = dict(case=case, native_sha256=baseline["native_sha256"], offer=request["offered_region"],
                    archive=request["archive"], raw_authority=request["raw_authority"],
                    detector_sha256=native["provenance"]["detector_sha256"])
    if (archive_identity(archive) != identity["archive"] or terminal["native_sha256"] != canonical_digest(native)
            or terminal["region"] != identity["offer"] or terminal["arms"] != baseline["arms"]
            or native["source"]["raw_recording_authority_digest"] != identity["raw_authority"]
            or native["source"]["session_id"] != request["session"]):
        raise ValueError("Expected original weak installed-v3 authority and science")
    expected = dict(status=terminal["decision"], reason=terminal["reason"], orbit_policy=terminal["orbit_policy"],
                    arms=baseline["arms"], owners=baseline["owners"], science=baseline["scientific_digests"])
    return native, archive, identity["offer"], expected, identity


def paired_savings(rows):
    start, end = rows[0]["cpu_s"], rows[-1]["cpu_s"]
    return {mode: [start-next(r["cpu_s"] for r in rows if r["mode"] == mode),
                   end-next(r["cpu_s"] for r in reversed(rows) if r["mode"] == mode)]
            for mode in ("best", "piece", "both")}


def graph(case, output, census_only=False):
    machine = host()
    publication, spec = configuration()
    publication._checked_graph_path(spec)
    if not spec["defer_preparation_gc"]:
        raise ValueError("Expected installed preparation collection policy")
    poly, tracks = installed_sources()
    from tools.pipeline_eval.variants.experimental.graph_path import native_paths
    from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection
    from tools.pipeline_eval.variants.track_preparation import fingerprint

    native, _, _, _, identity = recorded(case)
    if identity["detector_sha256"] != "sha256:" + spec["detector_sha256"]:
        raise ValueError("Expected the installed detector packet")
    config = poly.TrackConfig(**read(checked(RELEASE / "assets/tracks.json", TRACKS_SHA256))["config"])
    prepare = defer_collection(tracks.prepare_tracks)
    rows = []
    for mode in (("census",) if census_only else (*ORDER, "census")):
        counts = Counter()
        with native_paths(Path(spec["graph_path"]["library"]), required=True) as paths, reuse(mode, counts):
            cpu, wall = process_time(), perf_counter()
            prepared = prepare(native, config)
            elapsed = dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-wall)
        rows.append(dict(mode=mode, digest=fingerprint(prepared), native_path=dict(paths), **elapsed, cache=dict(counts)))
    switches = {tuple(row["native_path"].get(k, 0) for k in ("packed_lanes", "native_paths", "reference_paths"))
                for row in rows}
    if len({row["digest"] for row in rows}) != 1 or len(switches) != 1 or next(iter(switches))[1] == 0:
        raise ValueError("Polynomial cache changed the complete Graph preparation or native path coverage")
    census = rows.pop()
    counts = census["cache"]
    duplicate_costs = dict(best_original_s=counts.get("best_original_duplicate_cpu_ns", 0)/1e9,
                           piece_original_s=counts.get("piece_original_duplicate_cpu_ns", 0)/1e9,
                           extra_piece_original_s=counts.get("piece_duplicate_cpu_ns_outside_duplicate_best", 0)/1e9)
    write(output, dict(case=case, identity=identity, machine=machine, preparation=rows, census=census,
                       cumulative_disjoint_census_s=duplicate_costs["best_original_s"]+duplicate_costs["extra_piece_original_s"],
                       census_original_calls=duplicate_costs, paired_savings_s=paired_savings(rows) if rows else {},
                       limits=dict(entries_per_function_per_lane=MAX_ENTRIES, array_items=MAX_ARRAY_ITEMS),
                       graph=dict(points=prepared["graph_points"], tracks=len(prepared["tracks"]),
                                  curved=len(prepared["curved_indices"]), observations=len(prepared["observations"])),
                       sources=SOURCE_PINS, track_asset_sha256=TRACKS_SHA256, graph_path_sha256=spec["graph_path"]["sha256"]))


def eligibility(dense, weak):
    checks = {}
    for mode in ("best", "piece", "both"):
        first, second = dense["paired_savings_s"][mode]
        weak_slowdown = -mean(weak["paired_savings_s"][mode])
        checks[mode] = dict(dense_mean_saving=mean((first, second)), weak_mean_slowdown=weak_slowdown,
                            passes=first > 0 and second > 0 and mean((first, second)) >= .10 and weak_slowdown <= .03)
    eligible = [mode for mode, data in checks.items() if data["passes"]]
    return checks, max(eligible, key=lambda x: checks[x]["dense_mean_saving"], default=None)


def downstream(case, dense_graph, weak_graph, output):
    machine = host()
    dense, weak = read(dense_graph), read(weak_graph)
    checks, mode = eligibility(dense, weak)
    if mode is None:
        raise ValueError("No graph-only backend passed the frozen downstream gate")
    publication, spec = configuration()
    native, archive, region, expected, identity = recorded(case)
    comparison = dense if case == CASES[0] else weak
    if comparison["identity"] != identity or comparison["sources"] != SOURCE_PINS:
        raise ValueError("Downstream replay must use the eligible graph-only configuration")
    from leo.application import localization_v3
    from tools.pipeline_eval.variants.track_preparation import fingerprint

    original, captured, counts = localization_v3.prepare_tracks, [], Counter()

    def prepare(*args, **options):
        result = original(*args, **options)
        captured.append(result)
        return result

    with patch.object(localization_v3, "prepare_tracks", prepare), reuse(mode, counts):
        result = solve(publication, spec, native, archive, region)
    digest, = map(fingerprint, captured)
    exact = {name: result[name] == value for name, value in expected.items()}
    if not all(exact.values()) or digest != comparison["preparation"][0]["digest"]:
        raise ValueError(f"Saved downstream scientific parity failed for {case}: {exact}")
    result.pop("owner_rows", None)
    write(output, dict(case=case, mode=mode, machine=machine, input=identity, graph_digest=digest, result=result,
                       exact=exact, eligibility=checks, cache=dict(counts),
                       eligibility_receipts=[sha256(path.read_bytes()).hexdigest() for path in (dense_graph, weak_graph)]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    stages = parser.add_subparsers(dest="stage", required=True)
    for name in ("graph", "downstream"):
        sub = stages.add_parser(name)
        sub.add_argument("case", choices=CASES)
        if name == "downstream":
            sub.add_argument("dense_graph", type=Path)
            sub.add_argument("weak_graph", type=Path)
        else:
            sub.add_argument("--census-only", action="store_true")
        sub.add_argument("output", type=Path)
    args = vars(parser.parse_args())
    (graph if args.pop("stage") == "graph" else downstream)(**args)
