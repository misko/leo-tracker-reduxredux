"""Freeze all post-DS21 fast and adaptive recordings without outcome gates."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from raw_inventory import digest, inventory


def legacy_member(row):
    outer = row["document"]
    d = outer.get("manifest", outer)
    if d.get("kind") != "starlink_adaptive_hop_iq":
        raise ValueError("unrecognized post-cutoff recording format: " + row["path"])
    receipt = d["receipt"]
    root = Path(row["path"]).parent
    identity = digest(
        json.dumps(
            sorted((c["compressed_sha256"], c["uncompressed_sha256"]) for c in d["chunks"])
        ).encode()
    )
    chunks, errors = [], []
    for c in d["chunks"]:
        item = dict(c, payload_path=str(root / c["relative_path"]))
        try:
            item["observed_payload_bytes"] = Path(item["payload_path"]).stat().st_size
            if item["observed_payload_bytes"] != c["compressed_bytes"]:
                errors.append("payload size mismatch: " + item["payload_path"])
        except OSError as e:
            errors.append(str(e))
        chunks.append(item)
    configured = sorted({p["target"]["channel"] for p in receipt["plan"]["geometry"]["profiles"]})
    return dict(
        case_id=d["session_id"] + "-" + identity[-12:],
        recording_id=d["session_id"],
        session_id=d["session_id"],
        session_ids=[d["session_id"]],
        channels=configured,
        observed_channels=configured,
        captured_utc_ns=(d.get("timing") or {}).get(
            "first_sample_estimate_utc_ns", d["created_utc_ns"]
        ),
        recording_state="complete" if receipt["terminal"]["reason"] == "complete" else "incomplete",
        recording_format="starlink_adaptive_hop_iq",
        window_count=len(receipt["retained_visit_indices"]),
        source_inputs=[],
        tracking_inputs=[],
        automatic_job=None,
        analysis_availability=(
            "not inventoried for adaptive format; explicitly unavailable in this snapshot"
        ),
        raw_recording=dict(
            identity_sha256=identity,
            root=str(root),
            duplicate_roots=[],
            segments=[row],
            chunks=chunks,
            integrity_errors=errors,
            iq_hash_verification="manifest_hashes_pinned_payload_sizes_checked_not_rehashed",
        ),
    )


def counts(members):
    return dict(
        members=len(members),
        complete=sum(r["recording_state"] == "complete" for r in members),
        incomplete=sum(r["recording_state"] != "complete" for r in members),
        fast_recordings=sum(
            r.get("recording_format") != "starlink_adaptive_hop_iq" for r in members
        ),
        adaptive_recordings=sum(
            r.get("recording_format") == "starlink_adaptive_hop_iq" for r in members
        ),
        with_tracking_input=sum(bool(r["tracking_inputs"]) for r in members),
        windows=sum(r["window_count"] for r in members),
        compressed_bytes=sum(
            c["compressed_bytes"] for r in members for c in r["raw_recording"]["chunks"]
        ),
        integrity_errors=sum(len(r["raw_recording"]["integrity_errors"]) for r in members),
    )


HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "2026_10_12_ds21_post_ds20" / "local"


def write(path, document):
    path.write_text(json.dumps(document, indent=2, allow_nan=False) + "\n")


def legacy_census(start, end):
    """Bounded metadata reads; include non-fast captures without quality gates."""
    roots = [
        Path("/srv/bulk/leo") / n
        for n in (
            "scanner-adaptive-recordings",
            "scanner-recordings",
            "scanner-hop-recordings",
            "native-recordings",
            "recordings",
        )
    ] + [Path("/srv/postgres-nvme/leo-scanner-spool")]
    result = {"roots": [str(p) for p in roots], "members": [], "errors": [], "checked": {}}
    for root in roots:
        count = 0
        try:
            for path in root.rglob("manifest.json"):
                count += 1
                with path.open("rb") as f:
                    prefix = f.read(16384)
                    f.seek(max(0, path.stat().st_size - 16384))
                    suffix = f.read()
                times = re.findall(rb'"first_sample_estimate_utc_ns"\s*:\s*(\d+)', suffix)
                if not times:
                    times = re.findall(rb'"created_utc_ns"\s*:\s*(\d+)', prefix + suffix)
                if not times:
                    document = json.loads(path.read_bytes())
                    document = document.get("manifest", document)
                    stamp = document.get("created_utc_ns")
                    if stamp is None:
                        result["errors"].append({"path": str(path), "reason": "no_capture_time"})
                        continue
                    times = [str(stamp).encode()]
                if start <= int(times[0]) <= end:
                    raw = path.read_bytes()
                    result["members"].append(
                        {"path": str(path), "sha256": digest(raw), "document": json.loads(raw)}
                    )
        except OSError as e:
            result["errors"].append({"root": str(root), "error": str(e)})
        result["checked"][str(root)] = count
    return result


def verify(root):
    seal = json.loads((root / "seal.json").read_bytes())
    for name, sha in seal["files"].items():
        if digest((root / name).read_bytes()) != sha:
            raise ValueError("seal mismatch: " + name)
    m = json.loads((root / "manifest.json").read_bytes())
    parent = json.loads((root / "parent-manifest.json").read_bytes())
    if (
        m["dataset_id"] != "DS22"
        or parent["dataset_id"] != "DS21"
        or m["start_utc_ns"] != parent["cutoff_utc_ns"]
    ):
        raise ValueError("parent boundary mismatch")
    identities = [r["raw_recording"]["identity_sha256"] for r in m["members"]]
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate acquisition")
    if set(identities) & {r["raw_recording"]["identity_sha256"] for r in parent["members"]}:
        raise ValueError("parent overlap")
    for r in m["members"]:
        if not m["start_utc_ns"] < r["captured_utc_ns"] <= m["cutoff_utc_ns"]:
            raise ValueError("outside frozen window")
        for item in r["source_inputs"] + r["tracking_inputs"] + r["raw_recording"]["segments"]:
            if digest((root / item["snapshot"]).read_bytes()) != item["sha256"]:
                raise ValueError("analysis snapshot mismatch")
    units = json.loads((root / "evaluation-units.json").read_bytes())
    if units["case_ids"] != [r["case_id"] for r in m["members"]]:
        raise ValueError("evaluation membership mismatch")
    if counts(m["members"]) != m["counts"]:
        raise ValueError("count mismatch")
    return {
        "verified": True,
        "manifest_sha256": digest((root / "manifest.json").read_bytes()),
        **m["counts"],
    }


def mint(output, cutoff):
    if output.exists():
        raise ValueError("refusing to overwrite a mint")
    parent_raw = (PARENT / "manifest.json").read_bytes()
    parent = json.loads(parent_raw)
    if parent["dataset_id"] != "DS21":
        raise ValueError("expected DS21 parent")
    expected = (PARENT / "manifest.sha256").read_text().split()[0]
    if digest(parent_raw) != expected:
        raise ValueError("parent digest mismatch")
    start = parent["cutoff_utc_ns"]
    roots = [Path(p) for p in parent["discovery_roots"]]
    # Discover sibling raw recording collections added after the parent mint.
    for base in (Path("/srv/bulk/leo"), Path("/srv/postgres-nvme")):
        roots.extend(
            p
            for p in base.iterdir()
            if p.is_dir() and p.name.startswith(("fast8-", "fast-scan-recordings"))
        )
    roots = sorted(set(roots))
    result = inventory(
        roots,
        Path("/srv/bulk/leo"),
        cutoff,
        start_ns=start + 1,
        dataset_id="DS22",
        required_channels=None,
    )
    result["start_utc_ns"] = start
    result["start_utc"] = datetime.fromtimestamp(start / 1e9, UTC).isoformat()
    result["parent_dataset"] = "DS21"
    result["parent_manifest_sha256"] = digest(parent_raw)
    result["selection"] = (
        "All discovered raw acquisitions starting strictly after DS21 cutoff "
        "through frozen DS22 cutoff; incomplete retained; no channel, signal, "
        "analysis or position gate."
    )
    census = legacy_census(start + 1, cutoff)
    if census["errors"]:
        raise ValueError(
            "legacy census needs reconciliation: " + json.dumps(census, default=str)[:4000]
        )
    identities = {r["raw_recording"]["identity_sha256"]: r for r in result["members"]}
    for row in census["members"]:
        member = legacy_member(row)
        key = member["raw_recording"]["identity_sha256"]
        if key in identities:
            identities[key]["raw_recording"]["duplicate_roots"].append(
                member["raw_recording"]["root"]
            )
        else:
            identities[key] = member
    result["members"] = sorted(
        identities.values(), key=lambda r: (r["captured_utc_ns"], r["case_id"])
    )
    census["members"] = [{"path": r["path"], "sha256": r["sha256"]} for r in census["members"]]
    if result["discovery_errors"]:
        raise ValueError("raw discovery errors: " + json.dumps(result["discovery_errors"]))
    output.mkdir(parents=True)
    (output / "analysis").mkdir()
    (output / "parent-manifest.json").write_bytes(parent_raw)
    (output / "parent-manifest.sha256").write_bytes((PARENT / "manifest.sha256").read_bytes())
    for name in ("mint.py", "raw_inventory.py", "test_mint.py"):
        (output / name).write_bytes((HERE / name).read_bytes())
    for number, member in enumerate(result["members"], 1):
        member["dataset_label"] = f"DS22-{number:03}"
        for item in (
            member["source_inputs"]
            + member["tracking_inputs"]
            + member["raw_recording"]["segments"]
        ):
            raw = Path(item["path"]).read_bytes()
            if digest(raw) != item["sha256"]:
                raise ValueError("source changed during inventory: " + item["path"])
            name = "analysis/" + item["sha256"].removeprefix("sha256:") + ".json"
            (output / name).write_bytes(raw)
            item["snapshot"] = name
    result["counts"] = counts(result["members"])
    write(output / "legacy-census.json", census)
    write(output / "manifest.json", result)
    write(
        output / "evaluation-units.json",
        {
            "dataset_id": "DS22",
            "case_ids": [r["case_id"] for r in result["members"]],
            "manifest_sha256": digest((output / "manifest.json").read_bytes()),
        },
    )
    (output / "manifest.sha256").write_text(
        digest((output / "manifest.json").read_bytes()) + "  manifest.json\n"
    )
    write(
        output / "seal.json",
        {
            "dataset_id": "DS22",
            "files": {
                str(p.relative_to(output)): digest(p.read_bytes())
                for p in sorted(output.rglob("*"))
                if p.is_file()
            },
        },
    )
    write(output.parent / "verification.json", verify(output))
    print(json.dumps(verify(output)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["mint", "verify"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cutoff-ns", type=int)
    args = parser.parse_args()
    if args.action == "mint":
        if args.cutoff_ns is None:
            parser.error("--cutoff-ns required")
        mint(args.output, args.cutoff_ns)
    else:
        print(json.dumps(verify(args.output)))
