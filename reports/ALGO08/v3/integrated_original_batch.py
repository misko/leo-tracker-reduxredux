"""Run the charted original-file successor from a signed stock-shaped request."""

import argparse
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
BUILD_SCHEMA = "algo08v3-integrated-original-build-v1"
AUTHORITY_SCHEMA = "algo08v3-original-request-v1"
RELEASE_SCHEMA = "algo08v3-integrated-original-release-v1"
RELEASE_FILE = "algo08v3-successor-release.json"
CHARTED_COMMIT = "b54ea2104"
CHARTED_ADMISSION = "sha256:8cf2875a994a28d088bdf5b2afd7503df6c6c41b1798b554489ab4613641e872"
WAVEFORM_SUFFIX = ".ci16.zst"
QNAP = Path("/mnt/qnap01")
BULK = Path("/srv/bulk")
THREADS = ("OMP_NUM_THREADS", "OMP_THREAD_LIMIT", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "BLIS_NUM_THREADS", "NUMEXPR_NUM_THREADS")
PATH_OPTIONS = ("--short-binary", "--geographic-library", "--regional-track-library", "--frontier-block-library")
SIGNED_OPTIONS = ("--legacy-first-map-history", "--legacy-first-map-fast", "--portable-orbit-index")
FLAGS = ("--history-risk-route", "--cairo-six-sheets", "--verify-original-once", "--sparse8-primary")
SNAPSHOT_SOURCES = ("prefetch_snapshots.py", "legacy_snapshot_reuse.py")


def tagged_bytes(body):
    return "sha256:" + sha256(body).hexdigest()


def tagged(pin):
    tag = "sha256:" + pin.removeprefix("sha256:")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", tag):
        raise ValueError("Expected an externally pinned SHA-256")
    return tag


def direct(path):
    if path.is_relative_to(QNAP) or not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError(f"Expected a direct approved local path: {path}")
    return path


def checked(path, pin):
    body = direct(path).read_bytes()
    if tagged_bytes(body) != tagged(pin):
        raise ValueError(f"SHA-256 mismatch: {path}")
    return body


def document(path, pin):
    value = json.loads(checked(path, pin))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object: {path}")
    return value


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")


def checked_artifact(entry):
    if set(entry) != {"path", "sha256"}:
        raise ValueError("Every native artifact needs an explicit path and SHA-256")
    path = Path(entry["path"])
    checked(path, entry["sha256"])
    return path


def make_build(charted_admission, *, reuse_prefetched_snapshots=False):
    """Freeze one externally reviewed build once, using the existing chart receipt."""
    from integrated_original_entry import PNG_LIBRARY, PNG_SHA

    charted = document(charted_admission, CHARTED_ADMISSION)
    argv = charted["command"]

    def option(flag):
        return argv[argv.index(flag) + 1]

    native = dict(charted["native"])
    for flag in SIGNED_OPTIONS[1:]:
        native[flag] = dict(path=option(flag), sha256=option(flag + "-sha256"))
    source_pins = dict(charted["sources"])
    source_pins[str(Path(__file__).relative_to(ROOT))] = tagged_bytes(Path(__file__).read_bytes())
    if reuse_prefetched_snapshots:
        for name in SNAPSHOT_SOURCES:
            source = HERE / name
            source_pins[str(source.relative_to(ROOT))] = tagged_bytes(source.read_bytes())
    return dict(
        schema=BUILD_SCHEMA, charted_commit=CHARTED_COMMIT, charted_admission=CHARTED_ADMISSION,
        sources=source_pins, native=native, png=dict(path=str(PNG_LIBRARY), sha256=PNG_SHA),
        portable_producer=dict(path=str(Path(option("--portable-orbit-index")).parent / "artifact-bind.json"),
                               sha256=option("--portable-orbit-producer-sha256")),
    )


