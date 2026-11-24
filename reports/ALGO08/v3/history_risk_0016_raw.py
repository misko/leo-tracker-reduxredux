"""Measure the genuine history-risk and named CLIs on an already staged DS30-0016."""

import argparse
from contextlib import contextmanager
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from time import perf_counter


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
TMPFS = Path("/dev/shm")
STAGE = TMPFS/"leo-v3-guarded-selective-0016-stage01"
BACKING = Path("/srv/bulk/leo/fast-scan-recordings")
RECORDING = BACKING/"fast8-auto-20261113-112146-b04f5461-1-lower"
MEASUREMENTS = HERE/"measurements"
STOPPED = ("guarded-cfo-0016-stopped-stage.json.gz", "8271a2d880a00db4e118a536df20c126ade2ed5e80a69fa79b0e67760933c3d1")
NAMED = ("raw-0016-best.json.gz", "33d6cab032ab19f6093d57d6017be32820d479e5e96c082a21b40d4ea75824c0")
SAVED = ("history-risk-weak-physical.json.gz", "5407b1ab9ad0bbc167b5556a526d1686a568ae0e422b800ae9dd56888a89fb9d")
LIBRARIES = ("eight-ms-native-live.json.gz", "2604afe118cebc24fa4fb0a975a439e5a6e9c2858ca4ae793dbc5b7f7afe7b9d")
ORDER = ("candidate", "stock")
ISSUED, ADMITTED = 808, 713
WAVEFORM_BYTES, SIGNED_BYTES = 991_734_597, 993_933_681
ARM_NAMES = ("c0", "fitted_c")
ADAPTERS = ("reports/ALGO08/v3/exact_named_raw.py", "reports/ALGO08/v3/unified_short_bootstrap.py")
STAGING_LOCK = TMPFS/"leo-v3-guarded-selective-0016-staging.lock"
SAVED_SIDE_CAR_SCIENCE = {"grid": "sha256:8d2ac3a5f76abd886901e3c81d4f42e8270b438dcc5b453c1af8e710356b64a3",
                          "path": "sha256:ce942344219c7cab8c1d287c8d831eff3805e1e5925aa87ae8c2b1cb8976f3a4"}


def pinned_archive(binding, *, decoded_pin=False):
    name, pin = binding
    encoded = (MEASUREMENTS/name).read_bytes()
    body = gzip.decompress(encoded) if decoded_pin else encoded
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"Local reference seal changed: {name}")
    return json.loads(body if decoded_pin else gzip.decompress(encoded))


def enrolled():
    signed = pinned_archive(STOPPED, decoded_pin=True)
    rows = signed["files"]
    if (signed["recording"] != str(RECORDING) or (signed["issued"], signed["admitted"]) != (ISSUED, ADMITTED)
            or len(rows) != 28 or len({row["relative"] for row in rows}) != len(rows)
            or sum(row["signed_bytes"] for row in rows) != SIGNED_BYTES
            or sum(row["signed_bytes"] for row in rows if row["kind"] == "payload") != WAVEFORM_BYTES):
        raise ValueError("The approved local custody manifest must cover the original complete recording")
    return signed


