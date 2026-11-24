"""Compare one full original detector hook to sealed prefix and normal clocks."""

import argparse
from contextlib import ExitStack, contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.append(str(ROOT))
from reports.ALGO08.v3.original_prefix_scaling import DetectionPublished, PRIOR, PRIOR_PIN, STAGE, detection_hook, pinned

CASE = "DS30-0016"
NORMAL_AUDIT = "68aef7742c3c7da4cca09682a5c329975bd87afdab9d62c3dfb6f94e12a03253"
NORMAL_SELECTOR = "dfa99bd11bd86c131ef4ef11172bb42b950c2bbad1d476b119fdc8e873aebadb"
PREFIX = Path("/tmp/leo-v3-original-prefix-scaling-0016-result01/result.json")
PREFIX_PIN = "5e83af409a948189a861d34aa5d4aef9c947437dd36788c973d0743d7e4388dd"
WINDOWS, MEMBERS, COMPRESSED = 808, 13, 991_734_597


def admission():
    from exact_named_raw import staged_path

    result = json.loads(pinned(PRIOR / "verified-once.json", PRIOR_PIN))
    assigned = result["admission"]["inputs"][CASE]
    request = assigned["request"]
    normal = result["checked"][CASE]
    source = staged_path(Path(request["recording"]))
    paths = [staged_path(Path(path), root=source) for path in assigned["wavepaths"]]
    (detection,) = (PRIOR / CASE / "once").glob("fast-scan-automatic-work/*/detections.json")
    selector = PRIOR / CASE / "once-held-anchor-route.json"
    expected_date = normal["clock"]["clock"]["started_unix_ns"]
    audit = json.loads(pinned(PRIOR / CASE / "once/unified-short-bootstrap.json", NORMAL_AUDIT))
    selected = json.loads(pinned(selector, NORMAL_SELECTOR))
    native = json.loads(pinned(detection, request["native"]))
    options = normal["clock"]["command"][6:]
    roster = normal["original"]["members"]
    if (len(paths) != 2 + 2 * MEMBERS or len(roster) != MEMBERS
            or sum(row["encoded"] for row in roster) != COMPRESSED
            or normal["original"]["verified_source"]["windows"] != WINDOWS
            or selected["choice"]["route"] != "unfiltered" or selected["native_sha256"] != request["native"]
            or not expected_date < selector.stat().st_mtime_ns < detection.stat().st_mtime_ns
            or "--verify-original-once" not in options or "--legacy-first-map-replay" in options
            or "--legacy-first-map-plan" in options):
        raise ValueError("Expected the sealed full verify-once recording with an unfiltered selector")
    return dict(request=request, paths=[str(path) for path in paths], roster=roster, options=options,
                planned_probes=len(native["source"]["probes"]), reference_native=str(detection),
                normal=dict(process=normal["clock"]["clock"], phases=audit["phases"], receiver=audit["receiver_audit"],
                            selector_file_s=(selector.stat().st_mtime_ns - expected_date) / 1e9,
                            detection_s=(detection.stat().st_mtime_ns - expected_date) / 1e9,
                            graph_proof=audit["graph_proof"]["proven"]),
                prefix=[entry["growth"] for entry in json.loads(pinned(PREFIX, PREFIX_PIN))["times"]])


def enrolled_paths(book):
    import subprocess

    from exact_named_raw import staged_path

    root = staged_path(Path(book["request"]["recording"]))
    paths = [staged_path(Path(path), root=root) for path in book["paths"]]
    mount = subprocess.check_output(["findmnt", "-n", "-o", "OPTIONS", "-T", root], text=True)
    if not root.samefile(STAGE / root.name) or "ro" not in mount.strip().split(","):
        raise ValueError("Require a read-only private bind of the enrolled original resident tmpfs")
    return paths