def load_build(path, pin, *, reuse_prefetched_snapshots=False):
    book = document(path, pin)
    if (book.get("schema") != BUILD_SCHEMA or book.get("charted_commit") != CHARTED_COMMIT
            or book.get("charted_admission") != CHARTED_ADMISSION
            or set(book["native"]) != {*PATH_OPTIONS, *SIGNED_OPTIONS}
            or not book["sources"]):
        raise ValueError("Unknown charted original-file successor build")
    for name, checksum in book["sources"].items():
        source = (ROOT / name).resolve(strict=True)
        if not source.is_relative_to(ROOT) or source != ROOT / name:
            raise ValueError(f"Source leaves its frozen checkout: {name}")
        checked(source, checksum)
    if reuse_prefetched_snapshots and any(str((HERE / name).relative_to(ROOT)) not in book["sources"]
                                          for name in SNAPSHOT_SOURCES):
        raise ValueError("The build must pin both private snapshot sources")
    native = {flag: checked_artifact(entry) for flag, entry in book["native"].items()}
    png = checked_artifact(book["png"])
    producer = checked_artifact(book["portable_producer"])
    expected = native["--portable-orbit-index"].parent / "artifact-bind.json"
    transport = document(native["--legacy-first-map-fast"], book["native"]["--legacy-first-map-fast"]["sha256"])
    acceleration = [checked_artifact(transport[name]) for name in ("hasher", "projection", "template")]
    provenance = document(producer, book["portable_producer"]["sha256"])
    if (producer != expected or provenance["portable_sha256"] != tagged(book["native"]["--portable-orbit-index"]["sha256"])
            or type(provenance["source"]["cutoff_utc_ns"]) is not int
            or provenance["source"]["cutoff_utc_ns"] <= 0):
        raise ValueError("Portable catalogue producer does not bind the charted index")
    return book, frozenset((*native.values(), *acceleration, png, producer)), provenance["source"]["cutoff_utc_ns"]


def verify_paths(args):
    roots = (direct(args.recording), direct(args.archive))
    if any(not root.is_dir() for root in roots):
        raise ValueError("Original recording and causal archive must be directories")
    direct(args.region)
    direct(args.bulk_root.parent)
    if (args.bulk_root.exists() or args.bulk_root.is_symlink() or args.bulk_root.name in ("", ".", "..")
            or args.bulk_root.is_relative_to(QNAP) or any(args.bulk_root.is_relative_to(root) for root in roots)):
        raise ValueError("Use a fresh local --bulk-root outside the input trees")
    route_output = args.bulk_root.with_name(args.bulk_root.name + "-held-anchor-route.json")
    if route_output.exists() or route_output.is_symlink():
        raise ValueError("The held-anchor output beside --bulk-root already exists")


def validate_case(authority, args):
    expected = {"schema", "recording", "session_id", "inventory_sha256", "raw_authority_sha256",
                "window_count", "causal_cutoff_utc_ns", "archive_sha256", "region_sha256"}
    if (set(authority) != expected or authority["schema"] != AUTHORITY_SCHEMA
            or authority["recording"] != str(args.recording)
            or type(authority["window_count"]) is not int or authority["window_count"] < 1
            or type(authority["causal_cutoff_utc_ns"]) is not int or authority["causal_cutoff_utc_ns"] < 1
            or authority["session_id"] != "fast-" + tagged(authority["inventory_sha256"])[7:39]):
        raise ValueError("The case authority does not describe this original stock-shaped request")
    for name in ("inventory_sha256", "raw_authority_sha256", "archive_sha256", "region_sha256"):
        if tagged(authority[name]) != authority[name]:
            raise ValueError(f"Expected canonical tagged {name}")
    return checked(args.region, authority["region_sha256"])


def archive_digest(path, cutoff):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    refs = TleArchiveReader(path).list_snapshots("space-track")
    if not refs or any(ref.collected_utc_ns >= cutoff for ref in refs):
        raise ValueError("Supply the complete enrolled causal view, with every TLE before the original cutoff")
    return canonical_digest({ref.path.name: ref.sha256 for ref in refs})