@contextmanager
def local_directory(path, anchor=TMPFS):
    """Open directory descriptors on the enrolled device without following symlinks."""
    suffix = path.relative_to(anchor)
    if any(part in (".", "..") for part in suffix.parts):
        raise ValueError("Expected a direct local path")
    options = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(anchor, options)
    try:
        device = os.fstat(fd).st_dev
        for part in suffix.parts:
            next_fd = os.open(part, options, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            if os.fstat(fd).st_dev != device:
                raise ValueError("Local staging path crossed a filesystem")
        yield fd, device
    finally:
        os.close(fd)


def inspect_extent(root_fd, device, row):
    relative = Path(row["relative"])
    if relative.is_absolute() or len(relative.parts) != 2 or ".." in relative.parts:
        raise ValueError("Expected two direct member path components")
    wanted = row["signed_bytes"]
    observed, identity = 0, None
    try:
        segment = os.open(relative.parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        try:
            metadata = os.stat(relative.name, dir_fd=segment, follow_symlinks=False)
            if (os.fstat(segment).st_dev != device or metadata.st_dev != device
                    or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1):
                raise ValueError("not a direct regular file on the staged filesystem")
            observed = metadata.st_size
            identity = [metadata.st_dev, metadata.st_ino, observed, metadata.st_mtime_ns, metadata.st_ctime_ns]
            state = "complete" if observed == wanted else "partial" if observed < wanted else "oversized"
        finally:
            os.close(segment)
    except FileNotFoundError:
        state = "missing"
    except (ValueError, OSError):
        state = "unsafe_or_unavailable"
    return dict(relative=row["relative"], kind=row["kind"], signed_bytes=wanted, observed_bytes=observed,
                missing_bytes=max(0, wanted-observed), state=state, identity=identity)


def readiness(stage, signed):
    if not stage.is_absolute() or not stage.is_relative_to(TMPFS) or stage == TMPFS:
        raise ValueError("Expected an existing local tmpfs custody root")
    try:
        with local_directory(stage/RECORDING.name, TMPFS) as (fd, device):
            rows = [inspect_extent(fd, device, row) for row in signed["files"]]
        with local_directory(stage, TMPFS) as (fd, device):
            try:
                receipt = os.stat("staging.json", dir_fd=fd, follow_symlinks=False)
                completion_receipt = stat.S_ISREG(receipt.st_mode) and receipt.st_dev == device and receipt.st_nlink == 1
            except FileNotFoundError:
                completion_receipt = False
    except FileNotFoundError:
        rows = [dict(relative=row["relative"], kind=row["kind"], signed_bytes=row["signed_bytes"],
                     missing_bytes=row["signed_bytes"], observed_bytes=0, state="missing", identity=None)
                for row in signed["files"]]
        completion_receipt = False
    except (OSError, ValueError) as error:
        return dict(ready=False, stage=str(stage), reason=str(error), missing_bytes=None, workers_started=0,
                    waveform_bytes_read=0, catalogue_body_bytes_read=0)
    extents_complete = all(row["state"] == "complete" for row in rows)
    totals = {kind: {key: sum(row[key] for row in rows if row["kind"] == kind)
                     for key in ("signed_bytes", "observed_bytes", "missing_bytes")}
              for kind in ("manifest", "index", "payload")}
    return dict(ready=extents_complete and completion_receipt, extents_complete=extents_complete,
                custody_receipt_present=completion_receipt, stage=str(stage), kind_totals=totals,
                expected_bytes=sum(row["signed_bytes"] for row in rows),
                staged_bytes=sum(row["observed_bytes"] for row in rows),
                missing_bytes=sum(row["missing_bytes"] for row in rows),
                complete_files=sum(row["state"] == "complete" for row in rows), files=rows,
                workers_started=0, waveform_bytes_read=0, catalogue_body_bytes_read=0, identity_check="extent_only")


def references():
    saved = pinned_archive(SAVED)["run"]
    request = saved["binding.json"]["value"]["request"]
    earlier = pinned_archive(NAMED)
    return request, earlier["admission"], earlier["original"]["stock"], saved["verified-result.json"]["value"]


def stage_files(signed):
    return {kind: [[str(RECORDING/row["relative"]), row["signed_bytes"], row["signed_sha256"]]
                   for row in signed["files"] if row["kind"] == kind] for kind in ("manifest", "index", "payload")}


def require_custody(stage, signed):
    with local_directory(stage, TMPFS) as (fd, device):
        member = os.open("staging.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(member, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_dev != device or info.st_nlink != 1
                    or not 0 < info.st_size <= 64_000):
                raise ValueError("Expected a direct completed custody receipt")
            data = stream.read(64_001)
    receipt = json.loads(data)
    files = stage_files(signed)
    extents = {kind: sum(size for _, size, _ in rows) for kind, rows in files.items()}
    if (receipt["recording"] != str(RECORDING) or receipt["inventory"] != signed["inventory_sha256"]
            or receipt["raw_authority"] != signed["raw_authority"] or receipt["files"] != files
            or receipt["extents"] != extents or receipt["copied_bytes"] != SIGNED_BYTES):
        raise ValueError("Completed custody receipt does not bind the whole original stage")
    return sha256(data).hexdigest()


def authenticate_sidecars(stage, signed):
    from empty_bootstrap import checked

    recording = stage/RECORDING.name
    manifests = {Path(row["relative"]).parts[0] for row in signed["files"] if row["kind"] == "manifest"}
    with local_directory(recording, TMPFS) as (fd, _):
        if set(os.listdir(fd)) != manifests:
            raise ValueError("The stage contains a different set of recording segments")
    for row in signed["files"]:
        if row["kind"] in ("manifest", "index"):
            checked(recording/row["relative"], row["signed_sha256"][7:])


def arguments(root, request, named, python, libraries):
    common = ["--recording", request["recording"], "--archive", request["archive"]["root"], "--region", request["region"]]
    flags = ("--short-binary", "--geographic-library", "--regional-track-library", "--frontier-block-library")
    assets = [item for flag in flags for item in (flag, libraries[flag]["path"])]
    return dict(candidate=["/usr/bin/timeout", "--kill-after=2s", "75s", str(python), "-IB", str(HERE/"exact_named_raw.py"),
                           *common, "--archive-sha256", request["archive"]["snapshots_sha256"], "--history-risk-route",
                           "--output", str(root/"candidate"), *assets],
                stock=[str(named), *common, "--bulk-root", str(root/"stock")])


def roster(root):
    paths = [root/"admission.json"]
    for mode in ORDER:
        paths.extend(root/f"{mode}{suffix}" for suffix in ("-clock.json", ".stdout", ".stderr"))
        paths.extend(path for path in (root/mode).rglob("*") if path.is_file())
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths) if path.is_file() and not path.is_symlink()}


