"""Saved dense and omitted-offer proof replays for the contiguous native kernel."""

import argparse
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import subprocess
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, read, solve, write


HERE = Path(__file__).resolve().parent
DENSE = "DS30-0008"
SOUTH = "south-far"
CASES = (DENSE, SOUTH)
SCORE_TOLERANCE = 1e-10
SOUTH_GATE_SHA = "137472ab2997eb64a4a8c061819ae1f25208e9dad7b7babb40996291f1e94c06"
LIVE_CONTROL_SHA = "22f6a006e0958476c4a46591af1c1159e8f4c95ed60a13604db57831e20bbd79"


def now():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    return dict(cpu_s=(process_time_ns()-start[0])/1e9, elapsed_s=(perf_counter_ns()-start[1])/1e9)


def host():
    current = machine()
    if (current["cpu"] != [2] or current["nice"] < 15 or "prio 7" not in current["ionice"]
            or any(value != "1" for value in current["threads"].values())):
        raise ValueError("Expected the shared low-priority one-core slot")
    return current


def build(directory):
    current = host()
    directory.mkdir()
    source, binary = HERE / "dense_geographic_projection.c", directory / "geographic.so"
    vector_report = directory / "vectorization.txt"
    command = ["cc", "-O3", "-march=haswell", "-fopenmp-simd", "-ffp-contract=off", "-fno-math-errno",
               "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", f"-fopt-info-vec-optimized={vector_report}",
               str(source), "-lm", "-o", str(binary)]
    start = now()
    launch = subprocess.run(["/usr/bin/time", "-f", "%U %S", *command], text=True, capture_output=True)
    launch.check_returncode()
    clocks = elapsed(start)
    user, system = map(float, launch.stderr.split())
    write(directory / "build.json", dict(machine=current, command=command, compiler_cpu_s=user+system,
          elapsed_s=clocks["elapsed_s"], source_sha256=sha256(source.read_bytes()).hexdigest(),
          binary_sha256=sha256(binary.read_bytes()).hexdigest(),
          compiler=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
          vectorization=vector_report.read_text().splitlines() if vector_report.exists() else []))


def south_packet():
    from mixed_aperture_crossed import prepare

    path = HERE / "measurements/full-short-south-far-gate.json"
    body = path.read_bytes()
    if sha256(body).hexdigest() != SOUTH_GATE_SHA:
        raise ValueError("Saved southern terminal comparison changed")
    old = json.loads(body)
    native, archive, offered, identity, paid = prepare(SOUTH, "all-primary")
    expected = old["result"]["identity"]
    if not paid or any(identity[k] != expected[k] for k in ("native_sha256", "archive", "offer", "graph_parameters")):
        raise ValueError("The southern witness uses different paid factors or graph")
    return native, archive, offered, identity, old["proof"][0]["result"]


def difference(a, b):
    """Report the largest float drift and preserve every discrete field."""
    if type(a) in (float, int) and type(b) in (float, int) and (type(a) is float or type(b) is float):
        return abs(a-b)
    if type(a) in (tuple, list) and type(b) in (tuple, list) and len(a) == len(b):
        return max((difference(x, y) for x, y in zip(a, b, strict=True)), default=0.)
    if isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys():
        return max((difference(a[key], b[key]) for key in a), default=0.)
    return 0. if a == b else float("inf")


