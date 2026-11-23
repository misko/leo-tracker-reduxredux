"""Run the native discovery reward on sealed measured aperture packets."""

import argparse
from contextlib import contextmanager, nullcontext
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from time import perf_counter, process_time
from types import SimpleNamespace

from aperture_trial import RELEASE, configuration, read, write
from dense_full_short_raw import checked
from dense_geographic_trial import host
from discovery_margin import THRESHOLD, WeightedPath, build, discovery_weights, factor_weights, weighted_source
from eight_ms_crossover import BINDING_SHA, CASE_ROOTS, PACKET_PINS, originals
from full_short_physical import environment
from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA, checked_recipe, geographic_projection
from local_future_policy import TRACKS_SHA256
from weak_combined_raw import measure


GRAPH_ORDER = ("stock", "unit", "weighted", "weighted", "unit", "stock", "unit_audit")
SOLVE_ORDER = ("unit", "weighted")
APERTURES = ("12ms", "8ms")


def packet_pin(case, aperture):
    return PACKET_PINS[case][APERTURES.index(aperture)]


def verified_input(case, aperture):
    original, (path,), (native,) = originals(case, (aperture,))
    seal = read(CASE_ROOTS[case] / aperture / "full-short-recipe.json")
    _, counts = factor_weights(native, unit=True)
    if (seal["recipe"] != checked_recipe(aperture == "8ms") or seal["graph"] != "installed"
            or seal["saved_digest"] is not None or seal["receiver_audit"]["selected"] != sum(counts.values())):
        raise ValueError("Aperture input must reproduce the original unfiltered raw receiver receipt")
    return original, path, native


def library_from(build_path):
    receipt = read(build_path / "build.json")
    if sha256(weighted_source().encode()).hexdigest() != receipt["source_sha256"]:
        raise ValueError("Weighted recurrence source changed since compilation")
    return checked(build_path / "weighted-graph.so", receipt["binary_sha256"])


def graph(case, build_path, output, shape_only=False, aperture="8ms"):
    system = host()
    publication, spec = configuration()
    publication._checked_graph_path(spec)
    from leo.analysis.localization_v3 import tracks
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.application.localization_v3_engine import _json_value
    from tools.pipeline_eval.variants.experimental.graph_path import native_paths
    from tools.pipeline_eval.variants.experimental.preparation_gc import defer_collection
    from tools.pipeline_eval.variants.track_preparation import fingerprint

    library = library_from(build_path)
    _, _, native = verified_input(case, aperture)
    cfg = TrackConfig(**read(checked(RELEASE / "assets/tracks.json", TRACKS_SHA256))["config"])
    prepare = defer_collection(tracks.prepare_tracks)
    WeightedPath(library)
    rows = []
    for mode in (SOLVE_ORDER if shape_only else GRAPH_ORDER):
        counts = {}
        with native_paths(Path(spec["graph_path"]["library"]), required=True) as paths:
            scope = nullcontext() if mode == "stock" else discovery_weights(
                native, library, mode="weighted" if mode == "weighted" else "unit", counts=counts, verify=mode == "unit_audit")
            cpu, wall = process_time(), perf_counter()
            with scope:
                prepared = prepare(native, cfg)
            clocks = dict(cpu_s=process_time()-cpu, elapsed_s=perf_counter()-wall)
        rows.append(dict(mode=mode, clocks=clocks, paths=dict(paths), reward=counts, graph=fingerprint(prepared),
                         solver_shape=fingerprint(json.loads(json.dumps(prepared, default=_json_value, allow_nan=False))),
                         observations=fingerprint(prepared["observations"]), graph_points=prepared["graph_points"],
                         tracks=len(prepared["tracks"]), curved=len(prepared["curved_indices"])))
        if paths["reference_paths"] or (mode != "stock" and counts.get("path_calls", 0) != paths["native_paths"]):
            raise ValueError("Expected all eligible ordered paths to use the requested native recurrence")
    if (len({row["observations"] for row in rows}) != 1
            or len({row["graph"] for row in rows if row["mode"] != "weighted"}) != 1
            or len({row["graph"] for row in rows if row["mode"] == "weighted"}) != 1
            or (not shape_only and rows[-1]["reward"]["verified_calls"] != rows[-1]["paths"]["native_paths"])):
        raise ValueError("Graph measurement, determinism or unit-native parity failed")
    write(output, dict(case=case, aperture=aperture, packet_sha256=packet_pin(case, aperture), machine=system, threshold=THRESHOLD,
                       trials=rows, weighted_native_sha256=sha256(library.read_bytes()).hexdigest(),
                       original_native=spec["graph_path"]))


