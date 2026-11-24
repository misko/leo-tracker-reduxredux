"""Run one charted saved confidence witness after the original admission guard."""

import argparse
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import sys
from time import time_ns
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CASE = "DS30-0049"
STAGE = Path("/dev/shm/leo-v3-cfo-epoch-0049-saved01")
ADMISSION = "ae8fe9afa9d040443219524d5f36992d6c383bffa378097664b3a5aca43ef293"
CHARTED = Path("/tmp/leo-v3-integrated-original-batch")
BUILD = Path("/tmp/leo-v3-integrated-original-batch-proof01/build.json")
BUILD_PIN = "30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
PRIOR_WATCH = "c9ccd01d2647c3422ec2ece46ad4273c2eebc93806a1ce56fd1e6781a9651c3d"
LOCAL_SOURCES = ("accepted_confidence_trial.py", "accepted_confidence_trace.py",
                 "accepted-confidence-protocol.md", "second_curve_gate_trial.py")


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x") as file:
        json.dump(value, file, indent=2, sort_keys=True, allow_nan=False)
        file.write("\n")


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"Changed pinned input at {path}")
    return json.loads(data)


def runtime(root):
    import sparse8_cfo_epoch_saved as saved

    admission = checked(STAGE/"admission.json", ADMISSION)
    signed = checked(STAGE/"authority.json", admission["authority_pin"])
    if admission["case"] != CASE:
        raise ValueError("The frozen resident DS30-0049 input is required")
    sys.addaudithook(saved.deny_backing)
    sys.path[:0] = [str(CHARTED/"reports/ALGO08/v3"), str(CHARTED)]
    import empty_bootstrap as boot
    import integrated_original_batch as chart
    import legacy_first_map_acceleration as acceleration
    book, _, prior_cutoff = chart.load_build(BUILD, BUILD_PIN)
    _, spec, _, publication, _ = boot.load_runtime()
    from leo.operations.tle_archive import TleArchiveReader
    from unified_short_bootstrap import Handoff
    from visit_frame_raw_0016 import resident
    session, inventory_sha = signed["session_id"], signed["inventory_sha256"]
    recording = Path(signed["recording"])
    archive, offer = STAGE/"tle", STAGE/"offer.json"
    chart.validate_case(signed, SimpleNamespace(recording=recording, region=offer))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    index = book["native"]["--portable-orbit-index"]
    portable = Path(index["path"]).resolve(strict=True)
    paths = [Path(ref.path).resolve(strict=True) for ref in refs]
    if len(paths) != 48 or any(not path.is_relative_to(archive) for path in paths) or not portable.is_relative_to("/dev/shm"):
        raise ValueError("Expected all original catalogue bodies and the resident cache in tmpfs")
    cached = resident(list(map(str, [*paths, portable])))
    cutoff = signed["causal_cutoff_utc_ns"]
    if prior_cutoff >= cutoff or chart.archive_digest(archive, cutoff) != signed["archive_sha256"]:
        raise ValueError("The original offered cutoff and signed resident catalogue changed")
    inventory = checked(STAGE/"inventory.json", inventory_sha)
    native = checked(STAGE/"native.json", admission["native_pin"])
    chart.match_native(signed, native)
    chart.match_inventory(signed, session, inventory_sha, inventory)
    detector = native["provenance"]["detector_sha256"][7:]
    boot.bind_native(native, session, inventory_sha, detector, expected="sha256:"+admission["native_pin"])
    handoff = Handoff(session, inventory_sha, detector, native)
    fast = book["native"]["--legacy-first-map-fast"]
    manifest = acceleration.checked_artifacts(Path(fast["path"]), fast["sha256"])
    args = SimpleNamespace(recording=recording, archive=archive, region=offer, output=root/"publication",
                           archive_sha256=signed["archive_sha256"], history_risk_route=True,
                           legacy_first_map_fast=Path(fast["path"]), legacy_first_map_fast_sha256=fast["sha256"],
                           portable_orbit_index=portable, portable_orbit_index_sha256=index["sha256"],
                           portable_orbit_producer_sha256=book["portable_producer"]["sha256"].removeprefix("sha256:"),
                           cairo_six_sheets=True, cairo_residual_layout=False)

    def saved_inventory(_store, chosen, *, verify_windows=True):
        if Path(chosen) != recording or verify_windows:
            raise ValueError("Only the frozen saved inventory may be requested")
        return session, inventory_sha, inventory

    source_files = {name: sha(HERE/name) for name in LOCAL_SOURCES}
    if source_files["second_curve_gate_trial.py"] != PRIOR_WATCH:
        raise ValueError("The previously bounded admission runner changed")
    custody = dict(case=CASE, native=admission["native_pin"], admission=ADMISSION,
                   build=BUILD_PIN, archive=signed["archive_sha256"], portable=index["sha256"],
                   region=signed["region_sha256"], cached=cached, sources=source_files)
    return custody, handoff, args, spec, publication, acceleration, manifest, saved_inventory