def probe_pass(tracks, catalogue, region, projector, case):
    import numpy as np
    from dense_geographic_projection import checked_runtime
    from tools.pipeline_eval.variants.experimental.regional_veto_short_circuit import evaluate_terminal

    kernel, original = checked_runtime()
    recorded = []
    orbit_geometry = kernel.orbit_geometry

    def capture(*args):
        result = orbit_geometry(*args)
        recorded.append(result[0])
        return result

    start = now()
    with patch.object(kernel, "orbit_geometry", capture):
        points, score, meta = kernel._prepare_probe_scores(tracks, catalogue.catalogue, region)
    geometry_elapsed = elapsed(start)
    geometry, = recorded
    if geometry is None:
        raise ValueError("Expected eligible orbit-time cells")
    runs = {}
    for name in (("control", "native") if case == DENSE else ("native", "control")):
        visited = []

        def scored(point):
            row = score(dict(point))
            visited.append(row)
            return row["receiver_scores"]

        with patch.object(kernel, "phase_linear_frequency", projector if name == "native" else original):
            start = now()
            terminal = evaluate_terminal(points, region.width_km, scored)
            timing = elapsed(start)
        runs[name] = dict(visited=visited, terminal=dict(terminal, **meta, snapshots=sorted(
            {row["snapshot_digest"] for row in catalogue.provenance})), **timing)
    calls = dict(projector.counts)
    errors = []
    for point in (runs["control"]["visited"][0], runs["control"]["visited"][-1]):
        stock = original(geometry, *point["latlon"])
        candidate = projector(geometry, *point["latlon"])
        errors.append(dict(latitude_longitude=point["latlon"], cells=stock[0].size,
                           frequency_max_hz=float(np.max(np.abs(stock[0]-candidate[0]))),
                           tangent_max_hz_per_s=float(np.max(np.abs(stock[2]-candidate[2]))),
                           horizon_mismatches=int(np.count_nonzero((stock[1] >= 0) != (candidate[1] >= 0)))))
    p, n = runs["control"], runs["native"]
    # Owners, lattice and receiver keys stay discrete, while score fields have a fixed small tolerance.
    holds = len(p["visited"]) == len(n["visited"]) and all(
        a["owners"] == b["owners"] and a["xy_km"] == b["xy_km"] and a["latlon"] == b["latlon"] and a["side"] == b["side"]
        for a, b in zip(p["visited"], n["visited"], strict=True))
    probe_delta = difference(p["visited"], n["visited"])
    terminal_delta = difference(p["terminal"], n["terminal"])
    holds &= probe_delta <= SCORE_TOLERANCE and terminal_delta <= SCORE_TOLERANCE
    accepted = (holds and calls.get("calls") == len(n["visited"]) and not calls.get("original_fallback")
                and all(e["horizon_mismatches"] == 0 and max(e["frequency_max_hz"], e["tangent_max_hz_per_s"]) <= 1e-7
                        for e in errors))
    return dict(runs=runs, rebuilt_geometry=geometry_elapsed,
                visited_probe_max_difference=probe_delta if isfinite(probe_delta) else None,
                terminal_max_difference=terminal_delta if isfinite(terminal_delta) else None,
                evidence_matches=accepted, native=calls, arrays=errors,
                saved_probe_cpu_s=p["cpu_s"]-n["cpu_s"])


def run(case, stage, directory, output, *, gate=None):
    current = host()
    publication, spec = configuration()
    from dense_geographic_projection import Projector, checked_runtime
    from early_region import before_fit
    from joint_publication import full_catalogue_route
    from optimized_grid import reduced_grid
    from paid_quadratic import quadratic
    from prepared_exterior import handoff
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    if stage == "full":
        if case != DENSE or gate is None:
            raise ValueError("The complete replay requires its paired dense proof")
        measured = read(gate)
        if (measured["case"] != DENSE or not measured["probe"]["evidence_matches"]
                or measured["probe"]["saved_probe_cpu_s"] < 1.):
            raise ValueError("The dense native proof did not pass its timing and scientific gate")
    build = read(directory / "build.json")
    start = now()
    kernel, original = checked_runtime()
    projector = Projector(directory / "geographic.so", build["binary_sha256"], original)
    setup = elapsed(start)
    if case == SOUTH:
        native, archive, offered, identity, southern_proof = south_packet()
    else:
        native, archive, offered, _, identity = inputs(case)
        southern_proof = None
    if stage == "full" and measured["identity"] != identity:
        raise ValueError("The complete solve changed the paired proof input")
    original_solve = algo08_position.solve
    regional, attempts, visited, extra = [], [], [], {}

    def observed(document, reader, assets, region):
        if document is not native or reader.root != archive or region.document() != offered:
            raise ValueError("Unmatched saved authority")
        with ExitStack() as scopes:
            live, catalogue_counts, _ = scopes.enter_context(handoff(reader))
            if case == SOUTH:
                config = algo08_position.TrackConfig
                scopes.enter_context(patch.object(algo08_position, "TrackConfig", lambda **rows: quadratic(config(**rows))))

            def proof_only(prepared, view, _bound, _stages, **options):
                tracks = prepared["tracks"]
                catalogue = live.match(tracks, reader)
                if catalogue is None:
                    raise ValueError("The exact original prepared catalogue was unavailable")
                extra["probe"] = probe_pass(tracks, catalogue, view, projector, case)
                if case == SOUTH:
                    original_proof = extra["probe"]["runs"]["control"]["terminal"]
                    candidate_proof = extra["probe"]["runs"]["native"]["terminal"]
                    # The sealed metadata stores receiver-point count keys as JSON strings.
                    terminal_delta = difference(json.loads(json.dumps(original_proof)), southern_proof)
                    if (terminal_delta > SCORE_TOLERANCE
                            or not extra["probe"]["evidence_matches"]):
                        raise ValueError(f"The omitted offer differs from its published proof by {terminal_delta}")

                    def unexpected(*args, **kwargs):
                        raise ValueError("The omitted offer incorrectly entered a fit")

                    return before_fit(unexpected, reader, lambda *_a, **_k: candidate_proof, regional, live.match)(
                        prepared, view, _bound, _stages, **options)
                return dict(status="withheld", reason="probe_measurement_only", arms={a: {"latlon": None} for a in ARMS})

            route = proof_only
            if stage == "full":
                grid = scopes.enter_context(reduced_grid())
                fitted = full_catalogue_route(v5_core.infer, reader, attempts, optimized=True)
                route = before_fit(fitted, reader, regional_bound_guard.causal_probes, regional, live.match)
                prepare = kernel._prepare_probe_scores

                def audit(*args):
                    points, score, meta = prepare(*args)

                    def scored(point):
                        result = score(point)
                        visited.append(dict(result))
                        return result

                    return points, scored, meta

                scopes.enter_context(patch.object(kernel, "phase_linear_frequency", projector))
                scopes.enter_context(patch.object(kernel, "_prepare_probe_scores", audit))
            scopes.enter_context(patch.object(v5_core, "infer", route))
            start = now()
            decision, packet, policy = original_solve(document, reader, assets, region)
            extra["measure"] = elapsed(start)
        extra["catalogue"] = catalogue_counts
        if packet is not None:
            extra.update(grid={k: v for k, v in packet["position_grid"].items() if k not in ("binding", "elapsed_seconds")},
                         selected_rows={arm: [[r[key] for key in ("observation_id", "norad", "role")] for r in packet["rows"][arm]]
                                        for arm in ARMS},
                         grid_kernel=grid)
        return decision, packet, policy

    with patch.object(algo08_position, "solve", observed):
        result = solve(publication, spec, native, archive, offered)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("The causal archive changed during measurement")
    result.pop("owner_rows", None)
    write(output, dict(result, case=case, stage=stage, build=build, machine=current, setup=setup, identity=identity,
                       regional=regional, attempts=attempts, visited_probes=visited, native=dict(projector.counts), **extra))


