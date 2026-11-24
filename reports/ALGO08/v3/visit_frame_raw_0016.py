"""One ordinary/visit-index raw pair on the same freshly encoded physical capture."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
REFERENCE = Path("/dev/shm/leo-v3-history-risk-0016-cairo-result01")
CAIRO = Path("/dev/shm/leo-v3-history-risk-0016-cairo-score01.json")
CAIRO_PIN = "b340a594fadae0b871c42d31ac269efe2cfe0a34d26089038c739e4bb8822e39"
WRITER = Path("/dev/shm/leo-v3-frame-visit-0016-recording01")
AUTHORITY_PIN = "sha256:afb5a48420d0c1ab9d021e61aab59e3898298b27b0a998fd193dd823ef2383a3"
WRITER_PIN = "sha256:bf246173e0a702ac89cc1a589e6db57388fe65a60f436b77c747ad05b33e3ebc"
ORDER = ("ordinary", "frames")
SOURCES = (Path(__file__).name, "exact_named_raw.py", "visit_frame_input.py", "visit_frame_reader.py",
           "visit-frame-raw-0016-protocol.md", "unified_short_bootstrap.py")


def digest(path):
    return "sha256:"+sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def checked(path, pin):
    if digest(path) != "sha256:"+pin.removeprefix("sha256:"):
        raise ValueError(f"Pinned input changed at {path}")
    return read(path)


def source_pins():
    return {name: digest(HERE/name) for name in SOURCES}


def references():
    from exact_named_raw import staged_path

    old = checked(staged_path(CAIRO), CAIRO_PIN)
    if not old["qualified"] or not all(old["checks"].values()) or old["optional_process"]["clock"]["exit_code"]:
        raise ValueError("The archived original-input Cairo control is incomplete")
    return old


def command(previous, role, recording, output, authority, authority_pin):
    command = list(previous)
    if (role not in ORDER or Path(command[5]).name != "exact_named_raw.py"
            or not {"--history-risk-route", "--cairo-six-sheets"} <= set(command)
            or any(flag.startswith(("--strict-packed", "--visit-frame", "--portable-orbit")) for flag in command)):
        raise ValueError("Expected the qualified ordinary history-risk Cairo command")
    command[5] = str(HERE/"exact_named_raw.py")
    for flag, path in (("--recording", recording), ("--output", output)):
        command[command.index(flag)+1] = str(path)
    if role == "frames":
        command.extend(("--visit-frame-custody", str(authority), "--visit-frame-custody-sha256", authority_pin))
    return command


def resident(paths):
    from os import sysconf

    if len(paths) != len(set(paths)):
        raise ValueError("The custody roster contains a repeated physical path")
    report = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,PAGES,SIZE,FILE", *paths]))["fincore"]
    if len(report) != len(paths) or any(row["res"] < row["size"] for row in report):
        raise ValueError("All encoded files, index metadata and orbit bodies must be resident")
    extent = sum((row["size"]+sysconf("SC_PAGE_SIZE")-1)//sysconf("SC_PAGE_SIZE") for row in report)
    return dict(cached_pages=extent, observed_file_pages=extent, observed_members=len(paths),
                bytes=sum(row["size"] for row in report), unavailable={})


def authenticate(authority, authority_pin, recording):
    from exact_named_raw import staged_path
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.short_window import ShortWindowReader
    from visit_frame_input import CHUNK_FIELDS, bind_inventory, custody

    plan = custody(staged_path(authority), authority_pin, staged_path(recording))
    session, inventory, value = FastScanStore(recording.parent).inventory(recording, verify_windows=False)
    bind_inventory(plan, session, inventory, value)
    paths = [authority]
    for segment in plan["segments"]:
        folder = recording/segment["directory"]
        reader = ShortWindowReader(folder)
        lifecycle = segment["lifecycle"]
        if (any(getattr(reader.manifest, name) != value for name, value in lifecycle.items())
                or any(lifecycle[name] != segment["original_lifecycle"][name]
                       for name in ("status", "failure", "stop_reason"))):
            raise ValueError("The new ordinary file must preserve original lifecycle outcomes")
        paths.append(staged_path(folder/"manifest.json", root=recording))
        for row, chunk in zip(segment["members"], reader.manifest.chunks, strict=True):
            if any(row[key] != getattr(chunk, key) for key in CHUNK_FIELDS):
                raise ValueError("The actual ordinary input member differs from detached custody")
            paths.extend(staged_path(folder/name, root=recording) for name in (
                chunk.payload_relative_path, chunk.index_relative_path, row["side_name"]))
    if (plan["window_count"] != 808 or [s["window_count"] for s in plan["segments"]] != [512, 296]
            or [len(s["members"]) for s in plan["segments"]] != [8, 5]):
        raise ValueError("Only the complete original prepared physical recording is enrolled")
    return plan, paths


def new_source(root, authority_pin, receipt_pin):
    from exact_named_raw import staged_path

    source = checked(staged_path(root/"receipt.json"), receipt_pin)
    authority = staged_path(root/"capture-authority.json")
    declared = checked(authority, authority_pin)
    readback = source["readback"]
    indexes = [row["counts"] for row in readback["seek_checks"]]
    if (source["capture_authority_sha256"] != authority_pin or source["case"] != "DS30-0016"
            or source["new_recording"] != declared["recording"]
            or any(readback[name] != declared[name] for name in ("session_id", "window_count", "inventory_sha256", "raw_authority"))
            or len(indexes) != 13 or sum(count["prefix_checks"] for count in indexes) != 808):
        raise ValueError("The independent writer receipt has a different authority seal")
    plan, inputs = authenticate(authority, authority_pin, Path(declared["recording"]))
    return source, authority, plan, inputs


def launch(root, writer, authority_pin, receipt_pin):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import clock, now
    from exact_named_raw import parser, staged_path
    from leo.operations.tle_archive import TleArchiveReader
    from raw_0016_best_trial import measure_mode
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    if root.exists() or root.parent != Path("/dev/shm") or writer != WRITER:
        raise ValueError("Use the enrolled detached source and a fresh private tmpfs output")
    started = now()
    machine, previous = host(), references()
    request = previous["admission"]["request"]
    writer_receipt, authority, plan, wave_paths = new_source(writer, authority_pin, receipt_pin)
    if (writer_receipt["source_custody_sha256"] != previous["admission"]["custody_sha256"]
            or writer_receipt["original_inventory_sha256"] != request["inventory"]
            or writer_receipt["original_raw_authority"] != request["authority"]):
        raise ValueError("The independent writer must bind the original physical Cairo recording")
    if (plan["inventory_sha256"] == request["inventory"] or plan["raw_authority"] == request["authority"]
            or plan["session_id"] == request["session"]):
        raise ValueError("Do not reuse the historical input identity for the new encoding")
    archive = staged_path(Path(request["archive"]["root"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (archive_identity(archive) != request["archive"] or len(refs) != 46
            or any(ref.collected_utc_ns >= request["cutoff_utc_ns"] for ref in refs)
            or digest(staged_path(Path(request["region"]))) != "sha256:"+request["offer_sha256"]):
        raise ValueError("The original regional offer, archive or cutoff changed")
    tle_paths = [staged_path(ref.path, root=archive) for ref in refs]
    causal_pages = resident(tle_paths)
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    shutil.copytree(REFERENCE/"fonts", root/"fonts")
    paired = {role: command(previous["command"], role, Path(plan["recording"]), root/role, authority, authority_pin) for role in ORDER}
    for role in ORDER:
        args = parser().parse_args(paired[role][6:])
        if not (args.history_risk_route and args.cairo_six_sheets and bool(args.visit_frame_custody) == (role == "frames")):
            raise ValueError("The actual exact named research CLI does not expose the qualified pair")
    write(root/"admission.json", dict(source=plan, writer_receipt_sha256=receipt_pin, authority_sha256=authority_pin,
          writer_receipt=writer_receipt, archive=request["archive"], cutoff_utc_ns=request["cutoff_utc_ns"],
          historical_cairo_sha256=CAIRO_PIN, order=list(ORDER), machine=machine, sources=source_pins(), commands=paired,
          common_setup=clock(started), causal_residency_before=causal_pages))
    for role in ORDER:
        measure_mode(root, role, paired[role], environment_for(root), lambda: resident(wave_paths), require_success=False)
    write(root/"causal-after.json", resident(tle_paths))
    write(root/"sealed.json", {name: digest(root/name) for name in (
        "ordinary-clock.json", "frames-clock.json", "admission.json", "causal-after.json")})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("output", type=Path)
    cli.add_argument("--writer", type=Path, default=WRITER)
    cli.add_argument("--custody-sha256", default=AUTHORITY_PIN)
    cli.add_argument("--writer-receipt-sha256", default=WRITER_PIN)
    options = cli.parse_args()
    if options.action == "launch":
        launch(options.output, options.writer, options.custody_sha256, options.writer_receipt_sha256)
    else:
        from visit_frame_raw_score import score

        score(options.output)
