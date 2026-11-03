"""Read-only inventory of capture-start TLE availability for additional12.

This script does not propagate elements or inspect fit/reference errors.  It
replays the export's newest-per-object rule over exact archived bytes, admitting
a post-505-second-guard snapshot only when a matching local publication receipt
and completed archive file both predate capture.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
HILL = HERE.parent
REPO = HILL.parent.parent
sys.path.insert(0, str(HILL.parent / "2026_09_29_orbit_revision_support"))
from inventory import epoch_ns  # noqa: E402

EVENT_RE = re.compile(r"^(?P<time>\d+\.\d+)\s+.*?(?P<body>\{.*\})$")
STAT_TIME_RE = re.compile(
    r"^(?P<date>\d{4}-\d\d-\d\d) (?P<clock>\d\d:\d\d:\d\d)"
    r"\.(?P<fraction>\d+) (?P<zone>[+-]\d{4})$"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_journal(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        match = EVENT_RE.match(line)
        if match is None:
            continue
        try:
            body = json.loads(match["body"])
        except json.JSONDecodeError:
            continue
        if body.get("event") != "tle_collection":
            continue
        published_ns = int(Decimal(match["time"]) * 10**9)
        for provider in body.get("providers", []):
            rows.append(
                {
                    "journal_published_unix_s": match["time"],
                    "journal_published_utc_ns": published_ns,
                    "provider": provider.get("provider"),
                    "snapshot_sha256": provider.get("digest"),
                    "status": provider.get("status"),
                    "journal_line": line,
                }
            )
    return rows


def stat_time_ns(value: str) -> int:
    match = STAT_TIME_RE.match(value)
    if match is None:
        raise ValueError(f"unexpected stat timestamp: {value!r}")
    base = datetime.strptime(
        f"{match['date']} {match['clock']} {match['zone']}", "%Y-%m-%d %H:%M:%S %z"
    )
    fraction = (match["fraction"] + "0" * 9)[:9]
    return int(base.timestamp()) * 10**9 + int(fraction)


def file_times(path: Path) -> dict:
    result = subprocess.run(
        ["stat", "--printf=%w\\n%y\\n", str(path)],
        check=True,
        text=True,
        capture_output=True,
    )
    birth, mtime = result.stdout.splitlines()
    if birth == "-":
        raise ValueError(f"birth time unavailable for {path}")
    return {
        "file_birth_utc": birth,
        "file_mtime_utc": mtime,
        "file_birth_utc_ns": stat_time_ns(birth),
        "file_mtime_utc_ns": stat_time_ns(mtime),
    }


def qualifying_receipt(ref, capture_ns: int, journal_rows: list[dict]) -> dict | None:
    """Return the earliest qualified exact-digest publication receipt."""
    times = file_times(ref.path)
    candidates = [
        row
        for row in journal_rows
        if row["provider"] == ref.provider
        and row["snapshot_sha256"] == ref.digest
        and row["status"] == "published"
        and max(times["file_birth_utc_ns"], times["file_mtime_utc_ns"])
        <= row["journal_published_utc_ns"]
        < capture_ns
    ]
    if not candidates:
        return None
    receipt = min(candidates, key=lambda row: row["journal_published_utc_ns"])
    return {
        **times,
        "journal_published_unix_s": receipt["journal_published_unix_s"],
        "journal_published_utc_ns": receipt["journal_published_utc_ns"],
        "journal_publication_margin_before_capture_s": (
            capture_ns - receipt["journal_published_utc_ns"]
        )
        / 1e9,
        "journal_line": receipt["journal_line"],
    }


def element_rows(reader, ref, wanted: set[int]) -> dict[int, tuple]:
    from leo.sky.propagation import parse_element_set_records

    rows = {}
    for record in parse_element_set_records(reader.read(ref)):
        number = record.satellite_number
        if number not in wanted:
            continue
        element_sha = hashlib.sha256(
            (record.first_line + "\n" + record.second_line + "\n").encode()
        ).hexdigest()
        value = (epoch_ns(record.first_line), ref.collected_utc_ns, ref.digest, element_sha)
        if number in rows:
            raise ValueError(f"duplicate NORAD {number} in {ref.path}")
        rows[number] = value
    return rows


def choose_newest(options: list[tuple]) -> tuple:
    if not options:
        raise ValueError("no element choices")
    return max(options, key=lambda value: value[:3])


def verify_artifact(path: Path, expected: str) -> None:
    observed = "sha256:" + digest(path)
    if observed != expected:
        raise ValueError(f"artifact digest mismatch for {path}: {observed} != {expected}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal-log", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tle-root", type=Path, default=Path("/var/lib/leo/tle"))
    args = parser.parse_args()

    from leo.operations.tle_archive import TleArchiveReader
    from leo.operations import tle_collector
    from leo.sky.propagation import parse_element_set_records

    plan_path = HILL / "additional/plan.json"
    sidecar_path = HILL / "additional/catalogue_identities.json"
    plan = json.loads(plan_path.read_text())
    sidecar = json.loads(sidecar_path.read_text())
    if sidecar["plan_path"] != str(plan_path):
        raise ValueError("identity sidecar plan path mismatch")
    if sidecar["plan_sha256"] != digest(plan_path):
        raise ValueError("identity sidecar plan digest mismatch")
    if len(plan["inputs"]) != 12 or len(sidecar["scans"]) != 12:
        raise ValueError("additional12 cardinality mismatch")

    journal_rows = parse_journal(args.journal_log.read_text())
    reader = TleArchiveReader(args.tle_root)
    refs = reader.list_snapshots()
    refs_by_key = {(r.provider, r.collected_utc_ns, r.digest): r for r in refs}
    scans = []
    proof_rows = []

    for index, item in enumerate(plan["inputs"]):
        artifacts = {row["path"]: row for row in item["artifacts"]}
        for path_text, artifact in artifacts.items():
            verify_artifact(Path(path_text), artifact["sha256"])
        observation_path = next(
            Path(row["path"]) for row in item["artifacts"] if row["kind"] == "observations"
        )
        manifest_path = next(
            Path(row["path"])
            for row in item["artifacts"]
            if row["kind"] == "candidates" and row["path"].endswith("manifest.json")
        )
        observation = json.loads(observation_path.read_text())
        manifest = json.loads(manifest_path.read_text())
        identity = sidecar["scans"][str(index)]
        if not (
            item["session_id"] == observation["session_id"] == manifest["session_id"]
            == identity["session_id"]
        ):
            raise ValueError(f"session binding mismatch at index {index}")
        if identity["observation_sha256"] != digest(observation_path):
            raise ValueError(f"identity observation binding mismatch at index {index}")
        if identity["manifest_sha256"] != digest(manifest_path):
            raise ValueError(f"identity manifest binding mismatch at index {index}")

        capture_ns = observation["start_utc_ns"]
        guard_ns = capture_ns - 505 * 10**9
        wanted = {
            int(norad)
            for track in identity["tracks"].values()
            for norad in track["candidate_norad"]
        }
        source_refs = []
        for source in manifest["provider_sources"]:
            key = (
                source["provider"], source["collected_utc_ns"], source["snapshot_sha256"]
            )
            ref = refs_by_key.get(key)
            if ref is None:
                raise ValueError(f"missing exact original archive source {key}")
            reader.read(ref)  # exact archive digest is reverified here
            if ref.collected_utc_ns >= guard_ns:
                raise ValueError(f"original source violates 505-second guard at index {index}")
            source_refs.append(ref)

        interval_refs = sorted(
            (r for r in refs if guard_ns <= r.collected_utc_ns < capture_ns),
            key=lambda r: (r.provider, r.collected_utc_ns, r.digest),
        )
        qualified = []
        interval_rows = []
        for ref in interval_refs:
            reader.read(ref)  # fail on archive-name/content digest mismatch
            receipt = qualifying_receipt(ref, capture_ns, journal_rows)
            row = {
                "provider": ref.provider,
                "snapshot_collected_utc_ns": ref.collected_utc_ns,
                "snapshot_sha256": ref.digest,
                "archive_path": str(ref.path),
                "qualified": receipt is not None,
                "rejection": None if receipt else "no exact published receipt after completed file and before capture",
            }
            if receipt:
                row.update(receipt)
                qualified.append(ref)
                proof_rows.append({"index": index, "session": item["session_id"], **row})
            interval_rows.append(row)

        # The export chooses one latest source per provider, then newest element
        # per physical object.  Multiple interval occurrences for a provider are
        # reduced to its latest causally proven occurrence.
        latest_qualified = []
        for provider in sorted({r.provider for r in qualified}):
            latest_qualified.append(
                max(
                    (r for r in qualified if r.provider == provider),
                    key=lambda r: (r.collected_utc_ns, r.digest),
                )
            )
        all_refs = source_refs + latest_qualified
        records = {id(ref): element_rows(reader, ref, wanted) for ref in all_refs}
        candidates = []
        for norad in sorted(wanted):
            original = choose_newest(
                [records[id(ref)][norad] for ref in source_refs if norad in records[id(ref)]]
            )
            selected = choose_newest(
                [original]
                + [
                    records[id(ref)][norad]
                    for ref in latest_qualified
                    if norad in records[id(ref)]
                ]
            )
            candidates.append(
                {
                    "norad": norad,
                    "original_epoch_ns": original[0],
                    "selected_epoch_ns": selected[0],
                    "original_snapshot": original[2],
                    "selected_snapshot": selected[2],
                    "original_element_sha256": original[3],
                    "selected_element_sha256": selected[3],
                    "changed": original[3] != selected[3],
                    "epoch_advance_s": (selected[0] - original[0]) / 1e9,
                }
            )
        scans.append(
            {
                "index": index,
                "session": item["session_id"],
                "capture_start_utc_ns": capture_ns,
                "guard_cutoff_utc_ns": guard_ns,
                "unique_candidate_norads": len(wanted),
                "post_guard_archive_snapshots": interval_rows,
                "qualified_latest_provider_snapshots": [
                    {"provider": r.provider, "collected_utc_ns": r.collected_utc_ns, "digest": r.digest}
                    for r in latest_qualified
                ],
                "candidates": candidates,
            }
        )

    all_candidates = [row for scan in scans for row in scan["candidates"]]
    interval = [row for scan in scans for row in scan["post_guard_archive_snapshots"]]
    summary = {
        "scans": len(scans),
        "unique_candidate_occurrences": len(all_candidates),
        "post_guard_archive_snapshot_occurrences": len(interval),
        "completion_proof_qualified_snapshot_occurrences": sum(r["qualified"] for r in interval),
        "changed_candidate_occurrences": sum(r["changed"] for r in all_candidates),
        "newer_epoch_candidate_occurrences": sum(r["epoch_advance_s"] > 0 for r in all_candidates),
        "scans_changed": sum(any(r["changed"] for r in scan["candidates"]) for scan in scans),
    }
    result = {
        "schema": "ds11-additional12-causal-orbit-inventory/v1",
        "status": "read_only_metadata_inventory_complete",
        "position_fits_run": 0,
        "propagations_run": 0,
        "guard_seconds": 505,
        "selection": "newest per physical NORAD among latest exact source per provider",
        "completion_criterion": (
            "exact archive digest plus matching tle_collection provider status=published receipt; "
            "file birth/mtime and receipt all precede capture"
        ),
        "summary": summary,
        "completion_proof": {
            "schema": "ds11-capture-start-snapshot-completion-proof/v1",
            "qualified_snapshots": proof_rows,
        },
        "scans": scans,
        "limitations": [
            "Filesystem times and the local systemd journal are operational evidence, not signed external attestations.",
            "This eligibility inventory uses no propagation, measurements, fit results, or reference positions.",
        ],
        "source_sha256": {
            str(Path(__file__)): digest(Path(__file__)),
            str(plan_path): digest(plan_path),
            str(sidecar_path): digest(sidecar_path),
            str(args.journal_log): digest(args.journal_log),
            str(HILL / "causal_orbit_inventory/inventory.py"): digest(
                HILL / "causal_orbit_inventory/inventory.py"
            ),
            str(HILL / "orbit_age_audit/capture-start-completion-proof.json"): digest(
                HILL / "orbit_age_audit/capture-start-completion-proof.json"
            ),
            str(Path(inspect.getfile(TleArchiveReader))): digest(
                Path(inspect.getfile(TleArchiveReader))
            ),
            str(Path(inspect.getfile(parse_element_set_records))): digest(
                Path(inspect.getfile(parse_element_set_records))
            ),
            str(Path(inspect.getfile(tle_collector))): digest(Path(inspect.getfile(tle_collector))),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
