"""Qualify one live 8 ms native receiver before a single original North replay."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from continued_cfo_first_0016 import read, write
from empty_bootstrap import RELEASE, checked


EIGHT = Path("/var/tmp/leo-v3-eight-ms-build-padded/8ms/short-primary.so")
PROTOCOL = HERE/"eight-ms-native-live-protocol.md"
ORDER = ("history8", "guarded")
PHYSICAL = Path("/dev/shm/leo-eight-ms-DS30-0016-warm/8ms")
PHYSICAL_NATIVE = "f16ca1c684283a720596edfd727620a90f48712936f135c420d0c993ec669f6e"
PRIOR_GUARDED = Path("/dev/shm/leo-v3-continued-first-0016-result02/1-guarded")
PRIOR_GUARDED_NATIVE = "ce5af5611b56a42ba960e6d1296040b2bbf4ad8e60aea96d182e9ff6f94e3111"
PRIOR_GUARDED_RECEIPT = "b95c3a5fc21ab89dae16619a66e41c6155ff123bb1300ea833525788b713fdc2"
SOURCES = (Path(__file__), PROTOCOL, HERE/"eight_ms_native_score.py", HERE/"eight_ms_native_receiver.py",
           HERE/"eight_ms_held_fit.py", HERE/"continued_cfo_first_0016.py", HERE/"combined_raw_research.py",
           HERE/"joint_held_north_raw.py", HERE/"unified_short_bootstrap.py", HERE/"raw_cfo_north_trial.py",
           HERE/"continued_cfo_north_mirror.py")


def prefix_worker(mode, output):
    import continued_cfo_first_0016 as scope
    import eight_ms_native_receiver as receiver
    from combined_raw_research import native_eight

    if mode == "guarded":
        scope.worker(mode, output)
        return

    def launch(argv, seal):
        original = receiver.prepare

        def selected(native, recipe, session, inventory, receipt_file):
            actual, selected_recipe, pin, witness = original(native, recipe, session, inventory, receipt_file)
            probes = native["source"]["probes"]
            seal(actual, session, inventory, pin, recipe=selected_recipe, original=probes, acquired=probes,
                 route=witness, paid=[])

        argv[argv.index("--short-binary")+1] = str(EIGHT)
        with patch.object(receiver, "prepare", selected):
            native_eight(argv)

    scope.worker(mode, output, launch_alternative=launch)


def frozen():
    checkout = HERE.parents[2]
    git = ["git", "-c", f"safe.directory={checkout}", "-C", str(checkout)]
    if subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("Commit the frozen protocol and sources before entering the receiver")
    return dict(commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
                sources={path.name: sha256(path.read_bytes()).hexdigest() for path in SOURCES})


def prefix_run(root):
    import continued_cfo_first_0016 as scope
    from anchored_cfo_raw import verified_pack
    from dense_geographic_trial import host
    from full_short_physical import environment
    from full_short_run import EIGHT_MS_SHA
    from short_raw_diagnostic import measure

    if root.parent.resolve() != Path("/dev/shm"):
        raise ValueError("Use a fresh tmpfs output directory")
    binding = frozen()
    settings = host()
    chunk, files = scope.mapped_files()
    checked(EIGHT, EIGHT_MS_SHA)
    checked(scope.PACK/"pack.json", scope.PACK_SHA)
    verified_pack(scope.PACK)
    root.mkdir()
    (root/"tmp").mkdir()
    env = environment(root) | {"TMPDIR": str(root/"tmp")}
    write(root/"binding.json", dict(binding, machine=settings, chunk=chunk, order=ORDER, native_binary_sha256=EIGHT_MS_SHA,
                                   manifest_sha256=scope.MANIFEST, guard_pack_sha256=scope.PACK_SHA))
    for mode in ORDER:
        output = root/mode
        args = ["/usr/bin/timeout", "--kill-after=1s", "20s", RELEASE/"venv/bin/python", "-IB", Path(__file__),
                "prefix-worker", output, mode]
        before = scope.resident(files)
        clock = measure(args, env, output)
        write(root/(mode+"-clock.json"), dict(clock=clock, before=before, after=scope.resident(files),
                                             command=list(map(str, args))))
        if clock["exit_code"]:
            raise RuntimeError(clock["stderr_tail"])


def north_run(root, prefix):
    from combined_raw_trial import PRODUCER, checked_producer, flags
    from eight_ms_native_score import prefix_score
    from joint_held_north_raw import launch
    from north_orbit_index_trial import admitted_inputs

    if not prefix_score(prefix)["admit_north"]:
        raise ValueError("The paid physical prefix did not pass the frozen North gate")
    controls, census = admitted_inputs()
    checked_producer(controls["binding"]["request"]["cutoff_utc_ns"], census["72"]["body_digests"])
    pressure = Path("/proc/pressure/io").read_text()
    launch(root, continued=True, entrypoint=HERE/"combined_raw_research.py", trial_protocol=PROTOCOL,
           extra_sources=SOURCES, experiment_flags=flags(PRODUCER), native_eight_binary=EIGHT)
    write(root/"admission.json", dict(prefix_result_sha256=sha256((prefix/"result.json").read_bytes()).hexdigest(),
                                     io_pressure_before=pressure, io_pressure_after=Path("/proc/pressure/io").read_text()))


def omitted_run(root):
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    binding = frozen()
    seal = root/"science-seal.json"
    score = read(root/"score.json")
    if score["science_seal_sha256"] != sha256(seal.read_bytes()).hexdigest() or not score["admit_omitted"]:
        raise ValueError("Only the independently sealed containing science may admit the omitted solve")
    binding.update(native_sha256=read(seal)["raw"]["native_sha256"], containing_sha256=score["science_seal_sha256"])
    command = ["/usr/bin/timeout", "--kill-after=1s", "35s", RELEASE/"venv/bin/python", "-IB", Path(__file__),
               "omitted-worker", root]
    write(root/"omitted-binding.json", dict(binding, command=list(map(str, command))))
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    clock = measure(command, env, root/"omitted")
    write(root/"omitted-clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def omitted_worker(root):
    from time import perf_counter, process_time
    from combined_raw_research import combined_runtime, rank_status
    from combined_raw_trial import PRODUCER
    from continued_cfo_north_mirror import MIRROR, MIRROR_SHA
    from empty_bootstrap import bind_native, load_runtime
    from raw_cfo_north_trial import ORDER as OFFERS, native_file, publish_saved

    started = process_time(), perf_counter()
    binding = read(root/"omitted-binding.json")
    source = json.loads(checked(root/"science-seal.json", binding["containing_sha256"]))
    request = source["request"]
    if json.loads(checked(MIRROR, MIRROR_SHA)) != request["mirror_offer"]:
        raise ValueError("Wrong original North omitted offer")
    pins = read(root/"binding.json")["libraries"]
    libraries = {flag[2:].replace("-", "_"): row["path"] for flag, row in pins.items()}
    for row in pins.values():
        checked(Path(row["path"]), row["sha256"])
    request |= dict(libraries=libraries, offer_sha256={OFFERS[1]: MIRROR_SHA})
    packet, raw = native_file(root/"containing"), source["raw"]
    native = json.loads(checked(packet, binding["native_sha256"][7:]))
    orbit, rank = {}, {}
    with combined_runtime(orbit, rank, PRODUCER, use_blocks=True):
        runtime = load_runtime()
        bind_native(native, request["session"], request["inventory"], raw["detector_recipe_sha256"][7:])
        publish_saved(request, root/"omitted", MIRROR, packet, native, raw, started=started, runtime=runtime,
                      receipt_name="eight-ms-omitted.json")
    write(root/"omitted-execution.json", dict(orbit=orbit, rank=rank, rank_status=rank_status(True, rank)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    args = cli.add_subparsers(dest="action", required=True)
    for name in ("prefix-run", "prefix-worker", "north-run", "omitted-run", "omitted-worker"):
        command = args.add_parser(name)
        command.add_argument("root", type=Path)
        if name == "prefix-worker":
            command.add_argument("mode", choices=ORDER)
        if name == "north-run":
            command.add_argument("prefix", type=Path)
    options = cli.parse_args()
    if options.action == "prefix-run":
        prefix_run(options.root)
    elif options.action == "prefix-worker":
        prefix_worker(options.mode, options.root)
    elif options.action == "north-run":
        north_run(options.root, options.prefix)
    else:
        (omitted_run if options.action == "omitted-run" else omitted_worker)(options.root)
