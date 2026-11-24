"""One ordinary-renderer history-risk publication on the sealed dense mixed packet."""

import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
PROTOCOL = HERE / "history-risk-dense-mixed-protocol.md"
RECIPE = "authenticated saved 20/12 ms all visits, EOF unfiltered, earlier-orbit dispatch, ordinary renderer"
NATIVE = "sha256:ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"
COUNTS = {"processed": 6765, "invalid_capture": 7, "skipped_fast_score": 0}
EXACT = Path("/dev/shm/leo-exact-solver-0008-result01")
FINISH = Path("/dev/shm/leo-v3-mixed-final-0008-01")
CONTROL_PINS = {
    "exact": "f4750387b41c8247e6195a162a5653f11c2fd2281b23faa857cddbb1bc29255a",
    "finish": "da352d9b4b08a7d79be2fb46735afc7b63f2fee8bb29c1c886e268fae012dd1d",
}
SOURCE_PINS = {
    "exact_named_raw.py": "0495af4960cf0dc7df62034fa66fcdfa41798fc1dc2a7c035e2e6eeec5994186",
    "history_risk_route.py": "56cef69f9bfeed078e938da61e319e2b8c3a250fa45133907096ac8d0e5272b7",
}


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open("rb") as content:
        return file_digest(content, "sha256").hexdigest()


def source_pins():
    from exact_named_raw import RISK_SOURCES
    from exact_named_route import SOURCES

    pins = {str(path.relative_to(ROOT)): digest(path) for path in
            {*SOURCES, *(HERE / name for name in RISK_SOURCES), PROTOCOL, Path(__file__).resolve(),
             HERE / "exact_named_raw.py", HERE / "named_hybrid_baseline.py",
             HERE / "cumulative_grid_projection.py", HERE / "mixed_named_finish_0008.py"}}
    for name, expected in SOURCE_PINS.items():
        if pins[str((HERE / name).relative_to(ROOT))] != expected:
            raise ValueError(f"The reviewed release port changed: {name}")
    return pins


def deny_original(event, args):
    if event not in {"open", "os.listdir", "os.scandir"} or not isinstance(args[0], (str, bytes)):
        return
    path = Path(os.path.abspath(os.fsdecode(args[0])))
    if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01"):
        raise PermissionError("This saved publication cannot consult any backing data")


def certify_packet(native, req):
    source = native["source"]
    probes = source["probes"]
    if (req["native"] != NATIVE or req["issued"] != 6772
            or native["provenance"]["processed_windows"] != COUNTS["processed"]
            or source["raw_recording_authority_digest"] != req["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != req["cutoff_utc_ns"]
            or len(probes) != 13530 or sum(len(row["candidates"]) for row in probes) != 7336):
        raise ValueError("Expected the original, full-size mixed-aperture native document")


def publication_witness(document):
    recipe = dict(document["solver_recipe"], recipe=RECIPE)
    if (document["raw_route"] != "history_risk_installed" or "web_renderer" in recipe
            or not recipe["history_risk"]["requested"] or recipe["orbit_index"] != "cold"):
        raise ValueError("Expected only the reviewed history-risk route and ordinary renderer")
    return dict(document, raw_route="history_risk_saved_mixed", solver_recipe=recipe)


def preflight():
    from empty_bootstrap import checked
    from exact_named_route import checked_catalogue, resident_path
    from full_short_raw import RECIPE_SHA
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from mixed_named_finish_0008 import REQUEST_PIN, STAGED

    original = json.loads(checked(resident_path(STAGED / "request.json"), REQUEST_PIN))
    selection = json.loads(checked(resident_path(STAGED / "route-decision.json"), original["selection_sha256"]))
    if (selection["choice"]["route"] != "unfiltered" or original["original"]["detector"] != RECIPE_SHA
            or {original[mode]["native_sha256"] for mode in ("original", "selected")} != {NATIVE}):
        raise ValueError("The sealed EOF selection must preserve the original mixed detections")
    packet = resident_path(Path(original["original"]["file"]))
    offer = resident_path(Path(original["offer"]))
    inventory = resident_path(STAGED / "selected/fast-scan-inputs" / (original["session"] + ".json"))
    checked(offer, original["offer_sha256"])
    meta = json.loads(checked(inventory, original["inventory"][7:]))
    req = {key: original[key] for key in ("recording", "authority", "inventory", "session", "archive",
                                          "cutoff_utc_ns", "offer_sha256", "selection_sha256")}
    req.update(native=original["original"]["native_sha256"], packet=str(packet), region=str(offer),
               saved_inventory=str(inventory), issued=meta["window_count"], staged_request_sha256=REQUEST_PIN)
    certify_packet(json.loads(checked(Path(req["packet"]), NATIVE[7:])), req)
    archive = req["archive"]
    _, refs = checked_catalogue({"archive": archive["root"]}, dict(local_archive=dict(archive, snapshots=archive["records"]),
                              original_archive=archive, causal_cutoff_utc_ns=req["cutoff_utc_ns"]),
                              TleArchiveReader, canonical_digest)
    resident = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE,PAGES",
                                                   *(ref.path for ref in refs)], text=True))["fincore"]
    if len(resident) != 47 or any(row["res"] < row["size"] for row in resident):
        raise ValueError("The 47 authenticated causal files must already be resident")
    for name, root in (("exact", EXACT), ("finish", FINISH)):
        if digest(resident_path(root / "result.json")) != CONTROL_PINS[name]:
            raise ValueError("An archived same-packet control changed")
    return dict(request=req, sources=source_pins(), archive_resident_pages=sum(row["pages"] for row in resident),
                archive_snapshots=len(resident), archive_bytes=sum(row["size"] for row in resident), controls=CONTROL_PINS)


