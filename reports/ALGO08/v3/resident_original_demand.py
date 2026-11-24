"""Test ordinary demand snapshots against normal lookahead on resident originals."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
from resource import RUSAGE_SELF
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.append(str(ROOT))
from reports.ALGO08.v3 import original_full_detector_boundary as full
from reports.ALGO08.v3.owned_window_recycle_trial import Trace, clock, delta, total

ORDERS = ("normal", "demand")


def demand_eligible(paths, checked_paths):
    """A disappearing, mutable or partly resident enrolled mount uses ordinary lookahead."""
    from visit_frame_raw_0016 import resident

    try:
        eligible = checked_paths()
        return tuple(paths) == tuple(eligible) and resident(eligible)["members"] == len(paths)
    except (ValueError, OSError, subprocess.CalledProcessError):
        return False


def worker(root, book, variant):
    import empty_bootstrap as boot

    before = clock(RUSAGE_SELF)
    paths = [Path(p) for p in book["paths"]]
    eligible = demand_eligible(paths, lambda: full.enrolled_paths(book))
    trace = Trace(None, demand=variant == "demand" and eligible)
    load = boot.load_runtime
    with ExitStack() as patches:
        def loaded():
            result = load()
            patches.enter_context(trace.binding())
            return result

        patches.enter_context(patch.object(boot, "load_runtime", loaded))
        full.worker(root, book)
    (root / "memory.json").write_text(json.dumps(dict(requested=variant, enabled=trace.demand,
        eligible=eligible, process=delta(before, clock(RUSAGE_SELF)), members=trace.members,
        total_addresses=len(trace.addresses), prefetch=trace.prefetch,
        prefetch_stats=trace.prefetch_stats), sort_keys=True) + "\n")


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import RELEASE
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    book = full.admission() | dict(machine=host(), driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    paths = full.enrolled_paths(book)
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    write(root / "binding.json", book)
    trials = {}
    for variant in ORDERS:
        output = root / variant
        before = resident(paths)
        command = [str(RELEASE / "venv/bin/python"), "-IB", str(Path(__file__).resolve()), "worker",
                   str(output), "--binding", str(root / "binding.json"), "--variant", variant]
        timed = measure(command, environment_for(root), output)
        trials[variant] = dict(clock=timed, command=command, before=before, after=resident(paths))
        write(root / f"clock-{variant}.json", trials[variant])
        if timed["exit_code"]:
            raise RuntimeError(timed["stderr_tail"])
    write(root / "launch.json", dict(order=ORDERS, trials=trials,
                                    binding_sha256=sha256((root / "binding.json").read_bytes()).hexdigest()))


def score(root):
    from aperture_trial import write
    from visit_frame_raw_0016 import read

    book, manifest = read(root / "binding.json"), read(root / "launch.json")
    full.pinned(root / "binding.json", manifest["binding_sha256"])
    request, roster = book["request"], book["roster"]
    expected = full.pinned(Path(book["reference_native"]), request["native"])
    evidence = {}
    for variant in ORDERS:
        folder = root / variant
        native = full.pinned(folder / "detections.json", request["native"])
        live, memory = read(folder / "worker.json"), read(folder / "memory.json")
        process = manifest["trials"][variant]["clock"]
        phases = full.boundaries(process, live, (folder / "detections.json").stat().st_mtime_ns)
        audit = live["source"]
        fields = ("manifest_sha256", "chunk_index", "encoded", "decoded", "windows",
                  "member_sha256", "index_sha256", "raw_sha256")
        identities = lambda rows: [tuple(r[key] for key in fields) for r in rows]
        encoded_main = total([row["encoded_auth_main"] for row in memory["members"]])
        worker_reads = total(memory["prefetch"])
        expected_prefetch = 0 if variant == "demand" else full.MEMBERS - 2
        stats = memory["prefetch_stats"]
        if (native != expected or identities(audit["members"]) != identities(roster)
                or audit["finished_raw_authority"] != request["authority"] or process["exit_code"]
                or len(memory["members"]) != full.MEMBERS or not memory["eligible"]
                or memory["enabled"] != (variant == "demand") or len(memory["prefetch"]) != expected_prefetch
                or stats["submitted"] != expected_prefetch or stats["hits"] != expected_prefetch or stats["fallback"]
                or any(not row["supplied"] for row in memory["prefetch"])
                or encoded_main["input_blocks"] or worker_reads["input_blocks"]
                or live["selection"]["choice"]["route"] != "unfiltered" or live["receiver"]["issued"] != full.WINDOWS):
            raise ValueError("The matched resident original receiver pair changed support or scheduling")
        evidence[variant] = dict(clocks=phases, memory=memory, relative_source=audit, receiver=live["receiver"],
            encoded_main=encoded_main, worker_reads=worker_reads,
            demand_reads=full.MEMBERS - stats["hits"], demand_bytes=full.COMPRESSED - stats["hit_bytes"],
            native_decode=total([r for m in memory["members"] for r in m["decode"]]),
            callbacks=total([r for m in memory["members"] for r in m["callback"]]))
    write(root / "result.json", dict(case="DS30-0016", order=ORDERS, bytes=full.COMPRESSED, windows=full.WINDOWS,
        members=full.MEMBERS, detector_sha256=request["native"], request=request, evidence=evidence,
        launch=manifest, machine=book["machine"], waveform_backing_bytes=0, solver_children=0))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("--binding", type=Path)
    cli.add_argument("--variant", choices=ORDERS)
    args = cli.parse_args()
    if args.action == "launch":
        launch(args.root)
    elif args.action == "worker":
        worker(args.root, json.loads(args.binding.read_bytes()), args.variant)
    else:
        score(args.root)