def score(directory, summary, full):
    archived = HERE / "measurements/live-inference-profile.json.gz"
    blob = archived.read_bytes()
    if sha256(blob).hexdigest() != LIVE_CONTROL_SHA:
        raise ValueError("The archived complete live control changed")
    reference = json.loads(gzip.decompress(blob))["runs"]["control"]
    files = {name: directory / (name + ".json") for name in ("dense-probe", "south-probe", "dense-full")}
    paired = {name: read(path) for name, path in files.items()}
    candidate = paired["dense-full"]
    checks = {key: candidate[key] == reference[key] for key in (
        "identity", "status", "reason", "orbit_policy", "arms", "owners", "selected_rows", "associated",
        "science", "grid", "grid_points", "objective_replay",
    )}
    probe_error = difference(candidate["visited_probes"], reference["visited_probes"])
    checks["visited_probes"] = probe_error <= SCORE_TOLERANCE and bool(candidate["visited_probes"])
    checks["regional_decision"] = (difference(candidate["regional"][0]["result"], reference["regional"][0]["result"])
                                   <= SCORE_TOLERANCE)
    checks["optimizer_route"] = [row["decision"] for row in candidate["attempts"]] == [
        row["decision"] for row in reference["attempts"]]
    recovered = {"dense": paired["dense-probe"], "south": paired["south-probe"]}
    probes = {}
    for name, row in recovered.items():
        evidence = row["probe"]
        probes[name] = dict(
            setup=row["setup"], geometry=evidence["rebuilt_geometry"], native_counters=evidence["native"],
            evidence_matches=evidence["evidence_matches"], arrays=evidence["arrays"],
            probe_difference=evidence["visited_probe_max_difference"], terminal_difference=evidence["terminal_max_difference"],
            proof={arm: {k: v for k, v in result.items() if k != "visited"} for arm, result in evidence["runs"].items()},
        )
    accepted = (all(checks.values()) and all(row["evidence_matches"] for row in probes.values())
                and paired["south-probe"]["status"] == "withheld"
                and paired["south-probe"]["reason"] == "both_receivers_support_far_exterior"
                and not paired["south-probe"]["attempts"])
    result = dict(
        accepted=accepted, checks=checks, probe_difference_full=probe_error if isfinite(probe_error) else None,
        probes=probes, build=candidate["build"], control_receipt_sha256=LIVE_CONTROL_SHA,
        physical=dict(control=reference["solve"], native=candidate["measure"], early_control=reference["regional"][0],
                      early_native=candidate["regional"][0], native_counters=candidate["native"],
                      associated=candidate["associated"], arms=candidate["arms"]),
        south=dict(status=paired["south-probe"]["status"], reason=paired["south-probe"]["reason"],
                   fit_attempts=len(paired["south-probe"]["attempts"])),
        input_receipts={name: sha256(path.read_bytes()).hexdigest() for name, path in files.items()},
    )
    write(summary, result)
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(paired, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    builder = commands.add_parser("build")
    builder.add_argument("directory", type=Path)
    runner = commands.add_parser("run")
    runner.add_argument("case", choices=CASES)
    runner.add_argument("stage", choices=("probe", "full"))
    for name in ("directory", "output"):
        runner.add_argument(name, type=Path)
    runner.add_argument("--gate", type=Path)
    scores = commands.add_parser("score")
    for name in ("directory", "summary", "full"):
        scores.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    {"build": build, "run": run, "score": score}[args.pop("action")](**args)