def bundle_sha(checkout, names):
    from empty_bootstrap import checked

    for name, pin in names.items():
        checked(checkout/name, pin)


def frozen_sources(checkout, expected):
    science = {name: pin for name, pin in expected.items() if name not in ADAPTERS}
    bundle_sha(checkout, science)
    adapters = {name: sha256((checkout/name).read_bytes()).hexdigest() for name in ADAPTERS}
    return science, adapters


def route_options(argv):
    from exact_named_raw import parser

    args = parser().parse_args(argv[6:])
    required = ("history_risk_route", "eight_ms_native_history", "held_anchor_route", "prove_empty_graph",
                "prove_graph_time_support", "prove_no_active_curvature")
    disabled = ("strict_packed_eight", "packed_ci16_map", "portable_orbit_index", "full_anchor_primary_library",
                "one_pass_web_png", "direct_orbit_figures", "direct_residual_figures")
    settings = {name: bool(getattr(args, name, False)) for name in (*required, *disabled)}
    renderer = {name: value not in (None, False, "stock", "standard", "installed")
                for name, value in vars(args).items() if "cairo" in name}
    if not all(settings[name] for name in required) or any(settings[name] for name in disabled) or any(renderer.values()):
        raise ValueError("Expected the ordinary archive 20/8 history-risk and standard raster publication")
    return settings | renderer


