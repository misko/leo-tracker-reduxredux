"""Qualify the opt-in charted original entry against the sealed resident batch proof."""

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter, process_time


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
import integrated_original_batch as batch
from reports.ALGO08.v3 import original_full_detector_boundary as detector


REFERENCE = Path("/tmp/leo-v3-integrated-original-batch-proof01")
REFERENCE_BUILD = "sha256:30cc3b044040f2519677d67abfde731f83693612744d2236d1ba71bb5a31e4ab"
REFERENCE_AUTHORITY = "sha256:c661ddb3b776e436de107c83ce1e8c1112d167f28d3418b7456476bcc3f1852f"
REFERENCE_MARKER = "sha256:700525392747bb4ad3aafb3b3d97216f03b143330e6405a10cf1b473c6f0b8dc"
REFERENCE_NATIVE = "sha256:5eea8c0db979ec729e83f56f2cb806823d785fbc65455730ee321cfc9de9a245"
REGION = Path("/dev/shm/leo-v3-raw-0016-best-results-01/offer.json")


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return batch.tagged_bytes(path.read_bytes())


def experiment(root):
    from empty_bootstrap import RELEASE
    from short_raw_diagnostic import measure
    from visit_frame_raw_0016 import resident
    from eight_ms_south_transfer import environment_for

    old = batch.document(REFERENCE / "build.json", REFERENCE_BUILD)
    authority = batch.document(REFERENCE / "authority.json", REFERENCE_AUTHORITY)
    marker = batch.document(REFERENCE / "candidate" / batch.RELEASE_FILE, REFERENCE_MARKER)
    request = detector.admission()
    paths = detector.enrolled_paths(request)
    prior = read(REFERENCE / "candidate/unified-short-bootstrap.json")
    if (authority["recording"] != request["request"]["recording"] or marker["decision"] != "complete"
            or marker["authority_sha256"] != REFERENCE_AUTHORITY or marker["build_sha256"] != REFERENCE_BUILD
            or sha(REGION) != authority["region_sha256"] or prior["native_sha256"] != REFERENCE_NATIVE):
        raise ValueError("Expected the exact original charted 0016 batch proof")
    cache = resident(paths)
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts"):
        (root / name).mkdir()
    build = root / "build.json"
    source_names = (Path(batch.__file__).name, *batch.SNAPSHOT_SOURCES)
    pins = {str((HERE / name).relative_to(batch.ROOT)): sha(HERE / name) for name in source_names}
    batch.write(build, old | {"sources": old["sources"] | pins})
    checked = sha(build)
    batch.load_build(build, checked, reuse_prefetched_snapshots=True)
    output = root / "candidate"
    command = [str(RELEASE / "venv/bin/python"), "-IB", str(Path(batch.__file__)),
               "--recording", authority["recording"], "--archive", prior["archive_root"], "--region", str(REGION),
               "--bulk-root", str(output), "--build", str(build), "--build-sha256", checked,
               "--authority", str(REFERENCE / "authority.json"), "--authority-sha256", REFERENCE_AUTHORITY,
               "--reuse-prefetched-snapshots"]
    batch.write(root / "admission.json", dict(case=detector.CASE, command=command, build_sha256=checked,
        prior_build=REFERENCE_BUILD, authority=authority, reference_marker=REFERENCE_MARKER, cache_before=cache,
        signed_roster=request["roster"], native_reference=REFERENCE_NATIVE, scope="complete_original_batch"))
    before = resident(paths)
    resources = root / "peak-rss-kib.txt"
    clock = measure(["/usr/bin/time", "-f", "%M", "-o", str(resources), *command], environment_for(root), output)
    batch.write(root / "process.json", dict(clock=clock, peak_rss_kib=int(resources.read_text().strip().splitlines()[-1]),
                cache_before=before, cache_after=resident(paths), launch=command))
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def snapshot(folder, authority, started, expected_build):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from joint_publication import artifacts
    from raw_0016_best_score import position_sides
    from tools.pipeline_eval.qualification.paired_publication import evidence

    marker = read(folder / batch.RELEASE_FILE)
    receipt = marker["receipt"]
    bootstrap = read(folder / "unified-short-bootstrap.json")
    raw = read(folder / "legacy-original-acquisition.json")
    witness = read(folder / "exact-named-raw-witness.json")
    if (marker["authority_sha256"] != REFERENCE_AUTHORITY or marker["build_sha256"] != expected_build
            or marker["archive_sha256"] != authority["archive_sha256"] or receipt != bootstrap["receipt"]
            or not all(marker[key] == receipt[key] for key in ("decision", "session_id", "run_id", "terminal_sha256"))):
        raise ValueError("Publication does not match the signed original or checked build")
    (native_path,) = folder.glob("fast-scan-automatic-work/*/detections.json")
    native = read(native_path)
    batch.match_native(authority, native)
    product = evidence(folder, receipt, started, read_only=True)
    terminal = folder / "fast-scan-automatic-work" / receipt["run_id"] / "terminal.json"
    media = artifacts(folder, receipt)
    store = FastStandardAnalysisStore(folder)
    positions = position_sides(store, receipt, media)
    owners = witness["evidence"]["owner_rows"]
    if (sha(native_path) != bootstrap["native_sha256"] or sha(terminal) != receipt["terminal_sha256"]
            or product["raw_authority"] != authority["raw_authority_sha256"]
            or raw["finished_raw_authority"] != authority["raw_authority_sha256"]
            or receipt["decision"] != "complete" or len(media["images"]) != 8
            or set(owners) != {"c0", "fitted_c"} or set(product["arms"]) != set(owners)
            or any(canonical_digest({oid: label for oid, label, _ in rows}) != product["owners"][arm]
                   for arm, rows in owners.items())
            or bootstrap["raw_acquisitions"] != 1 or bootstrap["verified_handoffs"] != 1):
        raise ValueError("Original scope or published scientific evidence changed")
    grid, path = (store.position_grid(receipt["run_id"]), store.position_path(receipt["run_id"]))
    return dict(native_sha256=sha(native_path), terminal_sha256=sha(terminal), arms=product["arms"],
                owners=owners, geo_science=product["scientific_digests"], grid_points=positions["grid_points"],
                grid_normalized=canonical_digest({k: v for k, v in grid.items() if k != "elapsed_seconds"}),
                path=canonical_digest(path), images=media["images"], phases=bootstrap["phases"],
                prefetch=bootstrap["prefetch"], members=raw["members"], route=bootstrap["route"],
                receiver_recipe=bootstrap["receiver_recipe"], portable_dispatch=marker["portable_dispatch"],
                detector_file_s=(native_path.stat().st_mtime_ns - started) / 1e9,
                terminal_file_s=product["terminal_file_s"], marker_s=((folder / batch.RELEASE_FILE).stat().st_mtime_ns - started) / 1e9)


