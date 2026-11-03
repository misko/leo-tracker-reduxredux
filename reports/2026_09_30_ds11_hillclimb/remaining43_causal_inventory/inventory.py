"""Metadata-only guard-versus-capture orbit census for the remaining DS11 scans."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path

from sgp4.api import Satrec

HERE = Path(__file__).resolve().parent
HILL = HERE.parent
REPO = HILL.parent.parent
FULL_MANIFEST = HILL.parent / "2026_09_30_ds11_post_ds10/local/manifest.json"
ORIGINAL_IDENTITIES = HILL / "source_balance/catalogue_identities.json"
ADDITIONAL_PLAN = HILL / "additional-plan.json"
HELPER_PATH = HILL / "additional_causal_inventory/inventory.py"
FIELDS = (
    "jdsatepoch", "jdsatepochF", "bstar", "ndot", "nddot", "inclo",
    "nodeo", "ecco", "argpo", "mo", "no_kozai",
)

SPEC = importlib.util.spec_from_file_location("additional_causal_helper", HELPER_PATH)
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def element_digest(record) -> str:
    return hashlib.sha256(
        (record.first_line + "\n" + record.second_line + "\n").encode()
    ).hexdigest()


def latest_by_provider(refs, cutoff: int) -> list:
    answer = []
    for provider in sorted({ref.provider for ref in refs}):
        eligible = [ref for ref in refs if ref.provider == provider and ref.collected_utc_ns < cutoff]
        if eligible:
            answer.append(max(eligible, key=lambda ref: (ref.collected_utc_ns, ref.digest)))
    return answer


def sgp4_fields(record) -> dict[str, float]:
    satellite = Satrec.twoline2rv(record.first_line, record.second_line)
    return {name: float(getattr(satellite, name)) for name in FIELDS}


def compare_catalogues(original: dict, selected: dict) -> dict:
    rows = []
    for norad in sorted(original):
        old_value, old_record = original[norad]
        new_value, new_record = selected.get(norad, original[norad])
        changed = old_value[3] != new_value[3]
        if not changed:
            continue
        old_fields = sgp4_fields(old_record)
        new_fields = sgp4_fields(new_record)
        differences = {
            name: new_fields[name] - old_fields[name]
            for name in FIELDS
            if new_fields[name] != old_fields[name]
        }
        rows.append(
            {
                "norad": norad,
                "original_epoch_ns": old_value[0],
                "selected_epoch_ns": new_value[0],
                "epoch_advance_s": (new_value[0] - old_value[0]) / 1e9,
                "original_snapshot": old_value[2],
                "selected_snapshot": new_value[2],
                "original_element_sha256": old_value[3],
                "selected_element_sha256": new_value[3],
                "changed_sgp4_inputs": bool(differences),
                "sgp4_differences": differences,
            }
        )
    return {
        "baseline_objects": len(original),
        "changed_element_bytes": len(rows),
        "changed_sgp4_inputs": sum(row["changed_sgp4_inputs"] for row in rows),
        "newer_epoch": sum(row["epoch_advance_s"] > 0 for row in rows),
        "newer_epoch_and_changed_sgp4": sum(
            row["epoch_advance_s"] > 0 and row["changed_sgp4_inputs"] for row in rows
        ),
        "byte_only_no_sgp4_change": sum(not row["changed_sgp4_inputs"] for row in rows),
        "same_epoch_changed_sgp4": sum(
            row["epoch_advance_s"] == 0 and row["changed_sgp4_inputs"] for row in rows
        ),
        "changes": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()

    from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
    from leo.operations import tle_collector
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records

    full = json.loads(FULL_MANIFEST.read_text())
    originals = json.loads(ORIGINAL_IDENTITIES.read_text())
    additional = json.loads(ADDITIONAL_PLAN.read_text())
    if len(full["captures"]) != 87 or len(originals["scans"]) != 32 or additional["count"] != 12:
        raise ValueError("DS11 panel cardinality mismatch")
    original_sessions = {row["session_id"] for row in originals["scans"].values()}
    additional_sessions = {row["session_id"] for row in additional["captures"]}
    if original_sessions & additional_sessions:
        raise ValueError("original32 and additional12 overlap")
    remaining = [
        (index, row)
        for index, row in enumerate(full["captures"])
        if row["session_id"] not in original_sessions | additional_sessions
    ]
    if len(remaining) != 43:
        raise ValueError("remaining panel is not 43 scans")

    reader = TleArchiveReader(args.tle_root)
    refs = reader.list_snapshots()
    journal = HELPER.parse_journal(args.journal_log.read_text())
    record_cache = {}

    def records(ref):
        key = (ref.provider, ref.collected_utc_ns, ref.digest)
        if key not in record_cache:
            filtered, _ = exclude_labelled_starlink_debris(reader.read(ref))
            parsed = parse_element_set_records(filtered)
            mapping = {}
            for record in parsed:
                if record.satellite_number in mapping:
                    raise ValueError(f"duplicate NORAD in {ref.path}")
                value = (
                    HELPER.epoch_ns(record.first_line),
                    ref.collected_utc_ns,
                    ref.digest,
                    element_digest(record),
                )
                mapping[record.satellite_number] = (value, record)
            record_cache[key] = mapping
        return record_cache[key]

    def selection(source_refs, identities=None):
        choices = {}
        for ref in source_refs:
            for norad, item in records(ref).items():
                if identities is not None and norad not in identities:
                    continue
                if norad not in choices or item[0][:3] > choices[norad][0][:3]:
                    choices[norad] = item
        return choices

    census = []
    eligible = []
    proofs = []
    for index, capture in remaining:
        capture_ns = int(capture["capture_start_utc_ns"])
        guard_ns = capture_ns - 505 * 10**9
        interval_refs = sorted(
            (ref for ref in refs if guard_ns <= ref.collected_utc_ns < capture_ns),
            key=lambda ref: (ref.provider, ref.collected_utc_ns, ref.digest),
        )
        interval_rows = []
        for ref in interval_refs:
            reader.read(ref)
            receipt = HELPER.qualifying_receipt(ref, capture_ns, journal)
            row = {
                "provider": ref.provider,
                "snapshot_collected_utc_ns": ref.collected_utc_ns,
                "snapshot_sha256": ref.digest,
                "archive_path": str(ref.path),
                "qualified": receipt is not None,
                "rejection": None if receipt else "no exact publication after file completion and before capture",
            }
            if receipt:
                row.update(receipt)
                proofs.append(
                    {
                        "full_manifest_index": index,
                        "session": capture["session_id"],
                        "capture_start_utc_ns": capture_ns,
                        **row,
                    }
                )
            interval_rows.append(row)
        census_row = {
            "full_manifest_index": index,
            "session": capture["session_id"],
            "manifest_sha256": capture["manifest_sha256"],
            "capture_start_utc_ns": capture_ns,
            "guard_cutoff_utc_ns": guard_ns,
            "window_snapshots": interval_rows,
        }
        census.append(census_row)
        if interval_rows:
            eligible.append(census_row)

    if [row["full_manifest_index"] for row in eligible] != [10, 18, 35, 60, 75]:
        raise ValueError("request-window census differs from frozen five-scan set")
    comparisons = []
    for row in eligible:
        index = row["full_manifest_index"]
        capture_ns = row["capture_start_utc_ns"]
        guard_ns = row["guard_cutoff_utc_ns"]
        baseline_sources = latest_by_provider(refs, guard_ns)
        qualified_keys = {
            (proof["provider"], proof["snapshot_collected_utc_ns"], proof["snapshot_sha256"])
            for proof in proofs
            if proof["full_manifest_index"] == index
        }
        qualified_interval = [
            ref
            for ref in refs
            if (ref.provider, ref.collected_utc_ns, ref.digest) in qualified_keys
        ]
        capture_sources = []
        for provider in sorted({ref.provider for ref in baseline_sources + qualified_interval}):
            capture_sources.append(
                max(
                    (ref for ref in baseline_sources + qualified_interval if ref.provider == provider),
                    key=lambda ref: (ref.collected_utc_ns, ref.digest),
                )
            )
        base_identity_ref = max(
            baseline_sources, key=lambda ref: (ref.collected_utc_ns, ref.digest)
        )
        identities = set(records(base_identity_ref))
        baseline = selection(baseline_sources, identities)
        if set(baseline) != identities:
            raise ValueError("latest-provider baseline lost a baseline identity")
        capture_latest = selection(capture_sources, identities)

        history_start = guard_ns - 3 * 86400 * 10**9
        guard_history = [ref for ref in refs if history_start <= ref.collected_utc_ns < guard_ns]
        capture_history = guard_history + qualified_interval
        guard_best = dict(baseline)
        guard_best.update(
            {
                norad: item
                for norad, item in selection(guard_history, identities).items()
                if item[0][:3] > baseline[norad][0][:3]
            }
        )
        capture_best = dict(baseline)
        capture_best.update(
            {
                norad: item
                for norad, item in selection(capture_history, identities).items()
                if item[0][:3] > baseline[norad][0][:3]
            }
        )
        comparisons.append(
            {
                "full_manifest_index": index,
                "session": row["session"],
                "capture_start_utc_ns": capture_ns,
                "guard_cutoff_utc_ns": guard_ns,
                "baseline_identity_snapshot": base_identity_ref.digest,
                "baseline_latest_provider_sources": [
                    {"provider": ref.provider, "collected_utc_ns": ref.collected_utc_ns, "digest": ref.digest}
                    for ref in baseline_sources
                ],
                "capture_latest_provider_sources": [
                    {"provider": ref.provider, "collected_utc_ns": ref.collected_utc_ns, "digest": ref.digest}
                    for ref in capture_sources
                ],
                "latest_provider_capture_vs_guard": compare_catalogues(baseline, capture_latest),
                "three_day_best_at_guard_vs_latest_provider_guard": compare_catalogues(
                    baseline, guard_best
                ),
                "three_day_best_capture_vs_latest_provider_guard": compare_catalogues(
                    baseline, capture_best
                ),
                "three_day_best_capture_vs_three_day_best_guard": compare_catalogues(
                    guard_best, capture_best
                ),
            }
        )

    def totals(key):
        names = (
            "changed_element_bytes", "changed_sgp4_inputs", "newer_epoch",
            "newer_epoch_and_changed_sgp4", "byte_only_no_sgp4_change",
            "same_epoch_changed_sgp4",
        )
        return {name: sum(row[key][name] for row in comparisons) for name in names}

    result = {
        "schema": "ds11-remaining43-causal-orbit-inventory/v1",
        "status": "read_only_metadata_inventory_complete",
        "position_fits_run": 0,
        "propagations_run": 0,
        "selection_frozen_before_error_analysis": True,
        "membership": {
            "full_manifest_scans": 87,
            "excluded_original32": 32,
            "excluded_additional12": 12,
            "remaining_scans": 43,
        },
        "completion_criterion": (
            "exact archive digest plus matching tle_collection provider status=published receipt; "
            "file birth/mtime and receipt all precede capture"
        ),
        "summary": {
            "request_window_scans": len(eligible),
            "request_window_indices": [row["full_manifest_index"] for row in eligible],
            "request_window_snapshot_occurrences": sum(len(row["window_snapshots"]) for row in eligible),
            "completion_qualified_snapshot_occurrences": len(proofs),
            "latest_provider_capture_vs_guard": totals("latest_provider_capture_vs_guard"),
            "three_day_best_at_guard_vs_latest_provider_guard": totals(
                "three_day_best_at_guard_vs_latest_provider_guard"
            ),
            "three_day_best_capture_vs_latest_provider_guard": totals(
                "three_day_best_capture_vs_latest_provider_guard"
            ),
            "three_day_best_capture_vs_three_day_best_guard": totals(
                "three_day_best_capture_vs_three_day_best_guard"
            ),
        },
        "completion_proof": {
            "schema": "ds11-capture-start-snapshot-completion-proof/v1",
            "qualified_snapshots": proofs,
        },
        "census": census,
        "comparisons": comparisons,
        "limitations": [
            "SGP4 input fields are compared exactly; no orbit is propagated and no measurement or position error is inspected.",
            "Filesystem times and the local journal are operational evidence rather than signed external attestations.",
            "Latest-provider comparison reproduces the exporter catalogue rule; the three-day comparison reproduces the causal_fresh best-per-NORAD rule with the original baseline as fallback.",
        ],
        "source_sha256": {
            str(Path(__file__)): digest(Path(__file__)),
            str(FULL_MANIFEST): digest(FULL_MANIFEST),
            str(ORIGINAL_IDENTITIES): digest(ORIGINAL_IDENTITIES),
            str(ADDITIONAL_PLAN): digest(ADDITIONAL_PLAN),
            str(HELPER_PATH): digest(HELPER_PATH),
            str(args.journal_log): digest(args.journal_log),
            str(Path(inspect.getfile(TleArchiveReader))): digest(Path(inspect.getfile(TleArchiveReader))),
            str(Path(inspect.getfile(parse_element_set_records))): digest(
                Path(inspect.getfile(parse_element_set_records))
            ),
            str(Path(inspect.getfile(exclude_labelled_starlink_debris))): digest(
                Path(inspect.getfile(exclude_labelled_starlink_debris))
            ),
            str(Path(inspect.getfile(tle_collector))): digest(Path(inspect.getfile(tle_collector))),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
