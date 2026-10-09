"""Merge sealed subset reports after verifying all current phase receipt hashes."""

import hashlib
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def validate_membership(labels, rows, hashes):
    assert len(labels) == len(set(labels)) == len(rows) == 193
    assert set(labels) == set(rows) and len(hashes) == 386
    assert all(row["paired_terminal"] for row in rows.values())


def validate_bindings(members, rows, label_function):
    for member in members:
        payload = member["member"]
        row = rows[label_function(member)]
        assert row["dataset"] == member.get("dataset", payload.get("dataset"))
        assert row["session_id"] == payload["session_id"]
        assert row["exposure"] == payload.get("exposure")
        assert row["loader_kind"] == member.get("kind")


def main():
    report = runpy.run_path(str(HERE / "report.py"))
    plan = json.loads((HERE / "protocol.json").read_text())
    digest = sha(HERE / "protocol.json")
    rows, hashes, sources = {}, {}, {}
    for stem in ("DS16", "DS17", "DS18", "NEWER45"):
        path = HERE / (stem + "_COMPLETE_SNAPSHOT.json")
        data = json.loads(path.read_text())
        assert data["protocol_sha256"] == digest
        assert not data["metrics"]["full_census_position_metrics_withheld"]
        sources[path.name] = sha(path)
        for row in data["rows"]:
            assert row["paired_terminal"] and row["label"] not in rows
            rows[row["label"]] = row
        for name, value in data["receipt_sha256"].items():
            assert name not in hashes
            assert sha(Path(name)) == value, "Current receipt differs from sealed subset"
            hashes[name] = value
    labels = [report["member_label"](m) for m in plan["members"]]
    validate_membership(labels, rows, hashes)
    validate_bindings(plan["members"], rows, report["member_label"])
    ordered = [rows[label] for label in labels]
    for row in ordered:
        row["runtime"] = report["slice_metrics"](HERE / "results" / row["label"], digest)
    result = {
        "scope": "Full193 completed consumed development snapshot",
        "protocol_sha256": digest,
        "rows": ordered,
        "metrics": report["aggregate"](ordered),
        "datasets": {
            d: report["aggregate"]([r for r in ordered if r["dataset"] == d])
            for d in sorted({r["dataset"] for r in ordered})
        },
        "receipt_sha256": hashes,
        "subset_snapshot_sha256": sources,
        "receipt_hashes_reverified": True,
        "frozen_member_bindings_reverified": True,
        "reporting_method": "Sealed subset merge; no repeated reference or recording access",
    }
    (HERE / "FULL193_COMPLETE_SNAPSHOT.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n"
    )


if __name__ == "__main__":
    main()
