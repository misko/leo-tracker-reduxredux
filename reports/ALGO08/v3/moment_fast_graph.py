"""Compare the published fast Graph on the initial ordinary and masked inputs."""

import argparse
from contextlib import ExitStack
from dataclasses import replace
from hashlib import sha256
from importlib import import_module
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import subprocess
import sys
from time import monotonic, perf_counter_ns, process_time_ns, sleep, time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
LOCK = Path("/tmp/leo-algo08v2-2x-bench/gauss.lock")
CELLS = {
    "DS30-0280": (Path("/tmp/leo-v3-0280-moment-extended01/field"),
                  "e926376f4a34e6cb1881d89d9a76a024313310844ac514fd5b9ae005905f61df",
                  "82a6e79d151eed55dae7252511560422f233e2bfb22f7aad806143fd1a284b06",
                  ("stock", "fast")),
    "DS30-0212": (Path("/dev/shm/leo-0212-moment-publication01"),
                  "1c8228e382e1013dbfbd10eaa04685224f8e18590c164fb42a0244335219aa8f",
                  "657eb29062c6966597f0b3e34e019fbacd58eaf797c98b194e4907175aed7e6e",
                  ("fast", "stock")),
}
PINS = {
    "moment-fast-graph-protocol.md": "6d2cf1da34df0615a03a5d4bab69e8047f0bd023aeae51b1a96b47a666521a22",
    "exact_graph_execution.py": "cee1c8e095f139d4e1b839dc84a3c25b96794a96031df05a16f7f876a67391fe",
    "polynomial_fit_cache.py": "6c2f936f9904c707a6dab7846fb242602baf72a369c1c207624825625906c75b",
    "vector_graph_edges.py": "b4a4c67f9100b668129bce2c4baa23440edde92374386260475be01f898115fd",
    "moment_preserving_cfo.py": "f9e0836f40c03a7fa5f20a19a34ac1bcf67f632b830271ef43f0809f3ef8b982",
    "held_cfo_features.py": "65a9934437d2d495b269f7377dd4d82ebe4d4e1e6f6b8e3e89717f89a25e8843",
    "masked_cfo_saved.py": "2ecadcd736ea59184333280626e8c48de7afa2aed4ad95974bd1c5a564895c35",
}
FAST_PINS = {key: PINS[key] for key in ("polynomial_fit_cache.py", "vector_graph_edges.py")}
RELEASE_PINS = {
    "assets/tracks.json": "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a",
    "src/leo/analysis/localization_v3/tracks.py": "db44a947666c2dd7946534f69bf6af72ced63c8af553bb1b089c0fba3d5b7b6f",
    "src/leo/analysis/graph_tracklets.py": "74575f44c4e9716707faaac56e3e7c35bb423ba0f75332656d7c6576cd8f2c27",
    "src/leo/analysis/polynomial_tracklets.py": "933b83ce5e414a8441c62d17f8e5eb75e07b79cada283bf681193f7316346922",
    "src/leo/analysis/tracklet_fitting.py": "8e3917e1bb94bf59e37d97a7a3782254612e459d36075f67acfdfe15b3a19414",
    "src/leo/analysis/glrt_frequency_input.py": "e7ad53bf41c596042c654184c8f212f4ec187c9281d4944725344d7f5e3ee58b",
}
THREADS = ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
WAIT_S = 60
CAP_S = 12


