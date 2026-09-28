"""Outcome-independent proposal for equal-budget temporal coverage."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
folders = {
    "DS7": "2026_09_27_ds7_post_ds6",
    "DS8": "2026_09_28_ds8_post_ds7",
    "DS9": "2026_09_28_ds9_post_ds8",
}
panels = []
for ds, folder in folders.items():
    path = ROOT / "reports" / folder / "manifest.json"
    manifest = json.loads(path.read_text())
    captures = sorted(
        manifest["captures"], key=lambda c: (c["capture_start_utc_ns"], c["session_id"])
    )
    first, last = captures[0]["capture_start_utc_ns"], captures[-1]["capture_start_utc_ns"]
    # Integer arithmetic avoids timestamp rounding; selection precedes cache lookup.
    chosen = [
        min(
            captures,
            key=lambda c: (
                abs(7 * c["capture_start_utc_ns"] - ((7 - i) * first + i * last)),
                c["session_id"],
            ),
        )
        for i in range(8)
    ]
    assert len({c["session_id"] for c in chosen}) == 8
    panels.append(
        {
            "dataset": ds,
            "manifest_path": str(path.relative_to(ROOT)),
            "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "total_records": len(captures),
            "full_start_span_hours": (last - first) / 3.6e12,
            "first_eight_start_span_hours": (captures[7]["capture_start_utc_ns"] - first) / 3.6e12,
            "selected": [
                {
                    "session_id": c["session_id"],
                    "ordinal": captures.index(c) + 1,
                    "capture_start_utc_ns": c["capture_start_utc_ns"],
                    "sample_rate_hz": c["sample_rate_hz"],
                }
                for c in chosen
            ],
        }
    )

# Presence is only an inventory observation, not validation of a reusable bank.
listed = subprocess.check_output(
    ["rg", "--files", "--hidden", "--no-ignore", ".leo", "reports"], cwd=ROOT, text=True
).splitlines()
inventory = {}
for name in listed:
    if not name.endswith("/banks.npz"):
        continue
    path = ROOT / name
    manifest = path.parent / "manifest.json"
    if not manifest.exists():
        continue
    data = json.loads(manifest.read_text())
    if data.get("schema") != "ds7-baseline-bank-export/v1":
        continue
    inventory.setdefault(data["session_id"], []).append(
        {
            "bank_path": name,
            "bank_size_bytes": path.stat().st_size,
            "manifest_path": str(manifest.relative_to(ROOT)),
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        }
    )
for panel in panels:
    for capture in panel["selected"]:
        capture["unvalidated_bank_matches"] = sorted(
            inventory.get(capture["session_id"], []), key=lambda r: r["bank_path"]
        )
    panel["records_with_bank_matches"] = sum(
        bool(c["unvalidated_bank_matches"]) for c in panel["selected"]
    )
    for capture in panel["selected"]:
        for match in capture["unvalidated_bank_matches"]:
            snapshot = HERE / "coverage-manifests" / (match["manifest_sha256"] + ".json")
            snapshot.parent.mkdir(exist_ok=True)
            content = (ROOT / match["manifest_path"]).read_bytes()
            assert hashlib.sha256(content).hexdigest() == match["manifest_sha256"]
            snapshot.write_bytes(content)
            match["manifest_snapshot_path"] = str(snapshot.relative_to(ROOT))
result = {
    "rule": (
        "Nearest capture start to eight equally spaced timestamps including endpoints; "
        "ties by session_id; no model outcomes or cache availability enter selection."
    ),
    "inventory_scope": (
        "Existing banks.npz files beneath workspace .leo and reports; "
        "schema/session match only, not full bank/input validation."
    ),
    "panels": panels,
}
(HERE / "temporal-coverage-proposal.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps([{k: v for k, v in p.items() if k != "selected"} for p in panels], indent=2))