def worker(case, mode, build_path, geo, output, regional=None, aperture="8ms"):
    from joint_publication import run
    from tools.pipeline_eval.variants.track_preparation import fingerprint

    root = CASE_ROOTS[case]
    original = read(checked(root / "binding.json", BINDING_SHA[case]))
    packet, = (root / aperture / "fast-scan-automatic-work").glob("*/detections.json")
    native = read(packet)
    library = library_from(build_path)
    request = original["request"]
    count, captured = {}, []

    @contextmanager
    def scope():
        with geographic_projection(geo, regional) as projection, discovery_weights(native, library, mode=mode, counts=count):
            yield projection

    def observe(prepared):
        tracks = prepared["tracks"]
        captured.append(tracks)
        return dict(graph_points=tracks["graph_points"], tracks=len(tracks["tracks"]), curved=len(tracks["curved_indices"]))

    args = SimpleNamespace(recording=Path(request["recording"]), archive=Path(request["archive"]["root"]),
                           region=Path(request["region_file"]), saved=packet, saved_digest=packet_pin(case, aperture),
                           output=output, optimized_full_catalogue=True, verify_images=True, observe_prepared=observe)
    result = run(args, early_regional=True, keep_selected_rows=True,
                 saved_receiver=native["provenance"]["detector_sha256"].removeprefix("sha256:"),
                 geographic_projector=scope, reuse_cold_rows=True, reuse_grid_phase_states=True)
    if len(captured) != 1 or count.get("path_calls", 0) <= 0:
        raise ValueError("The saved study expected one prepared graph and the weighted native route")
    write(output / "discovery-margin.json", dict(mode=mode, aperture=aperture, threshold=THRESHOLD, counts=count,
          graph=fingerprint(captured[0]), observations=fingerprint(captured[0]["observations"]),
          terminal=result["receipt"]["terminal_sha256"], disclosure="research Graph discovery heuristic on unchanged measured factors"))


def replay(case, build_path, geo, graph_trial, output, regional=None, aperture="8ms"):
    system = host()
    checked(geo, GEOGRAPHIC_SHA)
    if (regional is not None) != (case == "north"):
        raise ValueError("Expected original per-recording geographic library settings")
    if regional is not None:
        checked(regional, TRACK_SCORES_SHA)
    trial = read(graph_trial)
    library = library_from(build_path)
    original, _, _ = verified_input(case, aperture)
    if (trial["case"] != case or trial.get("aperture", "8ms") != aperture or trial["packet_sha256"] != packet_pin(case, aperture)
            or trial["weighted_native_sha256"] != sha256(library.read_bytes()).hexdigest()):
        raise ValueError("Saved publication differs from the checked graph-only trial")
    output.mkdir()
    env = environment(output)
    python = str(RELEASE / "venv/bin/python")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, env=env, timeout=30)
    commands = {}
    for mode in SOLVE_ORDER:
        command = [python, "-BPs", str(Path(__file__).resolve()), "worker", case, mode, str(build_path),
                   str(geo), str(output / mode), "--aperture", aperture]
        if regional is not None:
            command.extend(["--regional", str(regional)])
        commands[mode] = command
    write(output / "binding.json", dict(case=case, aperture=aperture, machine=system, commands=commands, request=original["request"],
          inventory=original["inventory"], order=SOLVE_ORDER, graph_trial_sha256=sha256(graph_trial.read_bytes()).hexdigest()))
    for mode, command in commands.items():
        measure(command, env, output, mode)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    subs = cli.add_subparsers(dest="action", required=True)
    subs.add_parser("build").add_argument("output", type=Path)
    for action in ("graph", "replay", "worker"):
        sub = subs.add_parser(action)
        sub.add_argument("case", choices=CASE_ROOTS)
        sub.add_argument("--aperture", default="8ms", choices=APERTURES)
        if action == "worker":
            sub.add_argument("mode", choices=SOLVE_ORDER)
        sub.add_argument("build_path", type=Path)
        if action != "graph":
            sub.add_argument("geo", type=Path)
            sub.add_argument("--regional", type=Path)
        if action == "replay":
            sub.add_argument("graph_trial", type=Path)
        if action == "graph":
            sub.add_argument("--shape-only", action="store_true")
        sub.add_argument("output", type=Path)
    args = vars(cli.parse_args())
    {"build": build, "graph": graph, "replay": replay, "worker": worker}[args.pop("action")](**args)