def worker(root):
    import empty_bootstrap as boot
    import exact_named_raw as publisher

    sys.addaudithook(deny_original)
    bound = read(root / "binding.json")
    req = bound["request"]
    if source_pins() != bound["sources"] or req["native"] != NATIVE:
        raise ValueError("The frozen publication source changed")
    _, specification, _, publication, _ = boot.load_runtime()
    from cumulative_grid_projection import saved_inventory_port
    from full_short_raw import RECIPE_SHA
    from leo.storage.fast_scan import FastSegmentSource
    from named_constrained_research import deny_waveform
    from raw_cfo_north_trial import native_file
    from unified_short_bootstrap import Handoff

    native = json.loads(boot.checked(Path(req["packet"]), NATIVE[7:]))
    certify_packet(native, req)
    boot.checked(Path(req["region"]), req["offer_sha256"])
    boot.checked(Path(req["saved_inventory"]), req["inventory"][7:])
    boot.bind_native(native, req["session"], req["inventory"], RECIPE_SHA, expected=NATIVE)
    output = root / "candidate"
    options = SimpleNamespace(recording=Path(req["recording"]), archive=Path(req["archive"]["root"]),
        archive_sha256=req["archive"]["snapshots_sha256"], region=Path(req["region"]), output=output,
        portable_orbit_index=None, portable_orbit_index_sha256=None, portable_orbit_producer_sha256=None,
        history_risk_route=True)
    handoff = Handoff(req["session"], req["inventory"], RECIPE_SHA, native)
    write = publisher.write

    def saved_witness(path, document, *, scientific=False):
        # The shared entry's default receipt describes its live 20/8 ms receiver.
        if path != output / "exact-named-raw-witness.json":
            raise ValueError("Only the current publisher witness may receive the saved-input label")
        write(path, publication_witness(document), scientific=scientific)

    with (saved_inventory_port(req) as inventory, patch.object(FastSegmentSource, "windows", deny_waveform),
          patch.object(publisher, "write", saved_witness)):
        terminal, _ = publisher.publish_active(options, publication, specification, handoff)
    if not inventory or handoff.calls != 1 or digest(native_file(output)) != NATIVE[7:]:
        raise ValueError("Expected the unchanged native packet after a single saved handoff")
    write(root / "publication.json", dict(receipt=terminal, waveform_acquisitions=0, verified_handoffs=handoff.calls,
                                         native_sha256=NATIVE, release=boot.BASELINE_PIN))


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from mixed_named_finish_0008 import STAGED
    from short_raw_diagnostic import measure

    started = process_time_ns(), perf_counter_ns()
    sys.addaudithook(deny_original)
    machine = host()
    if root.parent.resolve(strict=True) != Path("/dev/shm") or root.exists():
        raise ValueError("Use a fresh private tmpfs root")
    record = preflight()
    root.mkdir(mode=0o700)
    (root / "tmp").mkdir()
    (root / "fonts").mkdir()
    for source in (STAGED / "fonts").glob("fontlist-*.json"):
        (root / "fonts" / source.name).hardlink_to(source)
    command = ["/usr/bin/timeout", "--kill-after=2s", "100s", RELEASE / "venv/bin/python", "-IB",
               Path(__file__).resolve(), "worker", root]
    env = environment(root) | {"TMPDIR": str(root / "tmp"), "XDG_CACHE_HOME": str(root / "tmp")}
    record.update(machine=machine, command=list(map(str, command)),
                  admission=dict(cpu_ns=process_time_ns()-started[0], elapsed_ns=perf_counter_ns()-started[1]))
    write(root / "binding.json", record)
    clock = measure(command, env, root / "candidate")
    write(root / "clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "launch", "worker"))
    parser.add_argument("root", type=Path, nargs="?")
    args = parser.parse_args()
    if args.action == "preflight":
        print(json.dumps(preflight(), indent=2))
    elif args.root is None:
        parser.error("A fresh launch root is required")
    else:
        {"launch": launch, "worker": worker}[args.action](args.root)
