"""Time a signed raw-to-publication ALGO08v3 bounds pair on Gauss."""
import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from time import time_ns
from types import SimpleNamespace

from leo.contracts.digests import canonical_digest
from leo.storage.fast_scan import FastScanStore, immutable_json
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from leo.storage.short_window import ShortWindowReader
from leo.storage.uri import confined_path
from PIL import Image
from tools.pipeline_eval.qualification import cache_residency, paired_publication
from tools.pipeline_eval.scoring import distance_km
from triage_successor import (
    BASELINE, CACHE, CACHE_SHA256, NUMERICAL_THREADS, checked, publication, read, witnesses,
)


CASE = "DS30-0008"
HERE = Path(__file__).resolve().parent
ASSIGNMENT = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/publications") / CASE / "pair.json"
ASSIGNMENT_SHA256 = "b2a0a7b73a245731ae2c21bdb3e44664a402397bb65cad6c42b66c8e2989b919"
REGION_SHA256 = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
REFERENCE = HERE.parent.parent / "2026_11_21_ds30_full/reference-audit.json"
REFERENCE_SHA256 = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
LAUNCHERS = {"baseline": BASELINE, "bounds": HERE / "run-bounds"}
WEAK_CASE = "DS30-0016"
WEAK_BINDING = Path("/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0016.json")
WEAK_BINDING_SHA256 = "c781d10abe126bdc40d75a6e202d09a7542e92ef932a535f42700fe95d9ac38c"
WEAK_ARCHIVE_SHA256 = "sha256:25bf630b8588a27a23f90de971041ce95b249ce5e1fd2f72144aa8b73945fafc"
WEAK_ARCHIVE_REQUEST_SHA256 = "c167f3c3d833cfe21fdb0baf2d05ab30cd8e4673ec8ef4b4f6fbda9f56474110"
WEAK_PRIOR_STOCK_NATIVE_SHA256 = "4c0e22cbc5646e059abf59e968df2ee9d971795204d552adc9223d2426a7a7e0"
BUILD_MANIFEST = HERE / "measurements/bounds-DS30-0008-build.json"
BUILD_MANIFEST_SHA256 = "c9ce9d8b2c1e562a9dd9e511f25427ee7071b5d5e36ab7303741fc361c123d6f"


def weak_assignment():
    binding = json.loads(checked(WEAK_BINDING, WEAK_BINDING_SHA256))["case"]
    release_region = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/station/region.json")
    bulk = Path("/srv/bulk")
    request = bulk / binding["request"]["path"]
    checked(request, WEAK_ARCHIVE_REQUEST_SHA256)
    segments = tuple((bulk / row["path"], "sha256:" + row["sha256"])
                     for row in binding["recording"]["segments"])
    prior = json.loads(checked(BUILD_MANIFEST, BUILD_MANIFEST_SHA256))
    expected_build = prior["candidate_build"]
    original_build = read(HERE / "measurements/bounds-DS30-0008-pair.json")["builds"]["baseline"]
    for name, item in prior["files"].items():
        checked(Path(prior["archive"]) / name, item["sha256"])
    assignment = dict(recording=str(segments[0][0].parents[1]), region=str(release_region),
                      archive=dict(root=str(request.parent / "tle"), snapshots_sha256=WEAK_ARCHIVE_SHA256),
                      cache_observation=dict(manifests=cache_residency.manifest_pins(segments)),
                      candidate_specification_digest=original_build["frozen_specification"],
                      candidate_specification=dict(detector_sha256=original_build["detector_sha256"]))
    witness = dict(session_id=binding["session_id"], raw_authority=binding["raw_authority"],
                   detection_file_sha256=WEAK_PRIOR_STOCK_NATIVE_SHA256)
    return assignment, witness, expected_build


def warm_recording(manifests):
    """Warm only the assigned compressed files via bounded read-only demand reads."""
    buffer = bytearray(1024 * 1024)
    for path, digest in manifests:
        reader = ShortWindowReader(path.parent)
        if reader.manifest_sha256 != digest:
            raise ValueError("Sealed recording manifest changed before warming")
        for chunk in reader.manifest.chunks:
            member = confined_path(reader.path, reader.path / chunk.payload_relative_path, must_exist=True)
            with member.open("rb", buffering=0) as stream:
                while stream.readinto(buffer):
                    pass