def launch_ready(root, stage, signed, ready):
    from aperture_trial import write
    from dense_geographic_trial import host
    from eight_ms_0107_pair import verified_scope
    from eight_ms_south_transfer import environment_for
    from empty_bootstrap import RELEASE, checked
    from exact_named_raw import staged_path
    from guarded_cfo_0016_stage import cache_states, fully_resident
    from history_risk_weak_physical import FROZEN
    from leo.operations.tle_archive import TleArchiveReader
    from raw_0016_best_trial import measure_mode
    from short_raw_diagnostic import pairs

    started = perf_counter()
    machine = host()
    verified_scope(stage/RECORDING.name, RECORDING)
    staged_path(root.parent)
    custody = require_custody(stage, signed)
    authenticate_sidecars(stage, signed)
    request, admission, _, saved = references()
    if (request["recording"] != str(RECORDING) or request["inventory"] != signed["inventory_sha256"]
            or request["authority"] != signed["raw_authority"] or request["session"] != signed["session"]
            or request["archive"]["snapshots_sha256"] != admission["archive"]["sha256"]
            or request["offer_sha256"] != admission["offer_sha256"]):
        raise ValueError("The enrolled saved and full-20 cases have different signed authority")
    offer, archive = (staged_path(Path(path)) for path in (request["region"], request["archive"]["root"]))
    checked(offer, request["offer_sha256"])
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    if (len(refs) != admission["archive"]["snapshots"] or pairs.archive_identity(archive) != request["archive"]
            or any(ref.collected_utc_ns >= request["cutoff_utc_ns"] for ref in refs)):
        raise ValueError("Expected exactly the original causal catalogue")
    paths = [staged_path(ref.path, root=archive) for ref in refs]
    resident_rows = json.loads(subprocess.check_output(["fincore", "--json", "--bytes", "-o", "RES,SIZE", *paths]))["fincore"]
    if len(resident_rows) != len(refs) or any(item["res"] < item["size"] for item in resident_rows):
        raise ValueError("All original causal catalogue bodies must already be local and resident")
    pins, adapters = frozen_sources(HERE.parents[2], saved["scientific"]["source_sha256"] |
                                   {f"reports/ALGO08/v3/{name}": pin for name, pin in FROZEN.items()})
    all_libraries = pinned_archive(LIBRARIES)["raw_binding"]["libraries"]
    lib = {flag: all_libraries[flag] for flag in ("--short-binary", "--geographic-library",
                                                  "--regional-track-library", "--frontier-block-library")}
    for item in lib.values():
        checked(Path(item["path"]), item["sha256"])
    installed = pairs.verified_v3(pairs.NAMED_V3)
    if installed != admission["stock"]:
        raise ValueError("Installed v3 differs from the original full-20 control")
    commands = arguments(root, request, pairs.NAMED_V3, RELEASE/"venv/bin/python", lib)
    options = route_options(commands["candidate"])

    def resident():
        status = readiness(stage, signed)
        verified_scope(stage/RECORDING.name, RECORDING)
        if not status["ready"] or status["files"] != ready["files"]:
            raise ValueError("The enrolled stage changed before or during the pair")
        scopes = cache_states({kind: [(Path(path), size, pin) for path, size, pin in rows]
                               for kind, rows in stage_files(signed).items()})
        if not fully_resident(scopes):
            raise ValueError("The whole staged recording must remain resident")
        return scopes["payload"] | {"index_cache": scopes["index"]}

    resident()
    root.mkdir()
    (root/"tmp").mkdir()
    shutil.copytree(offer.parent/"fonts", root/"fonts")
    env = environment_for(root)
    help_text = subprocess.run([*commands["candidate"][:6], "--help"], check=True, timeout=10,
                               capture_output=True, env=env).stdout
    if b"--history-risk-route" not in help_text:
        raise ValueError("The isolated candidate parser is unavailable")
    write(root/"admission.json", dict(machine=machine, original=admission, request=request, order=ORDER, stock=installed,
         commands=commands, sources=pins, adapters=adapters, active_options=options, candidate_libraries=lib,
         driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), stage=ready, custody_sha256=custody,
         archive_before=dict(snapshots=len(refs), bytes=sum(item["size"] for item in resident_rows)),
         original_backing_bytes=0, conditioning_bytes=0, setup_wall_s=perf_counter()-started))
    try:
        for mode in ORDER:
            measure_mode(root, mode, commands[mode], env, resident, require_success=False)
    finally:
        write(root/"prediction-seal.json", roster(root))


