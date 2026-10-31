"""Read-only provenance/initialization audit; never loads geographic truth."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import numpy as np


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return "sha256:" + hasher.hexdigest()


def normalized(value: str) -> str:
    return "sha256:" + value.removeprefix("sha256:")


def load(path: Path):
    return json.loads(path.read_text())


def tle_records(path: Path) -> dict[str, tuple[list[str], int]]:
    lines = path.read_text().splitlines()
    records = {}
    for index, line in enumerate(lines):
        if not line.startswith("1 "):
            continue
        pair = [line, lines[index + 1]]
        if not pair[1].startswith("2 "):
            raise ValueError("malformed TLE pair")
        encoded = line[2:7]
        if encoded[0].isalpha():
            alpha5 = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
            norad = str(alpha5.index(encoded[0]) * 10000 + int(encoded[1:]))
        else:
            norad = str(int(encoded))
        year = int(line[18:20])
        year += 2000 if year < 57 else 1900
        base = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()) * 10**9
        epoch = base + int((Decimal(line[20:32]) - 1) * 86400 * 10**9)
        if norad in records:
            raise ValueError("duplicate catalogue NORAD")
        records[norad] = pair, epoch
    return records


def age_summary(cutoff: int, epochs: list[int]) -> dict:
    return {
        "count": len(epochs),
        "minimum_utc_ns": min(epochs) if epochs else None,
        "latest_utc_ns": max(epochs) if epochs else None,
        "minimum_age_hours": (cutoff - max(epochs)) / 3.6e12 if epochs else None,
        "maximum_age_hours": (cutoff - min(epochs)) / 3.6e12 if epochs else None,
    }


def audit_snapshot(descriptor_path: Path, public_input_path: Path | None = None) -> dict:
    descriptor = load(descriptor_path)
    root = Path(descriptor["root"]).resolve(strict=True)
    files = descriptor["files"]
    checks = []
    hashes = {}

    def check(name, condition):
        checks.append({"check": name, "passed": bool(condition)})

    def verified(relative):
        path = root / relative
        check(relative + ":confined_regular_file", not path.is_symlink() and path.is_file()
              and path.resolve().is_relative_to(root))
        actual = digest(path)
        hashes[relative] = actual
        check(relative + ":descriptor_hash", actual == normalized(files[relative]))
        return path

    receipt = load(verified("SCAN/receipt.json"))
    cutoff = int(receipt["cutoff_utc_ns"])
    prepared = load(verified("SCAN/prepared.json"))
    tracking = load(verified("SCAN/tracking.json"))
    check("receipt_cutoff_matches_prepared", cutoff == prepared["metadata"]["causal_cutoff_utc_ns"])
    check("receipt_origin_matches_prepared", receipt["origin_utc_ns"] == prepared["metadata"]["anchor_utc_ns"])
    clock = tracking["clock_anchor"]
    check("cutoff_matches_original_clock_lower_bound", cutoff == clock["before"]["realtime_ns"])
    check("origin_within_original_clock_bracket", cutoff <= receipt["origin_utc_ns"] <= clock["after"]["realtime_ns"])
    if public_input_path is not None:
        hashes["frozen_public_input"] = digest(public_input_path)
        check("public_input_byte_hash", hashes["frozen_public_input"] == normalized(descriptor["input_sha256"]))
        check("snapshot_tracking_content_matches_public_input", tracking == load(public_input_path))
    else:
        check("tracking_matches_public_input_hash", hashes["SCAN/tracking.json"] == normalized(descriptor["input_sha256"]))
    check("prepared_matches_original_input_hash", normalized(prepared["tracking_sha256"]) == normalized(descriptor["input_sha256"]))
    nominal = load(verified("SCAN/nominal_elements.json"))
    latest = tle_records(verified("SCAN/selected.tle"))
    bank_path = verified("SCAN/bank.npz")
    with np.load(bank_path, allow_pickle=False) as bank:
        bank_ids = [str(int(n)) for n in bank["norad"]]
    check("bank_unique_exact_nominal_roster", len(bank_ids) == len(set(bank_ids))
          and set(bank_ids) == set(nominal))
    check("latest_exact_nominal_roster", set(latest) == set(nominal))
    check("candidate_count", receipt["candidate_count"] == len(nominal))
    epochs = [int(v["provenance"]["element_epoch_utc_ns"]) for v in nominal.values()]
    collections = [int(v["provenance"]["collected_utc_ns"]) for v in nominal.values()]
    check("latest_each_epoch_causal", all(e <= cutoff for e in epochs))
    check("latest_each_collection_causal", all(e <= cutoff for e in collections))
    check("latest_receipt_epoch_extremum", max(epochs) == receipt["latest_max_epoch_utc_ns"])
    check("latest_receipt_collection_extremum", max(collections) == receipt["latest_max_collection_utc_ns"])
    check("latest_TLE_lines_match_nominal", all(latest[k][0] == v["lines"] for k, v in nominal.items()))
    check("latest_TLE_epochs_match_provenance_1us", all(
        abs(latest[k][1] - int(v["provenance"]["element_epoch_utc_ns"])) <= 1024
        for k, v in nominal.items()))
    check("latest_TLE_each_epoch_causal", all(v[1] <= cutoff for v in latest.values()))
    check("bank_receipt_hash", hashes["SCAN/bank.npz"] == normalized(receipt["bank_sha256"]))
    check("latest_TLE_receipt_hash", hashes["SCAN/selected.tle"] == normalized(receipt["latest_tle_sha256"]))
    check("reference_position_unused", receipt.get("reference_position_used") is False)
    check("candidate_filter_no_whitelist", receipt.get("candidate_filter") == "regional elevation >= -12deg; no whitelist")
    check("search_center", receipt.get("search_center") == [37.906, -122.545])
    check("search_width", receipt.get("search_box_width_km") == 25.0)
    terminal = descriptor["terminal"]
    check("terminal_reference_usage_none", terminal.get("reference_usage") == "none")
    check("terminal_no_future_TLE", terminal.get("future_TLE_used") is False)
    check("terminal_search_center", terminal.get("region_center") == [37.906, -122.545])
    check("terminal_search_width", terminal.get("box_width_km") == 25.0)
    check("terminal_initial_offset", terminal.get("start_east_north_km") == [0.0, 0.0])

    previous_summaries = {}
    for prefix, prior_receipt in [("SCAN", receipt), ("causal_prior/SCAN", None)]:
        if prefix != "SCAN":
            relative = prefix + "/receipt.json"
            if relative not in files:
                continue
            prior_receipt = load(verified(relative))
            check(prefix + ":cutoff_matches", prior_receipt["cutoff_utc_ns"] == cutoff)
            check(prefix + ":shared_bank_and_initialization", all(
                prior_receipt.get(key) == receipt.get(key)
                for key in ("bank_sha256", "latest_tle_sha256", "reference_position_used",
                            "candidate_filter", "search_center", "search_box_width_km")))
        source_receipt = load(verified(prefix + "/previous_receipt.json"))
        previous = tle_records(verified(prefix + "/previous.tle"))
        sources = source_receipt["sources"]
        pe = [int(v["epoch_utc_ns"]) for v in sources.values()]
        pc = [int(v["collected_utc_ns"]) for v in sources.values()]
        check(prefix + ":each_previous_epoch_causal", all(e <= cutoff for e in pe))
        check(prefix + ":each_previous_collection_causal", all(e <= cutoff for e in pc))
        check(prefix + ":previous_roster", set(previous) == set(sources) and set(sources).issubset(nominal))
        check(prefix + ":previous_count", prior_receipt["previous_count"] == len(sources))
        check(prefix + ":previous_TLE_epochs_match_sources_1us", all(
            abs(previous[k][1] - int(v["epoch_utc_ns"])) <= 1024 for k, v in sources.items()))
        check(prefix + ":previous_TLE_each_epoch_causal", all(v[1] <= cutoff for v in previous.values()))
        gaps = [(int(nominal[k]["provenance"]["element_epoch_utc_ns"]) - int(v["epoch_utc_ns"])) / 1e9
                for k, v in sources.items()]
        check(prefix + ":strictly_earlier_than_latest", all(g > 0 for g in gaps))
        if "minimum_epoch_separation_s" in source_receipt:
            check(prefix + ":minimum_epoch_separation", all(g >= source_receipt["minimum_epoch_separation_s"] for g in gaps))
        actual = hashes[prefix + "/previous.tle"]
        check(prefix + ":previous_catalogue_receipt_hash", actual == normalized(source_receipt["catalogue_sha256"]))
        check(prefix + ":previous_main_receipt_hash", actual == normalized(prior_receipt["previous_tle_sha256"]))
        previous_summaries[prefix] = {
            "epoch": age_summary(cutoff, pe), "collection": age_summary(cutoff, pc),
            "minimum_latest_previous_epoch_gap_s": min(gaps) if gaps else None,
        }

    history_summary = None
    history_relative = "causal_phase_history/SCAN.json"
    if history_relative in files:
        history = load(verified(history_relative))
        versions = [v for values in history["past_versions"].values() for v in values]
        he = [int(v["epoch"]) for v in versions]
        hc = [int(v["collected_utc_ns"]) for v in versions]
        check("history_cutoff_matches", history["cutoff_utc_ns"] == cutoff)
        check("history_each_epoch_causal", all(e <= cutoff for e in he))
        check("history_each_collection_causal", all(e <= cutoff for e in hc))
        check("history_source_collections_causal", all(v["collected_utc_ns"] <= cutoff for v in history["sources"]))
        check("history_no_following_TLE_or_GPS", history.get("no_following_TLE_or_GPS") is True)
        check("history_archive_read_only", history.get("archive_access_is_read_only") is True)
        check("history_nominal_hash", normalized(history["latest_elements_sha256"]) == hashes["SCAN/nominal_elements.json"])
        history_summary = {"epoch": age_summary(cutoff, he), "collection": age_summary(cutoff, hc)}
    return {
        "status": "pass" if all(c["passed"] for c in checks) else "fail",
        "descriptor": str(descriptor_path), "descriptor_sha256": digest(descriptor_path),
        "input_sha256": descriptor["input_sha256"], "cutoff_utc_ns": cutoff,
        "snapshot_tracking_byte_identical_to_public_input": hashes["SCAN/tracking.json"] == normalized(descriptor["input_sha256"]),
        "candidate_count": len(nominal), "latest_epoch": age_summary(cutoff, epochs),
        "latest_collection": age_summary(cutoff, collections), "previous": previous_summaries,
        "phase_history": history_summary, "initialization": {
            "search_center": receipt["search_center"], "search_box_width_km": receipt["search_box_width_km"],
            "reference_position_used": receipt["reference_position_used"], "candidate_filter": receipt["candidate_filter"],
            "catalogue_regional_center": receipt["regional_center"], "catalogue_radius_km": receipt["radius_km"],
        }, "file_sha256": hashes, "check_count": len(checks),
        "failed_checks": [c["check"] for c in checks if not c["passed"]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--allow-in-progress", action="store_true")
    args = parser.parse_args()
    study = args.study
    seal_path = study / "evaluation-seal.json"
    if not seal_path.exists() and not args.allow_in_progress:
        raise RuntimeError("evaluation is not terminal/sealed")
    input_map = load(study / "public-input-map.json")
    if input_map["dataset_manifest_sha256"] != digest(study / "dataset/manifest.json"):
        raise ValueError("input roster belongs to another dataset manifest")
    roster = input_map["rows"]
    labels = [case["case"] for case in roster]
    if len(labels) != 15 or len(set(labels)) != 15:
        raise ValueError("expected all 15 distinct fast cases")
    if seal_path.exists():
        seal = load(seal_path)
        if (seal.get("all_terminal") is not True or seal.get("no_GPS") is not True
                or set(seal["cases"]) != set(labels)
                or len(seal["cases"]) != len(labels)
                or seal["protocol_sha256"] != digest(study / "evaluation-protocol.json")
                or set(seal["pipeline_receipts"]) != set(labels)):
            raise ValueError("evaluation seal does not cover the exact frozen fast roster")
        for label in labels:
            if seal["pipeline_receipts"][label] != digest(study / "cases" / label / "pipeline-receipt.json"):
                raise ValueError("changed sealed pipeline receipt: " + label)
    rows = []
    for case in roster:
        label = case["case"]
        descriptor = study / "cases" / label / "candidate-v2/recovery/snapshot/descriptor.json"
        if descriptor.exists():
            try:
                row = audit_snapshot(descriptor, Path(case["input_path"]))
                row["check_count"] += 1
                if row["input_sha256"] != case.get("input_sha256"):
                    row["status"] = "fail"
                    row["failed_checks"].append("frozen_public_input_sha256")
            except Exception as exc:
                row = {"status": "error", "reason": type(exc).__name__ + ": " + str(exc)}
        else:
            row = {"status": "snapshot_unavailable", "reason": case.get("reason", "no public completed snapshot descriptor")}
            pipeline = study / "cases" / label / "pipeline-receipt.json"
            if pipeline.exists():
                row["pipeline_sha256"] = digest(pipeline)
                row["pipeline_state"] = load(pipeline)["state"]
                row["pipeline_baseline_state"] = load(pipeline)["baseline"]
        rows.append({"case": label, **row})
    report = {
        "schema": "ds27-causal-initialization-audit/v1", "dataset": "DS27",
        "source_sha256": digest(Path(__file__)),
        "manifest_sha256": digest(study / "dataset/manifest.json"),
        "evaluation_seal_sha256": digest(seal_path) if seal_path.exists() else None,
        "all_evaluation_terminal": seal_path.exists(), "GPS_truth_read": False,
        "scientific_inference_rerun": False,
        "scope": "All 15 frozen fast cases; available public ALGO02 snapshots used by ALGO03/04 recovery",
        "counts": {state: sum(row["status"] == state for row in rows)
                   for state in ["pass", "fail", "error", "snapshot_unavailable"]},
        "total_checks": sum(row.get("check_count", 0) for row in rows),
        "limitations": ["Hash agreement verifies frozen receipt consistency, not independent orbit accuracy.",
                        "Archive snapshot payloads were not reread; each recorded epoch/collection was checked.",
                        "Re-exported tracking JSON may have different formatting; original public-input byte hash and parsed content equivalence are checked separately.",
                        "The 250 km catalogue prefilter and 25 km localization search box are distinct."],
        "cases": rows,
    }
    (study / "causal-initialization-audit.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = ["# DS27 causal catalogue and initialization audit", "",
             f"All 15 frozen fast cases retained: {report['counts']['pass']} passed, "
             f"{report['counts']['snapshot_unavailable']} snapshot unavailable, "
             f"{report['counts']['fail'] + report['counts']['error']} failed/error. "
             f"Evaluation sealed: {report['all_evaluation_terminal']}. No GPS truth was read; no inference was rerun.", "",
             "Every recorded nominal, previous and phase-history epoch/collection is checked against the scan cutoff. "
             "Bank/TLE bytes are checked against the public snapshot descriptor and their receipts. "
             "Available snapshots must use the fixed 25 km box centered at 37.906, -122.545, zero initial offset, "
             "no reference position and no candidate whitelist. The broad catalogue prefilter uses a separate 250 km region.", "",
             "| Case | Status | Candidates | Latest epoch age range (h) | Latest collection age range (h) |", "|---|---|---:|---:|---:|"]
    for row in rows:
        def interval(key):
            if key not in row:
                return "—"
            return f"{row[key]['minimum_age_hours']:.3f}–{row[key]['maximum_age_hours']:.3f}"
        lines.append(f"| {row['case']} | {row['status']} | {row.get('candidate_count', '—')} | {interval('latest_epoch')} | {interval('latest_collection')} |")
    lines += ["", "Unavailable cases: " + "; ".join(
        row["case"] + " — " + row["reason"] +
        (" (baseline " + row["pipeline_baseline_state"] + ")" if "pipeline_baseline_state" in row else "")
        for row in rows if row["status"] == "snapshot_unavailable") + ".", "",
              f"{report['total_checks']} checks performed. Unavailable cases retain their recorded pipeline state in the JSON. "
              "Per-case hashes, all check failures, previous-catalogue and phase-history ages are in the JSON. "
              "Hash agreement establishes frozen provenance consistency; it does not establish orbit or localization accuracy.", "",
              f"Manifest: `{report['manifest_sha256']}`. Audit source: `{report['source_sha256']}`.", ""]
    (study / "causal-initialization-audit.md").write_text("\n".join(lines))
    print(json.dumps(report["counts"]))


if __name__ == "__main__":
    main()
