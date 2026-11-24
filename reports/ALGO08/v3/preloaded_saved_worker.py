"""Compare fresh saved publication to sequential children of an import-only parent."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns, time_ns
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

WEAK = Path("/dev/shm/leo-v3-continued-refine-results-03")
WEAK_ORIGINAL = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
NORTH = Path("/dev/shm/leo-v3-continued-north-result01")
PINS = dict(weak_binding="d3a1c17592f6f4f626cb4fa994633be171d5d32ab8da7eb7126095b8b9e6aaef",
            weak_admission="bfd940c22e7cfac17040dbc95e4908ed3224370b5d19d27298d8412afc08e774",
            north_seal="4411ba5508e7cec22d0ded179af3da1d50fc2c8a3e75c235852a646e66dfb424")
CASES = ("weak", "north")
PROTOCOL = HERE / "preloaded-saved-worker-protocol.md"
PLAN = (("fresh", CASES), ("preloaded", CASES), ("preloaded", CASES[::-1]), ("fresh", CASES[::-1]))
FLAGS = ("named_survivor_finish", "exact_graph_reuse", "reuse_verified_png_reads", "one_pass_web_png",
         "direct_residual_figures", "direct_orbit_figures")


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def memory():
    values = {}
    for line in Path("/proc/self/smaps_rollup").read_text().splitlines():
        name, sep, content = line.partition(":")
        if sep and name in ("Rss", "Pss"):
            values[name.lower()+"_kib"] = int(content.split()[0])
    return values


def require_single_thread(task_dir=Path("/proc/self/task")):
    if len(tuple(task_dir.iterdir())) != 1:
        raise ValueError("Only an idle single-threaded import parent may fork")


def preload_runtime():
    from empty_bootstrap import PAYLOAD, load_runtime

    runtime = load_runtime()
    from tools import algo08_position, algo08_scan
    from matplotlib import pyplot

    # Hold code loaded by the normal job. No job, reader, projection or figure is constructed.
    if (pyplot.get_fignums()
            or any(not Path(module.__file__).resolve().is_relative_to(PAYLOAD) for module in (algo08_scan, algo08_position))):
        raise ValueError("The import parent must start with no published figure state")
    require_single_thread()
    return runtime


def enrolled(case):
    from aperture_trial import archive_identity
    from combined_frontier_run import BLOCK_SHA
    from empty_bootstrap import bind_native, checked
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from grid_feature_projection import LIBRARY_SHA
    from leo.contracts.digests import canonical_digest
    from raw_cfo_north_trial import native_file

    if case not in CASES:
        raise ValueError("Expected one original staged request")
    if case == "weak":
        job = json.loads(checked(WEAK / "binding.json", PINS["weak_binding"]))
        admission = json.loads(checked(WEAK_ORIGINAL / "admission.json", PINS["weak_admission"]))
        saved = job["saved"]
        request = {key: job[key] for key in ("recording", "saved_inventory", "session", "inventory")}
        request.update(issued=admission["issued"], cutoff_utc_ns=admission["cutoff_utc_ns"], authority=admission["raw_authority"])
        archive = dict(root=job["archive"], snapshots_sha256=admission["archive"]["sha256"])
        offer, offer_pin, packet = Path(job["offer"]), admission["offer_sha256"], native_file(WEAK / "selective")
        native_pin, detector, recipe = (saved[k] for k in ("native_sha256", "detector_sha256", "recipe"))
        libraries, route, selected = job["libraries"], saved["choice"]["route"], saved["selected"]
    else:
        seal = json.loads(checked(NORTH / "sealed.json", PINS["north_seal"]))
        binding = json.loads(checked(NORTH / "binding.json", seal["binding_sha256"]))
        request, raw = binding["request"], seal["raw"]
        archive = request["archive"]
        offer, offer_pin = Path(request["inside_offer"]), request["inside_offer_sha256"]
        packet = Path(seal["packet"])
        native_pin, detector, recipe = (raw[k] for k in ("native_sha256", "detector_recipe_sha256", "receiver_recipe"))
        libraries = {flag[2:].replace("-", "_"): row["path"] for flag, row in binding["libraries"].items()
                     if flag != "--short-binary"}
        route, selected = (raw["held_anchor_route"][k] for k in ("choice", "selected"))
        route = route["route"]
    library_pins = dict(geographic_library=GEOGRAPHIC_SHA, regional_track_library=TRACK_SCORES_SHA,
                        frontier_block_library=BLOCK_SHA, grid_feature_projection_library=LIBRARY_SHA)
    if set(libraries) != set(library_pins):
        raise ValueError("Publication needs the same verified native implementation for both inputs")
    libraries = {name: Path(path) for name, path in libraries.items()}
    for name, path in libraries.items():
        checked(path, library_pins[name])
    native = json.loads(checked(packet, native_pin[7:]))
    bind_native(native, request["session"], request["inventory"], detector[7:], expected=native_pin)
    if (canonical_digest(recipe) != detector or native["provenance"]["window_count"] != request["issued"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]
            or native["source"]["raw_recording_authority_digest"] != request["authority"]
            or sum(len(row["candidates"]) for row in native["source"]["probes"]) != selected
            or archive_identity(Path(archive["root"])) != archive):
        raise ValueError("The saved detector, opportunities, original cutoff or causal archive changed")
    offered = json.loads(checked(offer, offer_pin))
    identity = dict(case=case, native_sha256=native_pin, detector=detector, original_offer=offered,
                    offer_sha256=offer_pin, archive=archive, route=route, selected=selected,
                    **{k: request[k] for k in ("issued", "cutoff_utc_ns", "session", "inventory", "authority")})
    return request, Path(archive["root"]), offer, libraries, packet, native, identity


def publish(case, output, runtime=None):
    from empty_bootstrap import RELEASE, clock, load_runtime, now

    started = now()
    _, spec, _, publication, checks = runtime if runtime is not None else load_runtime()
    from aperture_trial import write as write_receipt
    from cumulative_grid_projection import saved_inventory_port
    from short_graph_guard import prove
    from unified_short_bootstrap import Handoff, publish_active

    request, archive, offer, libraries, packet, native, identity = enrolled(case)
    args = SimpleNamespace(recording=Path(request["recording"]), archive=archive, region=offer, output=output,
                           **libraries, **dict.fromkeys(FLAGS, True))
    handoff = Handoff(request["session"], request["inventory"], identity["detector"][7:], native)
    layout, graph, png = {}, {}, {}
    with saved_inventory_port(request) as ready:
        proof = prove(native, RELEASE / "assets", use_time_support=True, use_curvature_extent=True)
        if proof["proven"]:
            raise ValueError("Expected a genuine active saved graph on the original signed factors")
        receipt, detail = publish_active(args, publication, spec, handoff, layout, graph_audit=graph,
                                        png_read_audit=png,
                                        no_active_curvature_sha256=proof.get("curvature_extent", {}).get("native_sha256"))
    (published,) = output.glob("fast-scan-automatic-work/*/detections.json")
    if not ready or handoff.calls != 1 or published.read_bytes() != packet.read_bytes():
        raise ValueError("Expected one original packet and zero waveform calls")
    write_receipt(output / "request-receipt.json", dict(request=identity, receipt=receipt, graph=graph, layout=layout,
                  png=png, projection=detail["grid_feature_projection"], solve=detail["solve"], handoffs=handoff.calls,
                  source_checks=checks, preloaded=runtime is not None, waveform_calls=0, internal_request=clock(started)))


def sequences(mode, order, root):
    init_cpu, init_wall = process_time_ns(), perf_counter_ns()
    runtime = preload_runtime() if mode == "preloaded" else None
    initialized = dict(cpu_ns=process_time_ns()-init_cpu, wall_ns=perf_counter_ns()-init_wall,
                       **memory(), pid=os.getpid())
    jobs = []
    for case in order:
        require_single_thread()
        output = root / case
        before = perf_counter_ns(), time_ns()
        sys.stdout.flush()
        sys.stderr.flush()
        child = os.fork()
        if child == 0:
            if runtime is None:
                args = [sys.executable, "-IB", __file__, "child", str(output), case]
                os.execv(sys.executable, args)
            publish(case, output, runtime)
            return
        pid, status, usage = os.wait4(child, 0)
        jobs.append(dict(case=case, pid=pid, started_unix_ns=before[1], elapsed_ns=perf_counter_ns()-before[0],
                         cpu_s=usage.ru_utime+usage.ru_stime, max_rss_kib=usage.ru_maxrss,
                         major_faults=usage.ru_majflt, input_blocks=usage.ru_inblock,
                         status=os.waitstatus_to_exitcode(status), parent_after=memory()))
        if status:
            write(root / "sequence.json", dict(initialized=initialized, jobs=jobs))
            raise RuntimeError(f"Publication child exited before a clean seal for {case}")
    write(root / "sequence.json", dict(initialized=initialized, jobs=jobs))


def run(root):
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from north_held_anchor_pair import tmpfs
    from short_raw_diagnostic import measure

    settings = host()
    tmpfs(root.parent)
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit frozen worker sources before launch")
    root.mkdir()
    names = [Path(__file__), PROTOCOL, HERE / "unified_short_bootstrap.py", HERE / "joint_publication.py",
             HERE / "empty_bootstrap.py", HERE / "cumulative_grid_projection.py", HERE / "preloaded_saved_score.py"]
    write(root / "binding.json", dict(plan=PLAN, machine=settings, controls=PINS,
          commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
          sources={p.name: sha256(p.read_bytes()).hexdigest() for p in names}))
    for index, (mode, order) in enumerate(PLAN, 1):
        output = root / f"{index}-{mode}"
        output.mkdir()
        env = environment(output)
        for name in ("tmp", "fonts"):
            (output / name).mkdir()
        env.update(TMPDIR=str(output / "tmp"), XDG_CACHE_HOME=str(output / "tmp"))
        command = ["/usr/bin/timeout", "--kill-after=2s", "45s", RELEASE/"venv/bin/python", "-IB", Path(__file__),
                   "sequence", output, mode, *order]
        result = measure(command, env, output)
        write(root / (output.name+"-clock.json"), dict(clock=result, command=list(map(str, command))))
        if result["exit_code"]:
            raise RuntimeError(result["stderr_tail"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "sequence", "child"))
    parser.add_argument("root", type=Path)
    parser.add_argument("parameters", nargs="*")
    args = parser.parse_args()
    if args.action == "run":
        run(args.root)
    elif args.action == "child":
        (case,) = args.parameters
        publish(case, args.root)
    else:
        mode, *order = args.parameters
        if mode not in ("fresh", "preloaded") or set(order) != set(CASES) or len(order) != len(CASES):
            parser.error("Supply a fresh or preloaded independent two-case sequence")
        sequences(mode, order, args.root)