def require_full_cache(observation):
    # The previously verified DS30-0016 control had 13 members and 242,128 pages.
    if (observation["members"] != 13 or observation["observed_members"] != 13
            or observation["observed_file_pages"] != 242128 or observation["cached_pages"] != 242128
            or observation["unavailable"]):
        raise ValueError(f"DS30-0016 was not fully cached at launch: {observation}")


def pair_comparison(rows, natives, terminals):
    baseline, bounds = rows
    native_base, native_bounds = natives
    terminal_base, terminal_bounds = terminals
    figure_fields = ("pngs", "png_pixels")
    equality = {name: v == bounds[name] for name, v in baseline.items() if name not in figure_fields}
    for key in figure_fields:
        left, right = baseline.get(key, {}), bounds.get(key, {})
        equality[key] = {name: left.get(name) == right.get(name) for name in sorted(left.keys() | right.keys())}
    equality["ordered_probes"] = native_base["source"]["probes"] == native_bounds["source"]["probes"]
    equality["detection_document"] = native_base == native_bounds
    equality["terminal_document"] = terminal_base == terminal_bounds
    # A different detector changes its hash and the derived analysis digest and ID.
    # Compare all other fields, including counts and RF support, separately.
    def without_detector_identity(native):
        return native | {
            "source": {k: v for k, v in native["source"].items() if k != "analysis_manifest_sha256"},
            "provenance": {k: v for k, v in native["provenance"].items()
                           if k not in ("detector_sha256", "run_id")},
        }

    equality["detection_without_detector_identity"] = (
        without_detector_identity(native_base) == without_detector_identity(native_bounds)
    )
    equality["terminal_without_detection_digest"] = (
        {k: v for k, v in terminal_base.items() if k != "native_sha256"}
        == {k: v for k, v in terminal_bounds.items() if k != "native_sha256"}
    )
    return equality


def check_assignment(args, assignment):
    if paired_publication.archive_identity(args.archive) != assignment["archive"]:
        raise ValueError("Assigned causal archive changed")
    checked(args.region, REGION_SHA256)


def verify_launchers(args, assignment):
    controls = ["--recording", str(args.recording), "--archive", str(args.archive),
                "--region", str(args.region)]
    builds = {
        name: json.loads(subprocess.check_output([str(launcher), "--verify", *controls],
                                                 text=True, timeout=60))
        for name, launcher in LAUNCHERS.items()
    }
    if any(b["frozen_specification"] != assignment["candidate_specification_digest"]
           for b in builds.values()):
        raise ValueError("A launcher differs from the assigned ALGO08v3 build")
    if builds["baseline"]["detector_sha256"] != assignment["candidate_specification"]["detector_sha256"]:
        raise ValueError("The baseline detector differs from the assigned ALGO08v3 detector")
    return builds


def archived_witness(assignment, build):
    candidate = assignment["runs"]["candidate"]
    read_only = paired_publication.evidence(ASSIGNMENT.parent / "candidate", candidate["receipt"],
                                             started_ns=0, read_only=True)
    read_only.pop("terminal_file_s")
    if any(candidate[key] != value for key, value in read_only.items()):
        raise ValueError("Archived ALGO08v3 publication differs from its frozen receipt")
    return snapshot(ASSIGNMENT.parent / "candidate", candidate | {"build": build})[0]


def snapshot(root, run):
    native, terminal = publication(root, run)
    source = native["source"]
    analysis_digest = canonical_digest([
        "cancellation", source["raw_recording_authority_digest"], run["build"]["detector_sha256"], source["probes"],
    ])
    if (source["analysis_manifest_sha256"] != analysis_digest
            or native["provenance"]["run_id"] != "blind-compact-" + analysis_digest[7:39]):
        raise ValueError("Sealed analysis differs from its detector and ordered probes")
    native_path, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    run_id = run["receipt"]["run_id"]
    scans = FastScanStore(root)
    terminal_path = scans.automatic_workspace(run_id, create=False) / "terminal.json"
    standard = FastStandardAnalysisStore(root)
    detail = standard.detail(run_id)
    png_pixels = {}
    for item in run["artifacts"]:
        name = item["name"]
        data = standard.artifact(run_id, name, item["sha256"])
        with Image.open(BytesIO(data)) as image:
            pixels = image.convert("RGBA")
            png_pixels[name] = dict(width=pixels.width, height=pixels.height,
                                    rgba_sha256=sha256(pixels.tobytes()).hexdigest())
    witness = witnesses(run, native) | dict(
        detector_sha256=run["build"]["detector_sha256"], native_run_id=native["provenance"]["run_id"],
        publication_run_id=run_id, png_pixels=png_pixels,
        detection_file_sha256=sha256(native_path.read_bytes()).hexdigest(),
        terminal_file_sha256=sha256(terminal_path.read_bytes()).hexdigest(),
        scan_report_sha256=canonical_digest(scans.detail(run_id)),
        publication_detail_sha256=canonical_digest(detail),
        publication_detail_without_native_binding_sha256=canonical_digest({
            k: v for k, v in detail.items() if k not in ("input_sha256", "terminal_sha256")
        }),
    )
    return witness, native, terminal, native_path, terminal_path