def checked(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Sealed bytes changed for {path}")
    return body


def document(path, pin):
    return json.loads(checked(path, pin))


def read_clock(record, cpu="cpu_ns", wall="wall_ns"):
    if any(type(record[key]) is not int or record[key] <= 0 for key in (cpu, wall)):
        raise ValueError("CPU and wall clocks must be positive integer nanoseconds")
    return dict(cpu_ns=record[cpu], wall_ns=record[wall])


def historical(observation, publication):
    projection = observation["moment_preserving"]
    attempt, = observation["attempts"]
    raw_port = publication["ports"]["graph"]
    port = raw_port["graph"]
    if (observation["feature_calls"] != 1 or raw_port["enabled"] is not True or raw_port["sources"] != FAST_PINS
            or publication["source_sha256"]["reports/ALGO08/v3/exact_graph_execution.py"] != PINS["exact_graph_execution.py"]
            or any(port[k] != n for k, n in (("calls", 1), ("assigned", attempt["graph_points"]),
                                             ("tracks", attempt["tracks"])))):
        raise ValueError("Require evidence that the edited Graph used the pinned fast port once")
    return dict(derive=read_clock(observation["derive"]),
                **{name: read_clock(projection["clocks"][name]) for name in (
                    "held_odd_proposals", "ordinary_graph", "projection")},
                edited_outer=read_clock(attempt["ordinary_graph_with_extraction_and_overlay"]),
                edited_overlay=read_clock(attempt["overlay"]),
                edited_inner=read_clock(port, "graph_cpu_ns", "graph_elapsed_ns"),
                edited_edges=read_clock(port, "edge_cpu_ns", "edge_elapsed_ns"))


def snapshot(case, *, native=False):
    root, closure_pin, native_pin, order = CELLS[case]
    closure = document(root / "verification-pins.json", closure_pin)["corrected"]
    child = root / "corrected"
    plan = document(child / "plan.json", closure["plan"])
    observation = document(child / "masked-cfo-observation-witness.json", closure["observation"])
    receipt = document(child / "receipt.json", closure["receipt"])
    publication = document(child / "substituted/exact-named-raw-witness.json", receipt["witness"])
    clock = document(child / "clock.json", closure["clock"])
    signed_pin = "sha256:" + native_pin
    if (plan["case"] != case or not plan["enabled"] or clock["exit_code"] or receipt["input"] != signed_pin
            or observation["original_native_sha256"] != signed_pin or plan["original_native_sha256"] != signed_pin
            or observation["stage_plan_sha256"] != closure["plan"] or observation["waveform_reads"]
            or receipt["waveform_reads"] or receipt["receiver_rerun"]):
        raise ValueError("The sealed corrected worker does not bind one original native packet")
    data = checked(child / "derived-native.json", native_pin)
    clocks = historical(observation, publication)
    bindings = dict(closure_sha256=closure_pin, observation_sha256=closure["observation"],
                    publication_sha256=receipt["witness"], original_native=signed_pin, mode_order=list(order))
    return (json.loads(data) if native else None), observation, dict(bindings=bindings, historical_clocks=clocks)


def no_science_files(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0])).resolve()
        if (path.suffix in (".tle", ".sigmf-data", ".iq", ".png") or path.is_relative_to("/mnt/qnap01")
                or {"tle", "space-track", "fast-scan-recordings"} & set(path.parts)
                or path.name in ("evaluation-reference.json", "reference-audit.json", "offer.json", "score.json")):
            raise RuntimeError("The Graph-only trial must use signed measurement metadata")


def preparation():
    for directory, pins in ((HERE, PINS), (RELEASE, RELEASE_PINS)):
        for name, pin in pins.items():
            checked(directory / name, pin)
    return dict(cases={case: snapshot(case)[2] for case in CELLS}, source_pins=PINS,
                released_pins=RELEASE_PINS, timing_runs=0, graph_preparations=0,
                receiver_runs=0, solver_runs=0, waveform_reads=0, archive_reads=0, survey_reads=0,
                source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())


