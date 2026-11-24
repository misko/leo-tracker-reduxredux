"""Publish one complete resident original with the genuinely installed receiver."""

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter, process_time

import prefetch_snapshot_publication as trial
from installed_receiver_control import RELEASE_FILE, RELEASE_SCHEMA


STOCK = Path("/dev/shm/leo-v3-raw-0016-best-results-01")
STOCK_RECEIPT = "sha256:348ed9bffa27185f39673bdd0ee20ec2418a9b1e8723f19a950f4e5bd4e399a8"
STOCK_MARKER = "sha256:8bc646d305fb31cb6e731a9de59009168ddd585628c569ca87bb1b835cd9ff1b"


def reference():
    from raw_0016_best_score import STOCK_NATIVE

    set_ = trial.batch.document(STOCK / "result-final.json", STOCK_RECEIPT)
    named = set_["original"]["stock"]
    marker = trial.batch.document(STOCK / "stock/algo08v3-release.json", STOCK_MARKER)
    (native,) = (STOCK / "stock/fast-scan-automatic-work").glob("*/detections.json")
    if (trial.sha(native) != STOCK_NATIVE or named["native_sha256"] != STOCK_NATIVE
            or marker["version"] != "ALGO08v3" or marker["decision"] != "complete"
            or marker["session_id"] != named["science"]["receipt"]["session_id"]):
        raise ValueError("The independently sealed installed original changed")
    return named, marker, native


def launch(root):
    _, _, native = reference()
    trial.experiment(root, stock_native=trial.sha(native))


def score(root):
    sys.path.insert(0, str(trial.batch.ROOT / "src"))
    from leo.contracts.digests import canonical_digest
    from raw_0016_best_score import STOCK_OWNERS, STOCK_OWNERS_SHA
    from triage_bounds import calibration_comparison
    from prospective_0316_solver import owner_delta

    named, installed, original_native = reference()
    reference_rows = trial.batch.document(STOCK_OWNERS, STOCK_OWNERS_SHA)
    original_owners = reference_rows["selected_rows"]
    stock_science = named["science"]
    if (reference_rows["receipt"]["terminal_sha256"] != stock_science["receipt"]["terminal_sha256"]
            or any(canonical_digest({oid: label for oid, label, _ in rows}) != stock_science["owners"][arm]
                   for arm, rows in original_owners.items())):
        raise ValueError("Ordered installed owners were sealed against a different result")
    logs, admission = (trial.read(root / name) for name in ("process.json", "admission.json"))
    folder = root / "candidate"
    began, cpu = perf_counter(), process_time()
    watched = trial.snapshot(folder, admission["authority"], logs["clock"]["started_unix_ns"],
                             admission["build_sha256"], stock_receiver=True)
    marker = trial.read(folder / RELEASE_FILE)
    overlay = trial.read(folder / "prefetch-snapshots.json")
    bootstrap = trial.read(folder / "unified-short-bootstrap.json")
    (native,) = (folder / "fast-scan-automatic-work").glob("*/detections.json")
    if logs["clock"]["exit_code"]:
        raise ValueError("Original receiver child did not exit successfully")
    validation = dict(elapsed_s=perf_counter() - began, cpu_s=process_time() - cpu)
    owner_rows = watched["owners"]
    canvas_equal = {k: watched["images"][k]["rgba_sha256"] == named["figures"][k]["rgba_sha256"] for k in watched["images"]}
    encoded_equal = {k: watched["images"][k]["sha256"] == named["figures"][k]["sha256"] for k in watched["images"]}
    verify_keys = ("chunk_index", "first_sequence", "manifest_sha256", "member_sha256", "index_sha256", "raw_sha256",
                   "encoded", "decoded", "windows")
    checks = dict(installed_native_exact=(native.read_bytes() == original_native.read_bytes()
                      and marker["native_sha256"] == watched["native_sha256"] == admission["native_reference"]),
        authenticated_roster=[tuple(m[k] for k in verify_keys) for m in watched["members"]] ==
                             [tuple(m[k] for k in verify_keys) for m in admission["signed_roster"]],
        requested_identity=marker["session_id"] == stock_science["receipt"]["session_id"]
                           and marker["receipt"]["region"] == stock_science["receipt"]["region"],
        explicit_research_release=marker["schema"] == RELEASE_SCHEMA and marker["detector_sha256"] ==
            "sha256:" + installed["detector_sha256"] and not (folder / "algo08v3-release.json").exists()
            and not (folder / trial.batch.RELEASE_FILE).exists(),
        installed_only=bootstrap["receiver_audit"]["native"]["native_calls"] == {"full": named["probes"]}
                       and "held_anchor_route" not in bootstrap and watched["receiver_recipe"]["probe_ms"] == 20,
        exact_slots=overlay["statistics"] == watched["prefetch"] and watched["prefetch"]["hits"] == 11
                    and not watched["prefetch"]["fallback"] and sum(s.get("reuses", 0) for s in overlay["slots"]) > 0,
        charted_publication=watched["grid_points"] == 179 and len(watched["images"]) == 8
                            and watched["portable_dispatch"] == "eligible",
        resident=admission["cache_before"] == logs["cache_before"] == logs["cache_after"],
        boundary=0 < watched["detector_file_s"] < watched["terminal_file_s"] <= watched["marker_s"] <= logs["clock"]["elapsed_s"])
    science_exact = dict(arms=watched["arms"] == stock_science["arms"], owners=owner_rows == original_owners,
        grid=watched["geo_science"]["grid"] == stock_science["scientific_digests"]["grid"],
        path=watched["geo_science"]["path"] == stock_science["scientific_digests"]["path"],
        terminal=watched["terminal_sha256"] == stock_science["receipt"]["terminal_sha256"],
        png_pixels=canvas_equal, png_files=encoded_equal)
    geo = calibration_comparison(dict(installed=stock_science, candidate={"arms": watched["arms"]}), trial.detector.CASE)
    clock = logs["clock"]
    historical = named["process"]["clock"]
    target = historical["elapsed_s"] / 2
    acquisition = watched["phases"]["authenticated_raw_acquisition"]
    result = dict(qualified=all(checks.values()), checks=checks, science_exact=science_exact, geography=geo,
        owner_delta={a: owner_delta(original_owners[a], rows) for a, rows in owner_rows.items()},
        stock_archival=named, stock_archival_receipt=STOCK_RECEIPT,
        candidate=watched, process=logs, validation=validation, snapshots=overlay, original_raw_children=1,
        elapsed_s=clock["elapsed_s"] + validation["elapsed_s"], raw_waveform_backing_bytes=0,
        native_work=bootstrap["receiver_audit"]["native"],
        budgets=dict(historical_through_exit_half_s=target, seconds_over_half=clock["elapsed_s"]-target,
                     historical_elapsed_ratio=historical["elapsed_s"]/clock["elapsed_s"],
                     budget_after_acquisition_s=target-acquisition["elapsed_s"]),
        admission_sha256=trial.sha(root / "admission.json"))
    trial.batch.write(root / "result.json", result)
    if not result["qualified"]:
        raise ValueError(f"Original receiver or publication scope changed: {checks}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    (launch if args.action == "launch" else score)(args.root)
