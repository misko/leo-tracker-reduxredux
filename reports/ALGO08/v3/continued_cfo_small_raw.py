"""Pair installed and continued-CFO publication on the complete DS30-0107 recording."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import resource
import sys
from time import perf_counter, process_time, sleep


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from raw_0016_best_trial import FLAGS, PairInputs, PROJECTION, PROJECTION_SHA, frozen_sources, measure_mode
from short_raw_0180 import BULK, OPERATOR_OFFER, SHORT, STAGED, Workload, enrollment


BASE = "250c07d0c86eed9c227003bb9e151726de7dee72"
CASE = Workload("DS30-0107", BULK / "leo-dev/ds30-full-20261121/bindings/DS30-0107.json",
                "bb31fb4b47619f5e6e71ac46a6587d1194f4a68da2c0eeacf43f0610648de7ae",
                29, 51, 33_519_983, 85_000_000, ("stock", "candidate"))
ROSTER = "7e8426bb2a3afc06894f1ba410ee0489e7fc5f67e8bdbac5ec09aa32fc69f0f7"
INPUTS = PairInputs(CASE, 1, 27, 1794702096144017710,
                    "sha256:4c05fc0cbe26fcae1c42a85417b4ba20be683f1c8ea0b3fce0eb7a5c273f473d",
                    "sha256:056baef0073d49b8b02e3258eb6608d341ad6e1c41d5a8339c15834d82dd5665")
RECORDING = BULK / "leo/fast-scan-recordings/fast8-auto-20261115-002130-7ec6871a-1-upper"
ROUTE_FLAGS = (*FLAGS, "--prove-no-active-curvature", "--withhold-empty-family-calibration")
REFINER = Path("/dev/shm/leo-v3-short-cfo-held01/build/tail.so")
MB = 1024**2
PACE = 4 * MB


def enroll(rows):
    """Apply the predeclared length rule, then the approved nearest-lower exception."""
    ordered = sorted(rows)
    if len(ordered) != 455 or len({row[1] for row in ordered}) != len(ordered):
        raise ValueError("Expected the complete unique signed roster")
    if any(32 <= issued <= 64 for issued, _, _ in ordered):
        raise ValueError("The approved nearest-lower exception no longer applies")
    excluded = {"DS30-0227", "DS30-0180", "DS30-0102"}
    shorter = [row for row in ordered if row[0] < 32 and row[1] not in excluded]
    chosen = min(shorter, key=lambda row: (-row[0], row[1]))
    if chosen != (CASE.windows, CASE.id, CASE.binding_sha):
        raise ValueError("The selected signed cohort changed")
    return dict(rule="nearest issued count below 32 after empty 32–64 cohort; label breaks ties",
                eligible=[chosen], excluded=sorted(excluded),
                nearest_above=[row for row in ordered if 65 <= row[0] <= 124], count=len(ordered))


def selection():
    rows = []
    for path in CASE.binding.parent.glob("DS30-*.json"):
        data = path.read_bytes()
        case = json.loads(data)["case"]
        if case["id"] != path.stem:
            raise ValueError("Signed label differs from its manifest filename")
        rows.append((case["recording"]["window_count"], case["id"], sha256(data).hexdigest()))
    digest = sha256(json.dumps(sorted(rows), separators=(",", ":")).encode()).hexdigest()
    if digest != ROSTER:
        raise ValueError("Original roster bytes differ from the prospective census")
    return enroll(rows) | {"roster_sha256": digest, "outcomes_consulted": False}


def capacity(payload, index, manifest):
    if (payload != CASE.compressed_bytes or index != 78_609 or manifest != 3_542
            or 2 * payload > CASE.raw_limit or payload + index + manifest > CASE.raw_limit):
        raise ValueError("Complete original exceeds or changes the enrolled physical extent")


def copy_verified(source, destination, size, digest, *, bytes_per_second=None):
    """Read a signed body once, stopping at its size bound and pacing each block."""
    check, copied = sha256(), 0
    with source.open("rb") as incoming, destination.open("xb") as outgoing:
        if os.fstat(incoming.fileno()).st_size != size:
            raise ValueError(f"Signed source size changed: {source}")
        if bytes_per_second is not None:
            os.posix_fadvise(incoming.fileno(), 0, size, os.POSIX_FADV_RANDOM)
        start = perf_counter()
        while copied < size:
            block = incoming.read(min(MB, size - copied))
            if not block:
                raise ValueError(f"Signed source ended early: {source}")
            outgoing.write(block)
            check.update(block)
            copied += len(block)
            if bytes_per_second is not None:
                sleep(max(0, start + copied / bytes_per_second - perf_counter()))
    if check.hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"Signed source digest changed: {source}")
    return copied


def input_inventory():
    from leo.storage.fast_scan import FastScanStore
    from leo.storage.short_window import ShortWindowReader

    session, digest, inventory = FastScanStore(Path("/dev/shm")).inventory(RECORDING, verify_windows=False)
    segment, = inventory["segments"]
    folder = Path(segment["path"])
    reader = ShortWindowReader(folder)
    chunk, = reader.manifest.chunks
    manifest = folder / "manifest.json"
    if ((session, digest, inventory["window_count"], chunk.window_count) !=
            ("fast-" + INPUTS.inventory[7:39], INPUTS.inventory, CASE.windows, CASE.windows)
            or reader.manifest_sha256 != segment["manifest_digest"]):
        raise ValueError("Expected the complete original signed inventory")
    members = {
        "payload": (folder / chunk.payload_relative_path, chunk.compressed_bytes, chunk.compressed_sha256),
        "index": (folder / chunk.index_relative_path, chunk.index_bytes, chunk.index_sha256),
        "manifest": (manifest, manifest.stat().st_size, reader.manifest_sha256),
    }
    capacity(*(entry[1] for entry in members.values()))
    return session, members


def residency(members):
    from empty_bootstrap import checked
    from short_raw_diagnostic import CACHE_LIB, CACHE_SHA, cache_residency

    checked(CACHE_LIB, CACHE_SHA)
    query = cache_residency.load_query(CACHE_LIB)
    page = os.sysconf("SC_PAGE_SIZE")
    return {label: cache_residency.cache_snapshot([(path.parent, path.name, size)], page, query)
            for label, (path, size, _) in members.items() if label != "manifest"}


def stage_catalogue(root, names, cutoff):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    if (canonical_digest(names) != INPUTS.archive
            or any(Path(name).name != name or int(name.split("-", 1)[0]) >= cutoff for name in names)):
        raise ValueError("Signed causal catalogue membership changed")
    wanted = set(names.values())
    available = defaultdict(list)
    for folder in sorted(Path("/dev/shm").glob("*/tle/archive/space-track")):
        for path in sorted(folder.glob("*.tle")):
            digest = path.stem.rsplit("-", 1)[-1]
            if digest in wanted and path.resolve(strict=True).is_relative_to("/dev/shm"):
                available[digest].append(path)
    if set(available) != wanted:
        raise ValueError("All causal TLE bytes must come from existing tmpfs copies")
    preferred = Path("/dev/shm/leo-v3-graph-time-transfer-0102-pair01/tle")
    donors = {digest: min(paths, key=lambda path: (not path.is_relative_to(preferred), path))
              for digest, paths in available.items()}
    unique_bytes = sum(path.stat().st_size for path in donors.values())
    if len(donors) != 29 or len(names) != 51 or unique_bytes != 51_836_455:
        raise ValueError("Causal content census changed")
    destination = root / "tle/archive/space-track"
    destination.mkdir(parents=True)
    written = {}
    for name, digest in sorted(names.items()):
        target = destination / name
        if digest in written:
            target.hardlink_to(written[digest])
        else:
            donor = donors[digest]
            copy_verified(donor, target, donor.stat().st_size, digest)
            written[digest] = target
    if archive_identity(root / "tle")["snapshots_sha256"] != INPUTS.archive:
        raise ValueError("Staging changed the original catalogue identity")
    return dict(sha256=INPUTS.archive, names=len(names), unique=len(donors),
                tmpfs_unique_bytes=unique_bytes, original_body_bytes=0)


def stage(root):
    from aperture_trial import write
    from combined_frontier_run import BLOCK_SHA
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import REGION_SHA
    from full_short_run import GEOGRAPHIC_SHA, SHORT_SHA, TRACK_SCORES_SHA
    from short_cfo_raw import LIBRARY_SHA256
    from short_raw_diagnostic import pairs

    machine = host()
    binding, request = enrollment(CASE)
    case, job = binding["case"], request["job"]
    selection_document = selection()
    session, members = input_inventory()
    asserted = tuple((BULK / value["path"], "sha256:" + value["sha256"]) for value in case["recording"]["segments"])
    offer_bytes = checked(OPERATOR_OFFER, REGION_SHA)
    offer = json.loads(offer_bytes)
    if (asserted != ((members["manifest"][0], members["manifest"][2]),)
            or case["session_id"] != session or binding["orbit_cutoff_ns"] != INPUTS.cutoff_ns
            or case["valid_visits"] != INPUTS.admitted or job["evaluation_reference"] is not None
            or offer["center"] != job["search_center"] or offer["screen_center"] != job["screen_center"]):
        raise ValueError("Signed input or original operator offer changed")
    root.mkdir(mode=0o750)
    (root / "tmp").mkdir()
    (root / "offer.json").write_bytes(offer_bytes)
    named = pairs.verified_v3(pairs.NAMED_V3)
    sources = frozen_sources(BASE, ("continued_cfo.py", "short_cfo_raw.py", "held_cycle_refined.py",
                                    "anchor_cycle_route.py", "empty_family_calibration.py"))
    libraries = (
        ("short", SHORT, SHORT_SHA), ("geographic", STAGED / "geographic_library.so", GEOGRAPHIC_SHA),
        ("regional", STAGED / "regional_track_library.so", TRACK_SCORES_SHA),
        ("block", STAGED / "frontier_block_library.so", BLOCK_SHA),
        ("projection", PROJECTION, PROJECTION_SHA), ("refiner", REFINER, LIBRARY_SHA256),
    )
    for label, source, digest in libraries:
        (root / f"{label}.so").write_bytes(checked(source, digest))
    archive = stage_catalogue(root, request["causal_snapshots"], INPUTS.cutoff_ns)
    before = residency(members)
    pressure = Path("/proc/pressure/io")
    pressure_at_read = pressure.read_text()
    staged = root / RECORDING.name
    if staged.parent.stat().st_dev != Path("/dev/shm").stat().st_dev:
        raise ValueError("The target must be in the existing tmpfs")
    (staged / members["manifest"][0].parent.name).mkdir(parents=True)
    start, cpu = perf_counter(), process_time()
    blocks = resource.getrusage(resource.RUSAGE_SELF).ru_inblock
    copied = {}
    for label, (source, size, digest) in members.items():
        destination = staged / source.relative_to(RECORDING)
        copied[label] = copy_verified(source, destination, size, digest, bytes_per_second=PACE)
    paid = dict(copied=copied, pace_bytes_per_s=PACE, input_blocks=resource.getrusage(resource.RUSAGE_SELF).ru_inblock-blocks,
                elapsed_s=perf_counter()-start, cpu_s=process_time()-cpu, before=before, after=residency(members),
                pressure_before=pressure_at_read, pressure_after=pressure.read_text(), original_copy_passes=1)
    write(root / "admission.json", dict(case=CASE.id, selection=selection_document, order=CASE.order, machine=machine,
          named=named, sources=sources, driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          route_flags=ROUTE_FLAGS, raw_authority=case["raw_authority"], session=session, inventory=INPUTS.inventory,
          cutoff_utc_ns=INPUTS.cutoff_ns, offer_sha256=REGION_SHA, offer=offer, archive=archive,
          members={label: dict(path=str(path), bytes=size, sha256=digest) for label, (path,size,digest) in members.items()},
          staging=paid, library_sha256={label: pin for label, _, pin in libraries}))


def command(mode, root, named, python):
    common = ["--recording", RECORDING, "--archive", root / "tle", "--region", root / "offer.json"]
    if mode == "stock":
        return [named, *common, "--bulk-root", root / mode]
    if mode != "candidate":
        raise ValueError("Expected one child per registered arm")
    return [python, "-IB", __file__, "child", root, *common, "--output", root / mode,
            "--short-binary", root / "short.so", "--geographic-library", root / "geographic.so",
            "--regional-track-library", root / "regional.so", "--frontier-block-library", root / "block.so",
            "--grid-feature-projection-library", root / "projection.so", *ROUTE_FLAGS]


def prediction_seal(root):
    paths = [root / name for name in ("admission.json", "offer.json", "candidate-held-cycle-refined.json")]
    for mode in CASE.order:
        paths.extend(root / f"{mode}{suffix}" for suffix in ("-clock.json", ".stdout", ".stderr"))
        paths.extend(path for path in (root / mode).rglob("*") if path.is_file())
    return {str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def launch(root):
    from aperture_trial import read, write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE
    from full_short_physical import environment
    from short_raw_diagnostic import pairs, require_warm

    host()
    admission = read(root / "admission.json")
    staged = root / RECORDING.name
    if (not os.path.ismount(RECORDING) or os.stat(RECORDING)[:2] != os.stat(staged)[:2]
            or not os.statvfs(RECORDING).f_flag & os.ST_RDONLY):
        raise ValueError("Expected private read-only bind of the exact staged original path")
    session, members = input_inventory()
    if session != admission["session"]:
        raise ValueError("Staging changed the original path-based session")

    def resident():
        scopes = residency(members)
        for cache in scopes.values():
            require_warm(cache)
        return scopes["payload"] | {"index_cache": scopes["index"]}

    env = environment(root)
    env.update(TMPDIR=str(root / "tmp"), XDG_CACHE_HOME=str(root / "tmp"))
    python = RELEASE / "venv/bin/python"
    for mode in CASE.order:
        argv = command(mode, root, pairs.NAMED_V3, python)
        measure_mode(root, mode, argv, env, resident, require_success=False)
    write(root / "prediction-seal.json", prediction_seal(root))


def score(root, receipt):
    from aperture_trial import read, write
    from leo.contracts.digests import canonical_digest
    from raw_0016_best_score import process_rows
    from triage_bounds import calibration_comparison

    seal = root / "prediction-seal.json"
    if read(seal) != prediction_seal(root):
        raise ValueError("Raw results changed before geographic scoring")
    admission = read(root / "admission.json")
    candidate = read(root / "candidate/unified-short-bootstrap.json")
    route = candidate["held_anchor_route"]
    recipe = candidate["receiver_recipe"]
    pin = canonical_digest(recipe)
    if (recipe["continued_cfo"]["wrapper_sha256"] != admission["sources"]["continued_cfo.py"]
            or pin != candidate["detector_recipe_sha256"] or pin != route["selected_recipe_sha256"]
            or candidate["native_sha256"] != route["selected_native_sha256"]):
        raise ValueError("Published candidate is not the exact continued fixed-epoch route")
    runs = process_rows(root, admission, INPUTS, candidate_recipe=pin[7:])
    if (runs["stock"]["opportunities"] != runs["candidate"]["opportunities"]
            or runs["stock"]["process"]["clock"]["started_unix_ns"] >= runs["candidate"]["process"]["clock"]["started_unix_ns"]):
        raise ValueError("The quantitative pair changed original acquisition opportunities or launch order")
    results = calibration_comparison({k: row["science"] for k, row in runs.items()}, CASE.id)
    write(receipt, dict(case=CASE.id, base=BASE, admission=admission, runs=runs, calibrations=results,
                        prediction_seal_sha256=sha256(seal.read_bytes()).hexdigest(),
                        end_to_end=True, candidate_detector="exact continued_cfo.raw_entry"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("mode", choices=("stage", "launch", "score", "child"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--receipt", type=Path)
    arguments, inherited = parser.parse_known_args()
    if arguments.mode == "child":
        from continued_cfo import raw_entry

        raw_entry(arguments.root / "refiner.so", inherited)
    elif inherited:
        parser.error(f"Unexpected arguments {inherited}")
    elif arguments.mode == "stage":
        stage(arguments.root)
    elif arguments.mode == "launch":
        launch(arguments.root)
    elif arguments.receipt:
        score(arguments.root, arguments.receipt)
    else:
        parser.error("Scoring requires --receipt")