def score(root):
    logs, admission = (read(root / name) for name in ("process.json", "admission.json"))
    candidate = root / "candidate"
    old = REFERENCE / "candidate"
    batch.checked(old / batch.RELEASE_FILE, REFERENCE_MARKER)
    reference = snapshot(old, admission["authority"], 0, REFERENCE_BUILD)
    before, cpu = perf_counter(), process_time()
    current = snapshot(candidate, admission["authority"], logs["clock"]["started_unix_ns"], admission["build_sha256"])
    verification = dict(elapsed_s=perf_counter() - before, cpu_s=process_time() - cpu)
    overlay = read(candidate / "prefetch-snapshots.json")
    roster = ("chunk_index", "first_sequence", "manifest_sha256", "member_sha256", "index_sha256", "raw_sha256",
              "encoded", "decoded", "windows")
    stable = ("native_sha256", "terminal_sha256", "arms", "owners", "geo_science", "grid_points", "grid_normalized",
              "path", "images", "route", "receiver_recipe", "portable_dispatch")
    checks = {key: current[key] == reference[key] for key in stable}
    checks.update(scope=dict((key, current["prefetch"][key]) for key in
        ("hits", "fallback", "hit_bytes", "submitted", "submitted_bytes")) == {
            "hits": 11, "fallback": 0, "hit_bytes": 834805982, "submitted": 11, "submitted_bytes": 834805982},
        native_reference=reference["native_sha256"] == admission["native_reference"],
        original_roster=[tuple(row[k] for k in roster) for row in current["members"]] ==
                         [tuple(row[k] for k in roster) for row in admission["signed_roster"]],
        actual_buffers=overlay["statistics"] == current["prefetch"] and overlay["native_sha256"] == current["native_sha256"]
            and len(overlay["slots"]) == 2 and sum(slot.get("reuses", 0) for slot in overlay["slots"]) > 0,
        original_cache=logs["cache_before"] == logs["cache_after"] == admission["cache_before"],
        exited=logs["clock"]["exit_code"] == 0,
        publication_order=0 < current["detector_file_s"] < current["terminal_file_s"] <= current["marker_s"] <= logs["clock"]["elapsed_s"])
    # Prior child's GNU time already sealed its elapsed boundary. Event
    # mtimes above are used only to validate the new independent clock.
    for label in ("terminal_file_s", "marker_s", "detector_file_s"):
        del reference[label]
    batch.write(root / "result.json", dict(case=detector.CASE, qualified=all(checks.values()), checks=checks,
        candidate=current, reference=reference, archival_control=REFERENCE_MARKER, original_raw_children=1,
        backing_waveform_bytes=0, process=logs, validation=verification, snapshot_buffers=overlay,
        launch_plus_validation_s=logs["clock"]["elapsed_s"] + verification["elapsed_s"],
        admission_sha256=sha(root / "admission.json")))
    if not all(checks.values()):
        raise ValueError(f"Output parity failed: {[key for key, passed in checks.items() if not passed]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    (experiment if args.action == "launch" else score)(args.root)