def original_inventory(recording, output):
    from leo.storage.fast_scan import FastScanStore
    from reports.ALGO08.v3.legacy_block_input import ordered_members

    session, digest, inventory = FastScanStore(output).inventory(recording, verify_windows=False)
    for reader, _ in ordered_members(inventory):
        manifest = reader.manifest
        if (manifest.schema_version != 2 or manifest.sample_rate_hz != 10_000_000
                or tuple(manifest.receiver_ids) != (0, 1)):
            raise ValueError("The charted receiver requires original signed V2 dual-antenna 10 MS/s segments")
    return session, digest, inventory


def generate_authority(args):
    """Generate detached input metadata using the same ordinary source API."""
    import empty_bootstrap as boot

    verify_paths(args)
    boot.load_runtime()
    from reports.ALGO08.v3.legacy_block_input import ordered_members, raw_authority
    from reports.ALGO08.v3.legacy_block_seek import read_rows

    session, digest, inventory = original_inventory(args.recording, args.bulk_root)
    hashes, cutoff = [], None
    for reader, chunk in ordered_members(inventory):
        for row in read_rows(reader, chunk):
            acquisition = row.acquisition
            bracket = json.loads(acquisition["retune_receipt"]).get("utc_clock_bracket")
            if bracket is not None:
                if hashes or cutoff or bracket["sample_counter"] != acquisition["sample_start"]:
                    raise ValueError("The signed index has an invalid initial hardware clock")
                cutoff = bracket["before"]["realtime_ns"]
            hashes.append(row.iq_sha256)
    if cutoff is None or len(hashes) != inventory["window_count"]:
        raise ValueError("The signed index does not cover the full recording and original cutoff")
    return dict(schema=AUTHORITY_SCHEMA, recording=str(args.recording), session_id=session,
                inventory_sha256=digest, raw_authority_sha256=raw_authority(digest, hashes),
                window_count=len(hashes), causal_cutoff_utc_ns=cutoff, archive_sha256=archive_digest(args.archive, cutoff),
                region_sha256=tagged_bytes(args.region.read_bytes()))


def match_inventory(authority, session, digest, inventory):
    if (session, digest, inventory["window_count"]) != (
            authority["session_id"], authority["inventory_sha256"], authority["window_count"]):
        raise ValueError("The actual recording inventory does not match the detached authority")


def match_native(authority, native):
    source = native["source"]
    if (source["session_id"] != authority["session_id"]
            or source["input_manifest_sha256"] != authority["inventory_sha256"]
            or source["raw_recording_authority_digest"] != authority["raw_authority_sha256"]
            or native["clock_anchor"]["before"]["realtime_ns"] != authority["causal_cutoff_utc_ns"]):
        raise ValueError("Completed original acquisition does not bind the signed clock and source")