def launch(root, stage, signed):
    # Refuse incomplete custody before importing either launcher or looking at the archive.
    ready = readiness(stage, signed)
    if not ready["ready"]:
        return ready
    from guarded_stage_checkpoint import staging_lock

    with staging_lock(STAGING_LOCK):
        ready = readiness(stage, signed)
        if not ready["ready"]:
            return ready
        launch_ready(root, stage, signed, ready)
    return None


def read(path):
    return json.loads(path.read_bytes())


def published(root, mode, log, request, stock, saved, *, adapters=None):
    from empty_bootstrap import bind_native, checked
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from raw_0016_best_score import STOCK_OWNERS, STOCK_OWNERS_SHA, position_sides
    from tools.pipeline_eval.qualification import paired_publication as pairs

    output = root/mode
    clock = log["clock"]
    terminal = json.loads(output.with_suffix(".stdout").read_text().splitlines()[-1])
    science = pairs.evidence(output, terminal, clock["started_unix_ns"], read_only=True)
    packet_path = native_packet(output)
    body = packet_path.read_bytes()
    native = json.loads(body)
    digest = "sha256:" + sha256(body).hexdigest()
    source, provenance = native["source"], native["provenance"]
    candidate = mode == "candidate"
    detector = request["detector"][7:] if candidate else pairs.V3_IDENTITY["detector_sha256"]
    bind_native(native, request["session"], request["inventory"], detector)
    if (canonical_digest(native) != digest or source["raw_recording_authority_digest"] != science["raw_authority"]
            or science["raw_authority"] != request["authority"]
            or native["clock_anchor"]["before"]["realtime_ns"] != request["cutoff_utc_ns"]
            or terminal["region"] != stock["science"]["receipt"]["region"] or terminal["session_id"] != request["session"]
            or terminal["window_count"] != ISSUED or terminal["counts"] != dict(processed=ADMITTED, invalid_capture=ISSUED-ADMITTED, skipped_fast_score=0)
            or len(source["probes"]) != 2*ADMITTED or set(science["arms"]) != set(ARM_NAMES)):
        raise ValueError("Publication does not bind the entire original physical comparison")
    witness, raw, owners = None, None, {}
    if candidate:
        raw = read(output/"unified-short-bootstrap.json")
        witness = read(output/"exact-named-raw-witness.json")
        enrolled_recipe = {key: value for key, value in saved["scientific"]["solver_recipe"].items() if key != "history_risk"}
        actual_recipe = {key: witness.get("solver_recipe", {}).get(key) for key in enrolled_recipe}
        if (raw["receipt"] != terminal or raw["native_sha256"] != digest or raw["raw_acquisitions"] != 1
                or raw["verified_handoffs"] != 1 or raw["requested_offer_sha256"] != request["offer_sha256"]
                or raw["archive_root"] != request["archive"]["root"] or raw["frozen_specification"] != pairs.V3_IDENTITY["frozen_specification"]
                or raw["stock_launcher_sha256"] != pairs.V3_LAUNCHER_SHA or raw["scientific_imports_before"]
                or raw.get("packed_ci16_input") is not None
                or terminal["decision"] == "complete" and (raw["route"] != "history_risk_installed"
                    or actual_recipe != enrolled_recipe or not witness["solver_recipe"]["history_risk"]["requested"]
                    or witness["source_sha256"].get(ADAPTERS[0]) != (adapters or {}).get(ADAPTERS[0]))):
            raise ValueError("The candidate did not traverse its enrolled signed raw CLI")
        owners = witness["evidence"]["owner_rows"]
    else:
        pairs.verify_v3_publication(output, terminal)
        if terminal["decision"] == "complete" and stock["science"]["receipt"]["terminal_sha256"] == terminal["terminal_sha256"]:
            original = json.loads(checked(STOCK_OWNERS, STOCK_OWNERS_SHA))
            if original["receipt"]["terminal_sha256"] != terminal["terminal_sha256"]:
                raise ValueError("Archived ordered owners do not bind the actual named terminal")
            owners = original["selected_rows"]
    media = artifacts(output, terminal)
    store = FastStandardAnalysisStore(output)
    detail = store.detail(terminal["run_id"])
    complete = terminal["decision"] == "complete"
    sidecars = position_sides(store, terminal, media, expected_points=None) if complete else None
    if complete:
        if len(media["images"]) != 8 or not store.position_grid(terminal["run_id"])["matched_c_grid"]:
            raise ValueError("Expected all eight decoded figures and a complete matched c grid")
        if owners:
            for arm in ARM_NAMES:
                rows = owners[arm]
                mapped = {item[0]: item[1] for item in rows}
                if (len(rows) != len(mapped) or len(rows) != detail["arms"][arm]["associated_points"]
                        or canonical_digest(mapped) != science["owners"][arm]):
                    raise ValueError("Ordered owner rows differ from the official published owner digest")
    elif (media["images"] or detail["arms"] or any(x["latlon"] is not None for x in science["arms"].values())
          or store.position_path(terminal["run_id"]) is not None or store.position_grid(terminal["run_id"]) is not None
          or any(output.rglob("*.png"))):
        raise ValueError("A withheld original was accompanied by position products")
    opportunities = [{key: value for key, value in probe.items() if key != "candidates"} for probe in source["probes"]]
    older = saved["scientific"]["evidence"] if candidate else stock
    figure_reference = older["images"] if candidate else older["figures"]
    pngs = {name: all(item[key] == figure_reference.get(name, {}).get(key) for key in ("sha256", "rgba_sha256"))
            for name, item in media["images"].items()}
    previous_terminal = canonical_digest(saved["terminal"]) if candidate else stock["science"]["receipt"]["terminal_sha256"]
    if candidate and complete:
        sidecar_parity = {name: canonical_digest(getattr(store, "position_"+name)(terminal["run_id"])) == pin
                          for name, pin in older["sidecars"].items()}
    else:
        sidecar_parity = {name: media.get(name) == pin for name, pin in stock["full_sidecar_sha256"].items()} if complete else {}
    route_reference = saved["scientific"]["solver_recipe"]["history_risk"]
    actual_route = witness.get("solver_recipe", {}).get("history_risk", {}) if candidate else route_reference
    expected_sidecar_science = SAVED_SIDE_CAR_SCIENCE if candidate else stock["science"]["scientific_digests"]
    return dict(process=log, science=science, digest=digest, probes=len(opportunities),
                opportunities=canonical_digest(opportunities), excluded=provenance["excluded_windows"],
                factors=sum(len(row["candidates"]) for row in source["probes"]), sidecars=sidecars,
                figures=media["images"], png_parity=pngs, owners=owners, owner_counts={arm: info["associated_points"] for arm, info in detail["arms"].items()},
                all_owned_rf_rms_hz={arm: info["residual_rms_hz"] for arm, info in detail["arms"].items()},
                terminal_parity=terminal["terminal_sha256"] == previous_terminal,
                native_parity=digest == (request["native"] if candidate else stock["native_sha256"]),
                full_sidecar_record_parity=sidecar_parity,
                sidecar_science_parity=science["scientific_digests"] == expected_sidecar_science,
                reference_owner_parity=(owners == older["owner_rows"] if candidate else science["owners"] == stock["science"]["owners"]),
                route=witness["ports"] if witness else None,
                route_parity=all(actual_route.get(key) == value for key, value in route_reference.items()),
                phases=raw["phases"] if raw else None,
                detector_file_s=(packet_path.stat().st_mtime_ns-clock["started_unix_ns"])/1e9)