def calibration_comparison(runs, case_id=CASE):
    audit = json.loads(checked(REFERENCE, REFERENCE_SHA256))
    case, = (case for case in audit["cases"] if case["dataset_label"] == case_id)
    if not case["authority_eligible"] or not case["sealed_metadata_digests_verified"]:
        raise ValueError("DS30 reference is ineligible")
    reference = [case["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    comparisons = {}
    for name, run in runs.items():
        arms = run["arms"]
        error = {arm: distance_km(reference, row["latlon"]) for arm, row in arms.items()}
        rms = {arm: row.get("rf_rms_hz") for arm, row in arms.items()}
        comparisons[name] = dict(horizontal_error_km=error, rf_rms_hz=rms)
        if all(v is not None for v in rms.values()):
            comparisons[name]["fitted_minus_c0_rf_rms_hz"] = rms["fitted_c"] - rms["c0"]
        if all(v is not None for v in error.values()):
            comparisons[name]["fitted_minus_c0_horizontal_error_km"] = error["fitted_c"] - error["c0"]
    return dict(reference_audit_sha256=REFERENCE_SHA256, authority_revision=case["authority_revision"],
                reference_evidence=case["evidence"], runs=comparisons)


def measure_pair(output, first, *, preflight=False, case=CASE):
    weak = case == WEAK_CASE
    if weak:
        assignment, archived, expected_build = weak_assignment()
    else:
        assignment = json.loads(checked(ASSIGNMENT, ASSIGNMENT_SHA256))
    checked(CACHE, CACHE_SHA256)
    args = SimpleNamespace(recording=Path(assignment["recording"]), region=Path(assignment["region"]),
                           archive=Path(assignment["archive"]["root"]), timeout=360)
    check_assignment(args, assignment)
    manifests = tuple((Path(row["path"]), row["sha256"]) for row in assignment["cache_observation"]["manifests"])
    os.environ.update({key: "1" for key in NUMERICAL_THREADS})
    builds = verify_launchers(args, assignment)
    if weak and builds["bounds"] != expected_build:
        raise ValueError("Weak arm differs from the archived original bounds build")
    if not weak:
        archived = archived_witness(assignment, builds["baseline"])
    query = cache_residency.load_query(CACHE)
    page_size = os.sysconf("SC_PAGE_SIZE")
    if preflight:
        cache = cache_residency.bound_snapshot(FastScanStore(output), args.recording, manifests, page_size, query)
        print(json.dumps(dict(case=case, builds=builds, archived_witness=archived, cache=cache)), flush=True)
        return

    output.mkdir()
    os.environ["MPLCONFIGDIR"] = str(output / "mplconfig")
    # Charge neither arm for creating the shared Matplotlib font cache.
    subprocess.run([sys.executable, "-c", "import matplotlib.font_manager"], check=True, timeout=60)
    store = FastScanStore(output)
    order = (first, "bounds" if first == "baseline" else "baseline")
    result = dict(case=case, order=order, recording=str(args.recording), archive=assignment["archive"],
                  assignment_sha256=WEAK_BINDING_SHA256 if weak else ASSIGNMENT_SHA256, archived_witness=archived,
                  region_file=str(args.region), region_file_sha256=REGION_SHA256,
                  driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), builds=builds,
                  cpu=sorted(os.sched_getaffinity(0)), nice=os.getpriority(os.PRIO_PROCESS, 0),
                  ionice=subprocess.check_output(["ionice", "-p", str(os.getpid())], text=True).strip(),
                  numerical_threads={key: os.environ[key] for key in NUMERICAL_THREADS},
                  cache=dict(method="linux-cachestat", library_sha256=CACHE_SHA256, page_size_bytes=page_size,
                             managed_cache=weak, arms={}), runs={})
    if weak:
        result["archive_request_sha256"] = WEAK_ARCHIVE_REQUEST_SHA256
        result["archived_build_manifest_sha256"] = BUILD_MANIFEST_SHA256
        result["cache"].update(conditioning="fully warm by demand read outside each timed arm, with no eviction",
                               before_conditioning={})
    natives, terminals = {}, {}
    try:
        for name in order:
            def observe_cache():
                observed = cache_residency.bound_snapshot(store, args.recording, manifests, page_size, query)
                if weak:
                    result["cache"]["before_conditioning"][name] = observed
                    if observed["cached_pages"] != observed["observed_file_pages"]:
                        warm_recording(manifests)
                        observed = cache_residency.bound_snapshot(store, args.recording, manifests, page_size, query)
                result["cache"]["arms"][name] = observed
                if weak:
                    require_full_cache(observed)

            print(f"Measuring {name} for {case}", flush=True)
            root = output / name
            started = time_ns()
            run = paired_publication.measure(LAUNCHERS[name], root, args, before_launch=observe_cache)
            result["runs"][name] = run
            run.update(build=builds[name], measurement_requested_unix_ns=started,
                       measurement_returned_unix_ns=time_ns())
            marker_name = "algo08v3-release.json" if name == "baseline" else "algo08v3-bounds.json"
            expected = builds[name] | {k: run["receipt"][k] for k in ("session_id", "decision")}
            if (read(root / marker_name) != expected
                    or (not weak and run["receipt"]["region"] != archived["region"])):
                raise ValueError("Measured build or region differs from the intended run")
            run["witnesses"], natives[name], terminals[name], native_path, terminal = snapshot(root, run)
            run["detection_file_s"] = run["terminal_file_s"] + (native_path.stat().st_mtime_ns
                                                                - terminal.stat().st_mtime_ns) / 1e9
            run["detection_to_terminal_s"] = run["terminal_file_s"] - run["detection_file_s"]
            run["terminal_to_exit_s"] = run["elapsed_s"] - run["terminal_file_s"]
        check_assignment(args, assignment)
        names = ("baseline", "bounds")
        baseline, bounds = (result["runs"][name] for name in names)
        result["archived_witness_equality"] = {k: value == baseline["witnesses"][k]
                                              for k, value in archived.items()}
        if weak and not all(result["archived_witness_equality"][key] for key in ("raw_authority", "session_id")):
            raise ValueError("Weak pair differs from its assigned signed raw recording")
        comparison = pair_comparison([baseline["witnesses"], bounds["witnesses"]],
                                     [natives[name] for name in names], [terminals[name] for name in names])
        result["equality"] = comparison
        hooks = bounds["receipt"].get("bounds_research", {})
        layout = hooks.get("tools.pipeline_eval.variants.algo08_incremental_layout", {})
        regional = hooks.get("tools.pipeline_eval.variants.experimental.regional_envelope_install", {})
        result["activation"] = dict(
            native_detector_changed=baseline["build"]["detector_sha256"] != bounds["build"]["detector_sha256"],
            reused_fixed_constructions=layout.get("reused_fixed_constructions", 0),
            rejected_fine_salvage_supports=sum(v.get("reject_supports", 0) for v in regional.get("solves", [])),
        )
        if not all(comparison[key] for key in ("raw_authority", "session_id", "input_manifest_sha256", "region")):
            raise ValueError("Pair used different authenticated waveform or geography")
        result["speedup"] = {key: baseline[key] / bounds[key] for key in ("elapsed_s", "cpu_s")}
        result["calibration_ablation"] = calibration_comparison(result["runs"], case)
    except Exception as error:
        result["failure"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        immutable_json(output / "pair.json", result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new directory for the pair and its receipt")
    parser.add_argument("--first", choices=tuple(LAUNCHERS), required=True)
    parser.add_argument("--case", choices=(CASE, WEAK_CASE), default=CASE)
    parser.add_argument("--preflight", action="store_true", help="verify without acquiring I/Q or writing a pair")
    args = parser.parse_args()
    print(f"Waiting for {paired_publication.LOCK}", flush=True)
    with paired_publication.single_core_slot(2):
        measure_pair(args.output.resolve(), args.first, preflight=args.preflight, case=args.case)
    if not args.preflight:
        print(args.output / "pair.json", flush=True)


if __name__ == "__main__":
    main()
