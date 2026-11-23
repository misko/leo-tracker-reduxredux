"""Prepare and verify one matched original-input North held-anchor experiment."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from aperture_trial import RELEASE, read, write
from combined_frontier_run import BLOCK_SHA
from dense_full_short_raw import checked
from dense_geographic_trial import host
from full_short_physical import CACHE_LIB, CACHE_SHA, environment
from full_short_run import GEOGRAPHIC_SHA, SHORT_SHA, TRACK_SCORES_SHA
from north_combined import CASES, assignments
from north_interlaced_raw import MANIFEST_SHA, NORTH, OFFER_SHA, SOURCE, SOURCE_SHA
from short_raw_diagnostic import measure
from weak_combined_raw import STOCK, STOCK_PIN


HERE = Path(__file__).resolve().parent
ORDER = ("stock", "candidate")
WINDOWS = 1200
INVENTORY = "sha256:985dfe1e0423b1106f5e205b9ccf1aec7f9d1e156d9262da19852521dd703d4b"
CANDIDATE = Path("/var/tmp/leo-v3-north-held-candidate")
COMMIT = "0d0b2ad9f5f44aaf56c04d77bb2ab226d03b912e"
CONTROLS = Path("/dev/shm/leo-held-anchor-route-controls-01/controls.json")
CONTROLS_SHA = "c36abe2ba57fc140e2c75fb331192afbc31cc31dc9820d2c64add8304bed6e3f"
PINS = {
    "--short-binary": (Path("/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/short-primary.so"), SHORT_SHA),
    "--geographic-library": (Path("/var/tmp/leo-dense-short-pins.0zaX7eSH/geographic.so"), GEOGRAPHIC_SHA),
    "--regional-track-library": (Path("/srv/bulk/leo-dev/regional-probe-block-20261123/scores.so"), TRACK_SCORES_SHA),
    "--frontier-block-library": (Path("/srv/bulk/leo-dev/regional-probe-block-20261123/block.so"), BLOCK_SHA),
}
FLAGS = ("--prove-empty-graph", "--one-pass-web-png", "--exact-graph-reuse", "--held-anchor-route")


def tmpfs(path):
    kind = subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", str(path)], text=True)
    if kind.strip() != "tmpfs":
        raise ValueError(f"Expected tmpfs: {path}")


def members(inventory):
    return tuple(
        (Path(segment["path"]) / "manifest.json", segment["manifest_digest"])
        for segment in inventory["segments"]
    )


def require_resident(cache):
    if (cache["unavailable"] or not cache["members"]
            or cache["members"] != cache["observed_members"]
            or not cache["observed_file_pages"]
            or cache["observed_file_pages"] != cache["cached_pages"]):
        raise ValueError(f"Public North raw cache changed before launch: {cache}")


def preflight(directory):
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.qualification.cache_residency import bound_snapshot, load_query
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3

    tmpfs(directory)
    if CASES[:2] != ("containing", "stock") or ORDER != ("stock", "candidate"):
        raise ValueError("Expected reversal of the original North raw pair")
    pair, _ = assignments()
    stock = pair["runs"]["candidate"]
    rec = Path(pair["recording"])
    archive = Path(pair["archive"]["root"])
    region = Path(pair["region"])
    for path in (rec, archive, region):
        tmpfs(path)
    checked(STOCK, STOCK_PIN)
    verified_v3(NAMED_V3)
    store = FastScanStore(directory)
    session, digest, inventory = store.inventory(rec, verify_windows=False)
    segments = members(inventory)
    if (rec.name != NORTH or session != stock["receipt"]["session_id"]
            or digest != INVENTORY or inventory["window_count"] != WINDOWS
            or segments != ((rec / "manifest.json", "sha256:" + MANIFEST_SHA),)):
        raise ValueError("Unexpected physical or modified source inventory")
    query = load_query(checked(CACHE_LIB, CACHE_SHA))
    cache = bound_snapshot(store, rec, segments, os.sysconf("SC_PAGE_SIZE"), query)
    require_resident(cache)
    manifest = read(rec / "manifest.json")
    compressed = sum(row["compressed_bytes"] for row in manifest["chunks"])
    return dict(
        source_pair=dict(path=str(SOURCE), sha256=SOURCE_SHA),
        recording=str(rec), archive=pair["archive"], offered_region=stock["receipt"]["region"],
        region_file=str(region), region_sha256=OFFER_SHA, planning_cache=cache,
        session=session, inventory=digest, windows=WINDOWS, compressed_bytes=compressed,
        stock=dict(launcher=str(STOCK), sha256=STOCK_PIN, receipt=stock["receipt"],
                   raw_authority=stock["raw_authority"]),
        order=ORDER,
        sources={p.name: sha256(p.read_bytes()).hexdigest()
                 for p in (Path(__file__), HERE / "north-held-anchor-pair-protocol.md")},
    )


def publication_evidence(directory, receipt, clock, assignment):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from tools.pipeline_eval.qualification.paired_publication import evidence

    if receipt["decision"] != "complete" or receipt["window_count"] != WINDOWS:
        raise ValueError("The public containing replay must have two completed position arms")
    if (
        receipt["session_id"] != assignment["session"]
        or receipt["region"] != assignment["offered_region"]
        or receipt["counts"] != assignment["stock"]["receipt"]["counts"]
    ):
        raise ValueError("Assigned region, support or session changed")
    verified = evidence(directory, receipt, clock["started_unix_ns"], read_only=True)
    run = receipt["run_id"]
    work = directory / "fast-scan-automatic-work"
    (native_path,) = work.glob("*/detections.json")
    (terminal_path,) = work.glob("*/terminal.json")
    native, terminal = read(native_path), read(terminal_path)
    source = native["source"]
    probes = source["probes"]
    if (
        terminal_path.parent.name != run
        or source["input_manifest_sha256"] != assignment["inventory"]
        or source["session_id"] != assignment["session"]
        or source["raw_recording_authority_digest"] != assignment["stock"]["raw_authority"]
        or verified["raw_authority"] != assignment["stock"]["raw_authority"]
        or canonical_digest(native) != terminal["native_sha256"]
        or len(probes) != 2 * receipt["counts"]["processed"]
        or set(verified["arms"]) != {"c0", "fitted_c"}
        or any(point.get("latlon") is None or point.get("rf_rms_hz") is None
               for point in verified["arms"].values())
    ):
        raise ValueError("Unbound detector packet or incomplete calibration arms")
    rendered = artifacts(directory, receipt)
    pngs = rendered["images"]
    if tuple(pngs) != tuple(PLOTS):
        raise ValueError("Expected eight independently decoded web PNGs")
    store = FastStandardAnalysisStore(directory)
    path, grid = store.position_path(run), store.position_grid(run)
    if not grid["complete"] or any(
        item["binding"]["position_png_sha256"] != pngs["position"]["sha256"]
        for item in (path, grid)
    ):
        raise ValueError("Position evidence lost its own verified PNG binding")
    start = clock["started_unix_ns"]
    detector_file = (native_path.stat().st_mtime_ns - start) / 1e9
    if not 0 < detector_file <= clock["elapsed_s"]:
        raise ValueError("Raw handoff file is outside the measured process")
    return dict(
        verified=verified, figures=pngs, grid_points=grid["evaluated_points"], native=native,
        native_sha256=terminal["native_sha256"],
        detector_ready_s=detector_file,
        report_ready_s=((directory / "fast-scan-reports" / f"{run}.json").stat().st_mtime_ns
                        - start) / 1e9,
        cutoff_utc_ns=native["clock_anchor"]["before"]["realtime_ns"],
        opportunity_sha256=canonical_digest([
            {key: value for key, value in probe.items() if key != "candidates"}
            for probe in probes
        ]),
    )


def admission():
    controls = read(checked(CONTROLS, CONTROLS_SHA))
    expected = {
        "north": ("history", 456, "sha256:a03fefaf84057a282a0868ae8a52d34099f530dcf69220360147389e110523c3"),
        "DS30-0016": ("unfiltered", 475, "sha256:c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"),
    }
    if controls["waveform_calls"] or controls["publications"] or set(controls["controls"]) != set(expected):
        raise ValueError("Archived controls changed")
    for name, (route, factors, digest) in expected.items():
        data = controls["controls"][name]
        receipt = data["receipt"]
        if (not data["previous_chosen_verified"] or data["factors"] != factors
                or receipt["choice"]["route"] != route or receipt["selected_native_sha256"] != digest):
            raise ValueError(f"Archived chosen-packet parity unavailable for {name}")
    return controls["controls"]


def candidate_entry():
    def git(*args):
        return subprocess.check_output(["git", "-c", f"safe.directory={CANDIDATE}", "-C", str(CANDIDATE), *args])

    if git("rev-parse", "HEAD").decode().strip() != COMMIT or git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Candidate tree differs from the validated commit")
    entry = CANDIDATE / HERE.relative_to(HERE.parents[2]) / "unified_short_bootstrap.py"
    committed = git("show", f"{COMMIT}:{entry.relative_to(CANDIDATE)}")
    if entry.read_bytes() != committed:
        raise ValueError("Unfrozen unified CLI")
    return entry


def launch(directory):
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.qualification.cache_residency import bound_snapshot, load_query

    machine = host()
    assignment = preflight(directory)
    controls = admission()
    entry = candidate_entry()
    python = RELEASE / "venv/bin/python"
    rec = Path(assignment["recording"])
    store = FastScanStore(directory)
    _, _, inventory = store.inventory(rec, verify_windows=False)
    segments = members(inventory)
    query = load_query(checked(CACHE_LIB, CACHE_SHA))
    arguments = ["--recording", rec, "--archive", assignment["archive"]["root"],
                 "--region", assignment["region_file"]]
    libs = [part for flag, (path, digest) in PINS.items() for part in (flag, checked(path, digest))]
    commands = {
        "stock": [STOCK, *arguments, "--bulk-root", directory / "stock"],
        "candidate": [python, "-BPs", entry, *arguments, *libs, *FLAGS, "--output", directory / "candidate"],
    }
    env = environment(directory)
    candidate_env = dict(env, PYTHONPATH=os.pathsep.join(map(str, (
        entry.parent, Path("/opt/leo-algo08/algo08v3/payload"), RELEASE / "src", RELEASE, CANDIDATE,
    ))))
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    binding = dict(assignment=assignment, machine=machine, candidate_commit=COMMIT,
                   candidate_entry_sha256=sha256(entry.read_bytes()).hexdigest(),
                   controls_sha256=CONTROLS_SHA, controls=controls,
                   binaries={flag: dict(path=str(path), sha256=digest) for flag, (path, digest) in PINS.items()},
                   commands={name: list(map(str, command)) for name, command in commands.items()})
    frozen = directory / "binding.json"
    with frozen.open("x") as stream:
        json.dump(binding, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    (directory / "stock").mkdir()
    for arm in ORDER:
        cache = bound_snapshot(store, rec, segments, os.sysconf("SC_PAGE_SIZE"), query)
        require_resident(cache)
        write(directory / f"{arm}-cache.json", cache)
        clock = measure(commands[arm], candidate_env if arm == "candidate" else env, directory / arm)
        write(directory / f"{arm}-clock.json", clock)
        if clock["exit_code"]:
            raise ValueError(f"The {arm} process exited {clock['exit_code']}. See {directory / (arm + '.stderr')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--launch", action="store_true")
    args = parser.parse_args()
    if args.launch:
        launch(args.directory)
    else:
        write(args.directory / "preflight.json", preflight(args.directory))