def paths_for(args, assets):
    roots = (args.recording, args.archive)

    def allowed(path, *, root=None):
        observed = direct(path)
        if root is None:
            if observed not in {*roots, *assets, args.bulk_root.parent}:
                raise ValueError(f"Input lies outside the approved original build/request: {path}")
        elif (root not in {*roots, *(entry.parent for entry in assets)}
              or not observed.is_relative_to(root) or observed.stat().st_dev != root.stat().st_dev):
            raise ValueError(f"Input escaped its original or build scope: {path}")
        return observed

    def guard(event, call):
        if event != "open" or not isinstance(call[0], (str, bytes)):
            return
        path = Path(os.path.abspath(os.fsdecode(call[0])))
        writes = bool(call[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
        held = args.bulk_root.with_name(args.bulk_root.name + "-held-anchor-route.json")
        if (path.is_relative_to(QNAP)
                or writes and (any(path.is_relative_to(root) for root in roots) or path in assets)
                or path.is_relative_to(BULK) and not (path in assets or path == args.region
                    or path in (args.build, args.authority) or path == held or path.is_relative_to(args.bulk_root)
                    or any(path.is_relative_to(root) for root in roots))):
            raise ValueError(f"Open outside the signed original-file request: {path}")

    return allowed, guard


def original_argv(args, book, authority):
    argv = [str(HERE / "integrated_original_entry.py"), "--recording", str(args.recording),
            "--archive", str(args.archive), "--region", str(args.region), "--output", str(args.bulk_root),
            "--archive-sha256", authority["archive_sha256"], *FLAGS]
    for flag in (*PATH_OPTIONS, *SIGNED_OPTIONS):
        entry = book["native"][flag]
        argv.extend((flag, entry["path"]))
        if flag in SIGNED_OPTIONS:
            argv.extend((flag + "-sha256", tagged(entry["sha256"])))
    argv.extend(("--portable-orbit-producer-sha256", tagged(book["portable_producer"]["sha256"])[7:]))
    return argv


def run(args, authority, region_bytes, book, assets, producer_cutoff):
    import empty_bootstrap as boot
    import exact_named_raw as raw
    import integrated_original_entry as charted

    original_staged, original_portable = boot.staged_scanner, raw.portable_binding
    eligible = producer_cutoff < authority["causal_cutoff_utc_ns"]
    allowed, guard = paths_for(args, assets)
    parsed_region = None
    snapshots = [] if getattr(args, "reuse_prefetched_snapshots", False) else None
    sys.addaudithook(guard)

    def staged(*call, **options):
        nonlocal parsed_region
        scan = original_staged(*call, **options)
        if options.get("detector") is not None:
            from leo.storage.fast_scan import FastScanStore

            if archive_digest(args.archive, authority["causal_cutoff_utc_ns"]) != authority["archive_sha256"]:
                raise ValueError("Causal archive roster differs from the externally signed request")
            parsed_region = scan.Algo08Region.parse(json.loads(region_bytes)).document()
            # Enforce the manifest identity at the normal scanner entrance, before any payload read.
            base = scan.FastScanStore

            class CheckedInventory(FastScanStore):
                def inventory(self, recording, *, verify_windows=True):
                    result = base.inventory(self, recording, verify_windows=verify_windows)
                    match_inventory(authority, *result)
                    return result

            scan.FastScanStore = CheckedInventory
            acquire = scan.acquire

            def checked_acquire(session, digest, inventory, scan_assets):
                match_inventory(authority, session, digest, inventory)
                native = acquire(session, digest, inventory, scan_assets)
                match_native(authority, native)
                return native

            scan.acquire = checked_acquire
        return scan

    def portable(config, cutoff):
        if cutoff != authority["causal_cutoff_utc_ns"]:
            raise ValueError("Solver cutoff differs from the signed capture")
        return original_portable(config, cutoff) if eligible else None

    with ExitStack() as scope:
        if snapshots is not None:
            loaded = boot.load_runtime

            def load_with_snapshots():
                runtime = loaded()
                import combined_frontier_run as frontier
                from reports.ALGO08.v3.prefetch_snapshots import binding

                scope.enter_context(binding(frontier, snapshots))
                return runtime

            scope.enter_context(patch.object(boot, "load_runtime", load_with_snapshots))
        scope.enter_context(patch.object(boot, "staged_scanner", staged))
        scope.enter_context(patch.object(raw, "staged_path", allowed))
        scope.enter_context(patch.object(raw, "deny_backing", lambda _: guard))
        scope.enter_context(patch.object(raw, "portable_binding", portable))
        scope.enter_context(patch.object(charted, "PNG_LIBRARY", Path(book["png"]["path"])))
        scope.enter_context(patch.object(sys, "argv", original_argv(args, book, authority)))
        charted.main()

    witness = json.loads((args.bulk_root / "unified-short-bootstrap.json").read_bytes())
    verified = json.loads((args.bulk_root / "legacy-original-acquisition.json").read_bytes())["verified_source"]
    receipt = witness["receipt"]
    if (verified != dict(session=authority["session_id"], raw_authority=authority["raw_authority_sha256"],
                         inventory=authority["inventory_sha256"], windows=authority["window_count"])
            or witness["requested_offer_sha256"] != authority["region_sha256"][7:]
            or receipt["region"] != parsed_region or receipt["decision"] not in ("complete", "withheld")):
        raise ValueError("The original publication did not preserve the approved acquisition and region")
    run_id = receipt["run_id"]
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_id) or run_id in (".", ".."):
        raise ValueError("Invalid standard run identifier")
    terminal = args.bulk_root / "fast-scan-automatic-work" / run_id / "terminal.json"
    checked(terminal, receipt["terminal_sha256"])
    if snapshots is not None:
        if len(snapshots) != 1:
            raise ValueError("Expected one scoped private snapshot producer")
        sources = {name: book["sources"][str((HERE / name).relative_to(ROOT))] for name in SNAPSHOT_SOURCES}
        write(args.bulk_root / "prefetch-snapshots.json", dict(slots=snapshots[0], source_sha256=sources,
              native_sha256=witness["native_sha256"], statistics=witness["prefetch"]))
    marker = dict(schema=RELEASE_SCHEMA, build_sha256=args.build_sha256, authority_sha256=args.authority_sha256,
                  archive_sha256=authority["archive_sha256"], session_id=receipt["session_id"], run_id=run_id,
                  terminal_sha256=receipt["terminal_sha256"], decision=receipt["decision"],
                  portable_dispatch="eligible" if eligible else "ordinary_cold_preparation", receipt=receipt)
    write(args.bulk_root / RELEASE_FILE, marker)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("recording", "archive", "region", "bulk-root", "authority", "build"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--authority-sha256")
    parser.add_argument("--build-sha256")
    parser.add_argument("--reuse-prefetched-snapshots", action="store_true",
                        help="Research-only private lookahead buffers, requiring separately pinned source")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--verify", action="store_true")
    actions.add_argument("--preflight", action="store_true")
    actions.add_argument("--prepare-authority", type=Path)
    actions.add_argument("--freeze-build-from-chart", type=Path)
    args = parser.parse_args(argv)

    if args.freeze_build_from_chart:
        if args.build is None:
            parser.error("supply --build for the new build manifest")
        write(args.build, make_build(args.freeze_build_from_chart,
                                    reuse_prefetched_snapshots=args.reuse_prefetched_snapshots))
        print(tagged_bytes(args.build.read_bytes()))
        return
    if not args.verify and not all((args.recording, args.archive, args.region, args.bulk_root)):
        parser.error("supply --recording, --archive, --region and a fresh --bulk-root")
    if args.prepare_authority:
        add_metadata_guard()
        write(args.prepare_authority, generate_authority(args))
        print(tagged_bytes(args.prepare_authority.read_bytes()))
        return
    if not args.build or not args.build_sha256:
        parser.error("supply the frozen --build and --build-sha256")
    book, assets, cutoff = load_build(args.build, args.build_sha256,
                                      reuse_prefetched_snapshots=args.reuse_prefetched_snapshots)
    if args.verify:
        print(json.dumps(dict(schema=BUILD_SCHEMA, charted_commit=CHARTED_COMMIT, build_sha256=args.build_sha256)))
        return
    if not args.authority or not args.authority_sha256:
        parser.error("supply --authority and --authority-sha256 with the original request")
    verify_paths(args)
    authority = document(args.authority, args.authority_sha256)
    region_bytes = validate_case(authority, args)
    if args.preflight:
        add_metadata_guard()
        if generate_authority(args) != authority:
            raise ValueError("Ordinary signed metadata differs from the detached authority")
        print(json.dumps(dict(preflight="ready", session_id=authority["session_id"], waveform_opens=0)))
        return
    if len(os.sched_getaffinity(0)) != 1:
        raise ValueError("Start the reference and charted candidate on one CPU")
    for name in THREADS:
        os.environ[name] = "1"
    print(json.dumps(run(args, authority, region_bytes, book, assets, cutoff)))


def add_metadata_guard():
    def no_samples(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).absolute()
            if path.name.endswith(WAVEFORM_SUFFIX) or path.is_relative_to(QNAP):
                raise ValueError("Metadata admission cannot open original waveform bytes or QNAP")

    sys.addaudithook(no_samples)


if __name__ == "__main__":
    main()
