"""Replay the complete published Graph path while forming the frozen CFO edits."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch

import moment_fast_graph as stage


PAYLOAD = Path("/opt/leo-algo08/algo08v3/payload")
LIBRARY = PAYLOAD / "graph-path.so"
PATH_MODULE = "tools/pipeline_eval/variants/experimental/graph_path.py"
PATH_SOURCE = "tools/pipeline_eval/variants/experimental/graph_path.c"
PIN = {
    "spec.json": "652f8573e2fdec746dd318849c82992eb7786f014e8dbc393c0352b54e421e46",
    "graph-path.so": "e623daaff9ac9fddc709d26af2a1fecd696aa133568c3d6c0a4d10e6b481d627",
    PATH_MODULE: "289bd1b9dbf1559e4610013cdaed619a388e2d4a59c96c1956df42329483478c",
    PATH_SOURCE: "cbbee06c6305f82a096561ae6498ef163786e7c82af95e11af0dbf8b7da030eb",
}
PROTOCOL = "57f91831959b24c3d8327046b08b79ee74ed8d5532d84f057e8dbe8e9edad9b4"
PREVIOUS = "ec5b8957a3afc3523c32b271b05d09ea8a099471f357417c1623a220242a81d7"
PREVIOUS_NAME = "measurements/moment-fast-graph-comparison.json"


def prior_port(receipt):
    counters = receipt["receipt"]["graph_path"]
    if (not all(type(counters.get(key)) is int and counters[key] > 0 for key in (
            "native_paths", "packed_lanes", "pack_ns", "search_ns")) or counters.get("reference_paths", 0)):
        raise ValueError("The edited Graph receipt needs native paths and measured packing with zero fallback")
    return counters


def preparation():
    stage.checked(stage.HERE / "moment-fast-graph-full-protocol.md", PROTOCOL)
    prior = stage.document(stage.HERE / PREVIOUS_NAME, PREVIOUS)
    for name, pin in PIN.items():
        stage.checked(PAYLOAD / name, pin)
    spec = stage.document(PAYLOAD / "spec.json", PIN["spec.json"])
    if (spec["graph_path"]["sha256"] != PIN["graph-path.so"]
            or any(spec["sources"][name] != PIN[name] for name in (PATH_MODULE, PATH_SOURCE, "graph-path.so"))):
        raise ValueError("The released publication does not bind the exact native path port")
    history = {}
    for case, (root, seal, _, _) in stage.CELLS.items():
        if not prior["cases"][case]["parity"]["identical_invariants"] or any(
                "native_paths" in item for run in prior["cases"][case]["modes"].values()
                for item in run["graph_ports"].values()):
            raise ValueError("Do not repeat a complete port or extend a failed initial trial")
        pins = stage.document(root / "verification-pins.json", seal)["corrected"]
        receipt = stage.document(root / "corrected/receipt.json", pins["receipt"])
        history[case] = prior_port(receipt)
    return dict(base=stage.preparation(), payload_sha256=PIN, previous_sha256=PREVIOUS,
                historical_edited_native_paths=history, protocol_sha256=PROTOCOL,
                source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


@contextmanager
def complete(exact_graph, native_paths):
    original = exact_graph.graph_execution

    @contextmanager
    def install(*, enabled=False, audit=None):
        if not enabled:
            with original(enabled=False, audit=audit):
                yield
            return
        with native_paths(LIBRARY, required=True) as paths:
            with original(enabled=True, audit=audit):
                yield
        if audit is not None:
            audit["native_paths"] = dict(paths)

    with patch.object(exact_graph, "graph_execution", install):
        yield


def used_native(run):
    for port in run["graph_ports"].values():
        counts = port["native_paths"]
        if not (counts.get("native_paths", 0) > 0 and counts.get("packed_lanes", 0) > 0
                and counts.get("pack_ns", 0) > 0 and counts.get("search_ns", 0) > 0
                and not counts.get("reference_paths", 0) and not counts.get("unpacked_lanes", 0)):
            return False
    return True


def canonical_equal(a, b):
    return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)


def child(args):
    stage.require_child(args.lease_fd)
    sys.addaudithook(stage.no_science_files)
    prepared = stage.document(args.preflight, args.pin)
    if prepared != preparation():
        raise ValueError("The full-port preflight differs from what was reviewed")

    import exact_graph_execution as exact_graph
    from leo.analysis import graph_tracklets, polynomial_tracklets, tracklet_fitting
    from leo.analysis.localization_v3 import tracks
    from tools.pipeline_eval.variants.experimental import graph_path

    if (Path(graph_path.__file__).resolve() != PAYLOAD / PATH_MODULE
            or any(Path(module.__file__).resolve() != stage.RELEASE / "src" /
                   (module.__name__.replace(".", "/") + ".py")
                   for module in (graph_tracklets, polynomial_tracklets, tracklet_fitting, tracks))):
        raise ValueError("Require the released Graph modules and complete native path source")
    cfg = polynomial_tracklets.TrackConfig(**stage.document(stage.RELEASE / "assets/tracks.json",
                                                               stage.RELEASE_PINS["assets/tracks.json"])["config"])
    earlier = stage.document(stage.HERE / PREVIOUS_NAME, PREVIOUS)
    results, passed = {}, True
    with complete(exact_graph, graph_path.native_paths):
        start = stage.now()
        with exact_graph.graph_execution(enabled=True):
            pass
        setup = stage.elapsed(start)
        for case, (_, _, _, order) in stage.CELLS.items():
            source, observation, metadata = stage.snapshot(case, native=True)
            arms = {mode: stage.execute(source, cfg, observation, fast=(mode == "fast")) for mode in order}
            parity = stage.compare(arms["stock"], arms["fast"])
            prior = earlier["cases"][case]["modes"]["fast"]["invariants"]
            previous_exact = canonical_equal(arms["fast"][0]["invariants"], prior)
            native_exact = used_native(arms["fast"][0])
            passed = (parity["identical_invariants"] and parity["stock_sealed_exact"] and parity["fast_sealed_exact"]
                      and previous_exact and native_exact)
            results[case] = dict(**metadata, modes={("full" if mode == "fast" else mode): value[0]
                                                     for mode, value in arms.items()}, parity=parity,
                                 previous_vector_cache_exact=previous_exact, all_graph_lanes_used_native=native_exact,
                                 historical_edited_native_paths=prepared["historical_edited_native_paths"][case])
            if not passed:
                break
    return dict(status="exact" if passed else "stopped_at_parity_gate", cases=results,
                complete_port_initialization=setup, preflight_sha256=args.pin,
                previous_sha256=PREVIOUS, timing_runs=1, graph_preparations=4*len(results),
                receiver_runs=0, solver_runs=0, waveform_reads=0, archive_reads=0, survey_reads=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "watch", "child"))
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--pin")
    parser.add_argument("--driver", type=int)
    parser.add_argument("--lease-fd", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        sys.addaudithook(stage.no_science_files)
        result = preparation()
    elif args.mode == "watch":
        result = stage.watch(args.preflight, args.pin, args.driver, args.output, worker=Path(__file__))
    else:
        result = child(args)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