def score(root, output):
    from aperture_trial import write
    from eight_ms_held_score import owner_differences
    from triage_bounds import calibration_comparison

    sealed = root/"prediction-seal.json"
    if read(sealed) != roster(root):
        raise ValueError("The two output trees changed after launch")
    admission = read(root/"admission.json")
    request, original, stock, saved = references()
    if (admission["request"] != request or admission["original"] != original or tuple(admission["order"]) != ORDER
            or admission["driver_sha256"] != sha256(Path(__file__).read_bytes()).hexdigest()):
        raise ValueError("The paired admission file does not bind this benchmark")
    bundle_sha(HERE.parents[2], admission["sources"])
    bundle_sha(HERE.parents[2], admission["adapters"])
    if admission["active_options"] != route_options(admission["commands"]["candidate"]):
        raise ValueError("The recorded renderer and input options differ from the ordinary arm")
    logs = {mode: read(root/f"{mode}-clock.json") for mode in ORDER if (root/f"{mode}-clock.json").is_file()}
    if any(row["command"] != admission["commands"][mode] for mode, row in logs.items()):
        raise ValueError("Measured argv differs from the enrolled commands")
    runs = {mode: published(root, mode, row, request, stock, saved, adapters=admission["adapters"])
            for mode, row in logs.items() if row["clock"]["exit_code"] == 0}
    pair = len(runs) == 2
    same = (pair and runs["stock"]["opportunities"] == runs["candidate"]["opportunities"] == stock["opportunities"]
            and runs["stock"]["excluded"] == runs["candidate"]["excluded"]
            and logs["candidate"]["clock"]["started_unix_ns"] < logs["stock"]["clock"]["started_unix_ns"])
    owners = {arm: owner_differences(runs["stock"]["owners"][arm], runs["candidate"]["owners"][arm])
              for arm in ARM_NAMES} if pair and all(run["owners"] for run in runs.values()) else None
    ratio = {kind: logs["stock"]["clock"][kind]/logs["candidate"]["clock"][kind]
             for kind in ("elapsed_s", "cpu_s")} if same else None
    reference_parity = {mode: bool(run["native_parity"] and run["terminal_parity"] and run["reference_owner_parity"] and run["route_parity"]
                                   and run["sidecar_science_parity"]
                                   and run["sidecars"] and run["sidecars"]["grid_points"] == 179
                                   and len(run["png_parity"]) == 8 and all(run["png_parity"].values()))
                        for mode, run in runs.items()}
    write(output, dict(case="DS30-0016", admission=admission, runs=runs, measured_exits=logs, same_opportunities=same,
         owners=owners, reference_parity=reference_parity, qualified=same and all(reference_parity.values()),
         geographical_and_rf=calibration_comparison({mode: run["science"] for mode, run in runs.items()}, "DS30-0016"),
         ratio=ratio, saved_controls=dict(named_reference=NAMED[1], named_clock=stock["process"]["clock"],
             candidate_reference=SAVED[1], saved_worker_clock=saved["clock"], saved_route=saved["route"]),
         pre_score_sha256=sha256(sealed.read_bytes()).hexdigest()))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("ready", "launch", "score"))
    cli.add_argument("root", nargs="?", type=Path)
    cli.add_argument("--stage", type=Path, default=STAGE)
    cli.add_argument("--output", type=Path)
    args = cli.parse_args()
    if args.action == "score" and args.root is not None and args.output is not None:
        if args.output.resolve().is_relative_to(args.root.resolve()):
            cli.error("Scoring output must be outside the sealed pair")
        score(args.root, args.output)
        return 0
    if args.action == "ready" and args.root is None and args.output is None:
        status = readiness(args.stage, enrolled())
    elif args.action == "launch" and args.root is not None and args.output is None:
        status = launch(args.root, args.stage, enrolled())
        if status is None:
            return 0
    else:
        cli.error("Use ready, launch ROOT, or score ROOT --output FILE")
    print(json.dumps(status, indent=2, sort_keys=True), flush=True)
    return 0 if status["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