def worker(root, book):
    import resource
    import empty_bootstrap as boot
    import legacy_first_map_entry as entry

    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    enrolled_paths(book)
    options = list(book["options"])
    options[options.index("--output") + 1] = str(root)
    args = entry.parser().parse_args(options)
    live = {}
    load = boot.load_runtime
    with ExitStack() as patches:
        def loaded():
            live["runtime_started"] = time_ns()
            runtime = load()
            live["runtime_ended"] = time_ns()
            import eight_ms_native_receiver as selector
            import full_short_raw
            from leo.storage.fast_scan import immutable_json
            from reports.ALGO08.v3 import legacy_first_map_input as once

            binder, observer, select = once.binding, full_short_raw.observe_acquisition, selector.prepare

            @contextmanager
            def bound(boot, expected, history, hasher, replay, pending, audit, **mode):
                live["source"] = audit
                with binder(boot, expected, history, hasher, replay, pending, audit, **mode):
                    yield

            @contextmanager
            def observe(scan, mixer, pin, audit):
                live["receiver"] = audit
                with observer(scan, mixer, pin, audit):
                    acquire = scan.acquire

                    def timed(*values):
                        live["acquire_started"] = time_ns()
                        native = acquire(*values)
                        live["acquire_ended"] = time_ns()
                        return native

                    with patch.object(scan, "acquire", timed):
                        yield

            def chosen(original, recipe, session, inventory, path):
                live["selector_started"] = time_ns()
                output = select(original, recipe, session, inventory, path)
                live["selector_ended"] = time_ns()
                live["selector_file_mtime"] = path.stat().st_mtime_ns
                live["selection"] = output[3]
                return output

            for module, name, value in (
                (once, "binding", bound),
                (full_short_raw, "observe_acquisition", observe),
                (selector, "prepare", chosen),
                (boot, "empty_reason", detection_hook(root, live, WINDOWS, boot.SCIENTIFIC_IMPORTS, immutable_json)),
            ):
                patches.enter_context(patch.object(module, name, value))
            return runtime

        patches.enter_context(patch.object(boot, "load_runtime", loaded))
        try:
            entry.run(args)
        except DetectionPublished:
            pass
    if ("detector_published_unix_ns" not in live
            or any(path.suffix == ".png" or path.name in ("terminal.json", "first-map-bundle.json")
                   for path in root.rglob("*"))):
        raise ValueError("The full hook must stop after signed detections")
    (root / "worker.json").write_text(json.dumps(live, sort_keys=True, allow_nan=False) + "\n")


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from eight_ms_south_transfer import environment_for
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident

    book = admission() | dict(machine=host(), driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    paths = enrolled_paths(book)
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    write(root / "binding.json", book)
    before = resident(paths)
    command = [str(RELEASE / "venv/bin/python"), "-IB", str(Path(__file__).resolve()), "worker", str(root)]
    clock = measure(command, environment_for(root), root / "full")
    write(root / "launch.json", dict(clock=clock, command=command, before=before, after=resident(paths),
        binding_sha256=sha256((root / "binding.json").read_bytes()).hexdigest()))
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def boundaries(clock, live, mtime):
    points = [clock["started_unix_ns"], *(live[key] for key in
              ("acquire_started", "acquire_ended", "selector_started", "selector_file_mtime", "selector_ended")),
              mtime, live["detector_published_unix_ns"]]
    if any(start > end for start, end in zip(points, points[1:])):
        raise ValueError("Overlapping or unordered detector publication clocks")
    differences = [(end - start) / 1e9 for start, end in zip(points, points[1:])]
    before, acquire, bind, selector_write, selector_tail, publication, commit = differences
    return dict(to_acquire=before, outer_acquisition=acquire, acquire_to_selector=bind,
                selector=selector_write + selector_tail, selector_file_s=sum(differences[:4]),
                selector_file_to_detection=selector_tail + publication, selector_return_to_detection=publication,
                detector_file_s=sum(differences[:-1]), detection_s=sum(differences), detector_commit_tail_s=commit,
                after_detector_s=clock["elapsed_s"] - sum(differences))


def score(root):
    from aperture_trial import write
    from visit_frame_raw_0016 import read

    book, launched = read(root / "binding.json"), read(root / "launch.json")
    pinned(root / "binding.json", launched["binding_sha256"])
    live = read(root / "full/worker.json")
    path = root / "full/detections.json"
    request, normal = book["request"], book["normal"]
    data = pinned(path, request["native"])
    if data != pinned(Path(book["reference_native"]), request["native"]):
        raise ValueError("The complete detector file differs from standard publication")
    native = json.loads(data)
    audit, receiver, clock = live["source"], live["receiver"], launched["clock"]
    roster_fields = ("manifest_sha256", "chunk_index", "index_sha256", "member_sha256", "raw_sha256",
                     "encoded", "decoded", "windows")
    actual = [[member[field] for field in roster_fields] for member in audit["members"]]
    wanted = [[member[field] for field in roster_fields] for member in book["roster"]]
    chosen = live["selection"]
    source = native["source"]
    probes = source["probes"]
    original_blocks = sum(member[phase]["input_blocks"] for member in audit["members"]
                          for phase in ("metadata", "complete_encoded_auth"))
    if (clock["exit_code"] or original_blocks or clock["cpu_s"] > 10
            or audit["finished_raw_authority"] != request["authority"] or actual != wanted
            or source["input_manifest_sha256"] != request["inventory"] or source["session_id"] != request["session"]
            or chosen["choice"]["route"] != "unfiltered" or chosen["native_sha256"] != request["native"]
            or receiver["issued"] != WINDOWS or len(probes) != book["planned_probes"]
            or not all(member["owned_window_capacity"] for member in audit["members"])):
        raise ValueError("The full hook did not authenticate and analyze the exact original recording")
    timing = boundaries(clock, live, path.stat().st_mtime_ns)
    timing["runtime_load_s"] = (live["runtime_ended"] - live["runtime_started"]) / 1e9
    timing.update(inner_wall=receiver["acquire"]["wall_ns"] / 1e9, inner_cpu=receiver["acquire"]["cpu_ns"] / 1e9)
    forecasts = [{metric: row["intercept_s"] + COMPRESSED / 1e6 / row["marginal_mb_s"]
                  for metric, row in pair.items()} for pair in book["prefix"]]
    normal["selector_file_to_detection"] = normal["detection_s"] - normal["selector_file_s"]
    normal["after_detector_s"] = normal["process"]["elapsed_s"] - normal["detection_s"]
    normal["to_acquisition_phase_estimate_s"] = normal["selector_file_s"] - sum(
        normal["phases"][key]["elapsed_s"] for key in ("authenticated_raw_acquisition", "held_anchor_route_selection"))
    normal["member_phase_cpu_s"] = dict(
        encoded_auth=sum(row["complete_encoded_auth"]["cpu_ns"] for row in book["roster"]) / 1e9,
        direct_to_owned_decode=sum(row["native_read_cpu_ns"] for row in book["roster"]) / 1e9,
        decoded_hash=sum(row["hash_cpu_ns"] for row in book["roster"]) / 1e9)
    write(root / "result.json", dict(case=CASE, bytes=COMPRESSED, members=MEMBERS, windows=WINDOWS,
        timing=timing, normal=normal, forecasts=forecasts, launch=launched, source=audit, receiver=receiver,
        selection=chosen, native_sha256=request["native"], complete_bytes_equal=True,
        probes=len(probes), exclusions=len(native["provenance"]["excluded_windows"]),
        selected_factors=sum(len(probe["candidates"]) for probe in probes),
        prefix_receipt_sha256=PREFIX_PIN, normal_receipt_sha256=PRIOR_PIN, normal_audit_sha256=NORMAL_AUDIT,
        normal_selector_sha256=NORMAL_SELECTOR, solver_children=0, waveform_backing_bytes=0,
        original_metadata_and_payload_input_blocks=original_blocks, machine=book["machine"],
        as_run_driver_sha256=book["driver_sha256"], original_request=request))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    if args.action == "launch":
        launch(args.root)
    elif args.action == "worker":
        worker(args.root / "full", json.loads((args.root / "binding.json").read_bytes()))
    else:
        score(args.root)