def preflight(output):
    book, handoff, args, spec, _, acceleration, _, _ = runtime(output.parent)
    from accepted_confidence_trace import ConfidenceTrace, binding
    import lighter_joint_estimator as estimator
    import exact_named_raw as raw
    from combined_successor_raw_entry import smoke
    from mixed_repair_centre_reset_trial import LAZY_TOOLS

    for name, pin in LAZY_TOOLS.items():
        if sha(CHARTED/"tools/pipeline_eval/variants"/name) != pin:
            raise ValueError(f"The source-relative positive dependency {name} changed")
    raw.request_from_handoff(args, handoff)
    args.output = output.with_suffix(".unused-publication")
    trace, stdout = ConfidenceTrace(), StringIO()
    with binding(estimator, trace), redirect_stdout(stdout):
        smoke(args, acceleration)
    if handoff.calls or trace.records or args.output.exists():
        raise ValueError("Positive-port preflight must leave inference untouched")
    write(output, dict(custody=book, positive=json.loads(stdout.getvalue()), steps=[]))


def worker(root, proof, pin, fd):
    import second_curve_gate_trial as admission

    if not os.path.samestat(os.fstat(fd), admission.LOCK.stat()):
        raise ValueError("Require inherited shared Gauss lease")
    expected = checked(proof, pin)
    actual, handoff, args, spec, publication, _, acceleration, inventory = runtime(root)
    if expected["custody"] != actual or expected["steps"] or not expected["positive"]["solver_setup"]:
        raise ValueError("The frozen saved custody or source preflight changed")
    from accepted_confidence_trace import ConfidenceTrace, binding, elapsed, now, summarize
    from combined_successor_raw_entry import solver_ports
    import exact_named_raw as raw
    from integrated_original_entry import positive_ports
    import lighter_joint_estimator as estimator
    from leo.storage.fast_scan import FastScanStore, FastSegmentSource
    from leo.storage.short_window import ShortWindowReader

    def deny(*_args, **_kwargs):
        raise ValueError("Saved confidence witness cannot execute waveform operations")

    start = now()
    write(root/"stage-start.json", dict(time_ns=time_ns(), preflight_sha256=pin))
    trace, portable = ConfidenceTrace(), {}
    try:
        with (binding(estimator, trace), patch.object(FastScanStore, "inventory", inventory),
              patch.object(FastSegmentSource, "windows", deny), patch.object(ShortWindowReader, "windows", deny),
              positive_ports(solver_ports, acceleration, portable)):
            receipt, witness = raw.publish_active(args, publication, spec, handoff)
    finally:
        write(root/"trace.json", dict(records=trace.records, publication_interval=elapsed(start)))
    attempt, = witness["ports"]["history_risk"]["lean_attempts"]
    if attempt["decision"] != "complete" or receipt["decision"] != "complete" or handoff.calls != 1:
        raise ValueError("Expected one normally accepted saved publication")
    write(root/"observed.json", dict(receipt=receipt, source_sha256=witness["source_sha256"],
                                    witness_sha256=sha(args.output/"exact-named-raw-witness.json"),
                                    input=actual["native"], trace_sha256=sha(root/"trace.json"),
                                    summary=summarize(trace.records), handoffs=handoff.calls))


def watch(root, proof, pin):
    import second_curve_gate_trial as admission

    if sha(Path(admission.__file__)) != PRIOR_WATCH:
        raise ValueError("Only the existing short shared-lease watcher is allowed")
    # Its launcher constructs a single fresh Python child using __file__.
    with patch.object(admission, "__file__", __file__):
        return admission.watch(CASE, root, proof, pin)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("preflight", "watch", "worker"))
    cli.add_argument("case", choices=(CASE,))
    cli.add_argument("output", type=Path)
    cli.add_argument("proof", type=Path, nargs="?")
    cli.add_argument("pin", nargs="?")
    cli.add_argument("--lease-fd", type=int)
    args = cli.parse_args()
    if args.mode == "preflight":
        preflight(args.output)
    elif args.mode == "watch":
        sys.exit(watch(args.output, args.proof, args.pin))
    else:
        worker(args.output, args.proof, args.pin, args.lease_fd)
