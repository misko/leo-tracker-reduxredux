"""Price independent raw entry import prefixes without reading a scientific request."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
BASELINE = Path("/opt/leo-algo08/algo08v3/run")
PAYLOAD = BASELINE.parent/"payload"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PUBLICATION = PAYLOAD/"tools/pipeline_eval/qualification/experimental_publication.py"
PINS = {
    BASELINE: "fae032526227f55ca2419a0b29c69afc7fc97fa04508f33d0403802934f13448",
    PUBLICATION: "2a6fb84d59d1fba485d270b38a2a0553b59c1977373520dcce0e3488c6859690",
    HERE/"exact_named_raw.py": "b4f6c575970de04819c414f69a08260003f193ed6aa75671e0507c0ad28a0ad5",
    HERE/"unified_short_bootstrap.py": "07aa0f80f0114af2b22134da8fdff9f9c74e8384631dc834e6b6fd022df9a297",
    HERE/"empty_bootstrap.py": "2d789b4fb28447a623f6118bb53a2b734645a9bbedb7a263007f52f4acc429a0",
}
SEALED = (HERE/"measurements/strict-cairo-0107.json.gz", "8e30886adeb6ec4b475a6f023fa0ed32b79bdc3e6b267710f1e75fef34850145")
ORIGINAL = (HERE/"measurements/history-risk-0107-cairo.json.gz", "6f6923e6a4be803069581d5a254148c6e322d9e0c4ea4e93de1062dd2bb485e9")
ORDER = (("stock", "tiny"), ("candidate", "tiny"), ("candidate", "weak"), ("stock", "weak"))
IMPORT_LINE = re.compile(r"import time:\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.+)")
ACTIVE_PHASE = "physical import probe: candidate active-only roots"


def checked(path, digest):
    data = path.read_bytes()
    if sha256(data).hexdigest() != digest:
        raise ValueError(f"Unexpected input {path}")
    return data


def controls():
    import gzip

    sealed = json.loads(gzip.decompress(checked(*SEALED)))
    raw = gzip.decompress(ORIGINAL[0].read_bytes())
    old = json.loads(raw)
    if sha256(raw).hexdigest() != ORIGINAL[1] or not sealed["qualified"] or not old["qualified"]:
        raise ValueError("Expected the complete physical two-case evidence")
    return sealed, old["admission"]["candidate_libraries"]


def ceiling(positive, tiny, stock, *, target=2):
    want = stock/target
    return dict(stock_s=stock, target_s=want, original_candidate_s=positive+tiny, needed_s=positive+tiny-want,
                cheapest_candidate_s=positive, even_zero_tiny_shortfall_s=positive-want,
                even_zero_tiny_speedup=stock/positive)


def guarded(root):
    protected = (root/"recording", root/"causal", root/"unread-offer.json", Path("/srv/bulk"), Path("/mnt/qnap01"))

    def avoid_data(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.path.abspath(os.fsdecode(args[0])))
            if any(path.is_relative_to(p) for p in protected) or path.name.endswith((".ci16", ".ci16.zst")):
                raise ValueError("The import-only probe must never read a request")

    return avoid_data


class PrefixComplete(Exception):
    pass


def stock_prefix(root):
    from runpy import run_path
    from unittest.mock import patch

    sys.path[:0] = [str(PAYLOAD), str(RELEASE/"src"), str(RELEASE)]
    from tools.pipeline_eval.qualification import experimental_publication as publication

    def stop_before_assets():
        if not {"tools.algo08_scan", "tools.algo08_position"} <= sys.modules.keys():
            raise ValueError("The installed normal imports were incomplete")
        raise PrefixComplete

    command = ["--recording", str(root/"recording"), "--archive", str(root/"causal"),
               "--region", str(root/"unread-offer.json"), "--bulk-root", str(root/"empty-output")]
    with patch.object(publication, "TemporaryDirectory", stop_before_assets):
        try:
            run_path(str(BASELINE))["main"](command)
        except PrefixComplete:
            return
    raise ValueError("Expected the installed code to stop exactly before its request assets")


def candidate_prefix(root, libraries, *, active):
    from types import SimpleNamespace
    from unittest.mock import patch
    import empty_bootstrap as boot
    import exact_named_raw as entry

    state = {}

    def retain_runtime():
        runtime = original_runtime()
        state["publication"], state["specification"] = runtime[3], runtime[1]
        return runtime

    def stop_before_offer(sources):
        original_receiver(sources)
        raise PrefixComplete

    def stop_before_handoff(*args):
        raise PrefixComplete

    original_runtime, original_receiver = boot.load_runtime, boot.receiver_symbols
    options = [flag_value for flag, item in libraries.items() for flag_value in (flag, item["path"])]
    args = entry.parser().parse_args(["--recording", str(root/"recording"), "--archive", str(root/"causal"),
              "--region", str(root/"unread-offer.json"), "--output", str(root/"unwritten"), "--archive-sha256", "sha256:"+64*"0",
              "--strict-packed-eight", "--packed-ci16-map", str(root/"empty-map"), "--packed-ci16-map-sha256", "sha256:"+64*"0",
              "--packed-ci16-codec", str(root/"empty-codec"), "--history-risk-route", "--cairo-six-sheets", *options])
    try:
        with patch.object(boot, "load_runtime", retain_runtime), patch.object(boot, "receiver_symbols", stop_before_offer):
            entry.run(args)
    except PrefixComplete:
        from packed_combined_input import packed_source
        from short_graph_guard import prove
        if not callable(packed_source) or not callable(prove) or set(boot.SCIENTIFIC_IMPORTS) & sys.modules.keys():
            raise ValueError("The ordinary receiver-first path loaded scientific modules")
    else:
        raise ValueError("Expected the detector setup to stop before the offer")

    start = perf_counter(), process_time()
    if active:
        print(ACTIVE_PHASE, file=sys.stderr, flush=True)
        try:
            with patch.object(entry, "request_from_handoff", stop_before_handoff):
                entry.publish_active(args, **state, handoff=SimpleNamespace(receiver=None))
        except PrefixComplete:
            from history_cairo_render import binding
            if not callable(binding):
                raise ValueError("The active prefix must resolve the real Cairo binding")
        else:
            raise ValueError("Expected the active import prefix to stop before the handoff")
    return dict(wall_s=perf_counter()-start[0], cpu_s=process_time()-start[1])


def worker(root, arm, case):
    for path, digest in PINS.items():
        checked(path, digest)
    libraries = json.loads((root/"libraries.json").read_text())
    sys.addaudithook(guarded(root))
    start = perf_counter(), process_time()
    active = None
    if arm == "stock":
        stock_prefix(root)
    else:
        active = candidate_prefix(root, libraries, active=case == "weak")
    print(json.dumps(dict(work_s=perf_counter()-start[0], work_cpu_s=process_time()-start[1], active=active,
                          module_count=len(sys.modules), data_reads=0, science_requests=0)))


def imports(trace):
    phases = {"initial": {}, "active": {}}
    target = phases["initial"]
    for line in trace.splitlines():
        if line == ACTIVE_PHASE:
            target = phases["active"]
        elif (match := IMPORT_LINE.fullmatch(line)) is not None:
            name = match[3].strip()
            target[name] = target.get(name, 0) + int(match[1])
    return phases


def overlap(first, second):
    left, right = first["initial"], second["initial"]
    modules = left.keys() & right.keys()
    return dict(count=len(modules), measured_common_s=[sum(values[name] for name in modules)/1e6 for values in (left, right)],
                active_only_s=sum(second["active"].values())/1e6)


def run(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from exact_named_raw import staged_path
    from north_direct_multichunk import checked_lease
    from short_raw_diagnostic import measure

    checked_lease()
    machine = host()
    if root.exists() or staged_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Use a new tmpfs directory")
    case, libraries = controls()
    root.mkdir()
    for name in ("recording", "causal", "empty-output"):
        (root/name).mkdir()
    for name in ("empty-map", "empty-codec"):
        (root/name).touch()
    write(root/"libraries.json", libraries)
    timed, traces = {}, {}
    for profile, order in ((False, ORDER), (True, ORDER[::-1])):
        for arm, shape in order:
            name = f"{arm}-{shape}" + ("-imports" if profile else "")
            config = root/(name+"-config")
            config.mkdir()
            command = [sys.executable, "-IB", *(["-X", "importtime"] if profile else []), str(Path(__file__)), "worker", str(root), arm, shape]
            wall = measure(command, os.environ | {"MPLCONFIGDIR": str(config)}, root/name)
            write(root/(name+"-clock.json"), wall)
            if wall["exit_code"]:
                raise ValueError(wall["stderr_tail"])
            worker_receipt = json.loads((root/(name+".stdout")).read_text())
            timed[name] = dict(through_exit=wall, prefix=worker_receipt, command=command)
            if profile:
                traces[arm,shape] = imports((root/(name+".stderr")).read_text())
    bounds = {name: ceiling(case["positive_costs"]["scopes"][name][0], case["costs"]["scopes"][name][0],
                             case["cohort"][name]["timing"]["elapsed_s"]["totals"]["stock"])
              for name in ("child", "ready", "ready_with_common")}
    sources = {str(path): digest for path, digest in PINS.items()}
    sources[str(Path(__file__))] = sha256(Path(__file__).read_bytes()).hexdigest()
    write(root/"result.json", dict(timed=timed, bounds=bounds, machine=machine, sources=sources,
                                  overlap={arm: overlap(traces[arm,"tiny"], traces[arm,"weak"]) for arm in ("stock", "candidate")},
                                  waveform_reads=0, publication_requests=0, data_binding_sha256=SEALED[1]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("run", "worker"))
    cli.add_argument("root", type=Path)
    cli.add_argument("arm", choices=("candidate", "stock"), nargs="?")
    cli.add_argument("case", choices=("tiny", "weak"), nargs="?")
    args = cli.parse_args()
    if args.action == "run":
        run(args.root)
    else:
        worker(args.root, args.arm, args.case)