def freeze(value):
    """Bind complete ordered Graph results with binary64 floats and array bits."""
    import numpy as np

    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise ValueError("Graph contains a non-numerical array")
        return dict(dtype=value.dtype.str, shape=list(value.shape), bits=value.tobytes().hex())
    if isinstance(value, np.generic):
        return freeze(value.item())
    if isinstance(value, float):
        return value.hex()
    if isinstance(value, dict):
        return {key: freeze(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [freeze(item) for item in value]
    return value


def now():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    end = now()
    return {key: z - a for key, z, a in zip(("cpu_ns", "wall_ns"), end, start, strict=True)}


def execute(native, config, observed, *, fast):
    import exact_graph_execution as graph_port
    import moment_preserving_cfo as projection
    from leo.analysis.localization_v3 import tracks
    from reports.ALGO08.v3 import held_cfo_features as features

    extract = tracks.winning_observations
    extracted, scopes, internals, prepared = {}, {}, {}, {}

    def take(mode):
        def read(document):
            if mode in extracted:
                raise ValueError("Graph winner extraction ran more than once")
            start = now()
            value = extract(document)
            extracted[mode] = elapsed(start)
            return value
        return read

    def capture(document, cfg):
        if "masked" in prepared:
            raise ValueError("The original mask called Graph more than once")
        result = tracks.prepare_tracks(document, cfg)
        prepared["masked"] = result
        return result

    with (patch.object(features, "prepare_tracks", capture), patch.object(tracks, "winning_observations", take("masked")),
          graph_port.graph_execution(enabled=fast, audit=internals.setdefault("masked", {}))):
        start = now()
        proposed = features.derive(native, config)
        scopes["masked_proposals"] = elapsed(start)
    with (patch.object(tracks, "winning_observations", take("ordinary")),
          graph_port.graph_execution(enabled=fast, audit=internals.setdefault("ordinary", {}))):
        start = now()
        ordinary = tracks.prepare_tracks(native, config)
        scopes["ordinary_preparation"] = elapsed(start)
    prepared["ordinary"] = ordinary
    start = now()
    revised, proof = projection.project_tracks(ordinary, proposed.edits)
    scopes["projection"] = elapsed(start)

    residual = projection.residual
    digest = residual.digest
    projected_edits = {oid: dict(edit, updated_hz=revised[oid]) for oid, edit in proposed.edits.items()}
    adjusted = features.apply_to_winners(native, ordinary["observations"], replace(proposed, edits=projected_edits))
    if set(extracted) != {"ordinary", "masked"} or any(item["graph"]["calls"] != 1 for item in internals.values()):
        raise ValueError("Expected one extraction and one Graph call in each preparation")
    attempt, = observed["attempts"]
    sealed = observed["moment_preserving"]
    invariants = dict(projection=proof, provisional_edits_sha256=digest(proposed.edits),
                      projected_edits_sha256=digest(projected_edits), original_rows_sha256=digest(ordinary["observations"]),
                      consumed_rows_sha256=digest(adjusted), masked_forecasts_sha256=digest(proposed.forecasts),
                      graph_sha256={mode: digest(freeze(packet)) for mode, packet in prepared.items()})
    sealed_exact = (digest(sealed["projection"]) == digest(proof) and observed["edit_sha256"] == invariants["projected_edits_sha256"]
                    and {"assigned": ordinary["graph_points"], "tracks": len(ordinary["tracks"])} == sealed["ordinary_graph"]
                    and proposed.masked_graph == observed["masked_graph"] and proposed.gates == observed["eligible_gates"]
                    and proposed.eligibility == observed["nomination_gates"]
                    and all(attempt[key] == invariants[key] for key in ("original_rows_sha256", "consumed_rows_sha256")))
    for audit in internals.values():
        read_clock(audit["graph"], "graph_cpu_ns", "graph_elapsed_ns")
    return dict(clocks=scopes, winner_extraction=extracted, graph_ports=internals, invariants=invariants,
                sealed_projection_and_rows_exact=sealed_exact), proposed.edits, revised


def compare(stock, fast):
    left, a, x = stock
    right, b, y = fast
    return dict(full_graph_equal={key: left["invariants"]["graph_sha256"][key] == right["invariants"]["graph_sha256"][key]
                                 for key in ("masked", "ordinary")},
                proposal_id_diff=len(a.keys() ^ b.keys()), proposed_record_diff=sum(a[k] != b[k] for k in a.keys() & b.keys()),
                projected_id_diff=len(x.keys() ^ y.keys()), applied_value_diff=sum(x[k] != y[k] for k in x.keys() & y.keys()),
                identical_invariants=left["invariants"] == right["invariants"],
                stock_sealed_exact=left["sealed_projection_and_rows_exact"],
                fast_sealed_exact=right["sealed_projection_and_rows_exact"])


def child(fd, expected):
    import fcntl

    if os.sched_getaffinity(0) != {2} or os.getpriority(os.PRIO_PROCESS, 0) != 15:
        raise ValueError("The timed child requires shared Gauss CPU2 at nice 15")
    if any(os.environ.get(key) != "1" for key in THREADS) or not os.path.samestat(os.fstat(fd), LOCK.stat()):
        raise ValueError("Use one numerical thread and the inherited shared lease")
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    sys.addaudithook(no_science_files)
    prepared = preparation()
    if prepared != document(expected[0], expected[1]):
        raise ValueError("The frozen preflight changed before timing")

    import exact_graph_execution as graph_port
    from leo.analysis.polynomial_tracklets import TrackConfig

    for name in ("leo.analysis.localization_v3.tracks", "leo.analysis.graph_tracklets",
                 "leo.analysis.polynomial_tracklets", "leo.analysis.tracklet_fitting"):
        module = import_module(name)
        if Path(module.__file__).resolve() != RELEASE / "src" / (name.replace(".", "/") + ".py"):
            raise ValueError("The Graph comparison must use the released numerical modules")
    config = TrackConfig(**document(RELEASE / "assets/tracks.json", RELEASE_PINS["assets/tracks.json"])["config"])
    start = now()
    with graph_port.graph_execution(enabled=True):
        pass
    setup = elapsed(start)
    results = {}
    for case, (_, _, _, order) in CELLS.items():
        source, observation, metadata = snapshot(case, native=True)
        runs = {mode: execute(source, config, observation, fast=(mode == "fast")) for mode in order}
        parity = compare(runs["stock"], runs["fast"])
        if not parity["stock_sealed_exact"]:
            raise ValueError("The unchanged reference differs from the archived edit ledger")
        results[case] = dict(**metadata, modes={mode: value[0] for mode, value in runs.items()}, parity=parity)
    return dict(cases=results, fast_port_initialization=setup, preflight_sha256=expected[1], timing_runs=1,
                graph_preparations=8, receiver_runs=0, solver_runs=0, waveform_reads=0, archive_reads=0, survey_reads=0)


def watch(prepared, pin, pid, output):
    from field_crossover_admission_watch import recent_deferral
    from masked_cfo_0218_capsule import DRIVER, DRIVER_PIN, lease, live_window

    if os.sched_getaffinity(0) != {3} or os.getpriority(os.PRIO_PROCESS, 0) != 15:
        raise ValueError("Run the watch controller on low-priority CPU3")
    checked(DRIVER, DRIVER_PIN)
    document(prepared, pin)
    started, deadline = time_ns(), monotonic() + WAIT_S
    last_event = None
    while monotonic() < deadline:
        event = recent_deferral(CAMPAIGN, started, time_ns())
        if event and event != last_event:
            last_event = event
            with ExitStack() as scope:
                try:
                    scope.enter_context(patch("masked_cfo_0218_capsule.TIMEOUT", CAP_S))
                    fd = scope.enter_context(lease())
                    live_window(event, pid)
                except (OSError, ValueError):
                    sleep(.20)
                    continue
                started_wall = perf_counter_ns()
                before = getrusage(RUSAGE_CHILDREN)
                argv = ["/usr/bin/taskset", "-c", "2", "/usr/bin/ionice", "-c2", "-n7", sys.executable,
                        "-BPs", str(Path(__file__)), "child", "--preflight", str(prepared), "--pin", pin,
                        "--lease-fd", str(fd)]
                try:
                    run = subprocess.run(argv, pass_fds=(fd,), capture_output=True, timeout=CAP_S)
                except subprocess.TimeoutExpired:
                    return dict(state="child_timeout", event=event, timed_children=1,
                                child_clock=child_usage(before, started_wall))
                clock = child_usage(before, started_wall)
            if not run.returncode:
                with output.open("xb") as target:
                    target.write(run.stdout)
            return dict(state="sealed" if not run.returncode else "child_error", event=event,
                        timed_children=1, exit_code=run.returncode, child_clock=clock,
                        stderr=run.stderr.decode(errors="replace"))
        sleep(.20)
    return dict(state="no_fresh_slot", timed_children=0, last_deferral=last_event)


def child_usage(before, started_wall):
    after = getrusage(RUSAGE_CHILDREN)
    cpu_s = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
    return dict(cpu_ns=round(cpu_s * 1e9), wall_ns=perf_counter_ns() - started_wall,
                input_blocks=after.ru_inblock - before.ru_inblock)


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
        sys.addaudithook(no_science_files)
        result = preparation()
    elif args.mode == "watch":
        result = watch(args.preflight, args.pin, args.driver, args.output)
    else:
        result = child(args.lease_fd, (args.preflight, args.pin))
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
