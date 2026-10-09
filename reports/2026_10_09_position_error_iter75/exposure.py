"""Metadata and exact-ID exposure search; no localization values extracted."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OTHER = Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports")
ROOTS = (HERE.parent, OTHER)


def read(p):
    return json.loads(p.read_text())


manifest = read(HERE / "local/manifest.json")
parent_paths = {
    "DS16": OTHER / "2026_10_08_ds17_post_ds16/local/parent-manifest.json",
    "DS17": OTHER / "2026_10_08_ds18_post_ds17/local/parent-manifest.json",
    "DS18": OTHER / "2026_10_08_ds18_post_ds17/local/manifest.json",
}
disjoint = {}
for name, p in parent_paths.items():
    old = read(p)
    assert old["dataset_id"] == name
    overlaps = {
        k: sorted({r[k] for r in old["captures"]} & {r[k] for r in manifest["captures"]})
        for k in ("session_id", "uncompressed_sha256")
    }
    assert not any(overlaps.values())
    disjoint[name] = dict(
        members=len(old["captures"]),
        overlaps=overlaps,
        manifest_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
    )
rows = []
command = [
    sys.argv[1] if len(sys.argv) > 1 else "rg",
    "--only-matching",
    "--with-filename",
    "--fixed-strings",
    "--hidden",
    "--glob",
    "*.json",
    "--glob",
    "*.md",
    "--glob",
    "*.py",
    "--glob",
    "*.csv",
    "--glob",
    "!2026_10_09_position_error_iter75/**",
    "--glob",
    "!**/2026_10_09_position_error_iter75/**",
]
for row in manifest["captures"]:
    command.extend(["-e", row["session_id"]])
command.extend(str(p) for p in ROOTS)
result = subprocess.run(command, text=True, capture_output=True)
assert result.returncode in (0, 1), result.stderr
matches = {r["session_id"]: set() for r in manifest["captures"]}
for line in result.stdout.splitlines():
    path, sid = line.rsplit(":", 1)
    matches[sid].add(path)
for r in manifest["captures"]:
    paths = sorted(matches[r["session_id"]])
    assert all("position_error_iter75" not in p for p in paths)
    rows.append(
        {
            k: r[k]
            for k in (
                "dataset_label",
                "session_id",
                "capture_start_utc_ns",
                "finalized_utc_ns",
                "sample_rate_hz",
                "visits",
                "uncompressed_sha256",
                "recording_manifest_sha256",
            )
        }
        | dict(
            prior_matching_files=paths,
            exposure="prior file match; classify before validation"
            if paths
            else "no match in searched report text; independence not established",
        )
    )
receipt = dict(
    dataset_id=manifest["dataset_id"],
    window=manifest["capture_start_window_utc"],
    manifest_sha256=hashlib.sha256((HERE / "local/manifest.json").read_bytes()).hexdigest(),
    disjointness=disjoint,
    counts=manifest["counts"],
    members=rows,
    search_scope=[str(p) for p in ROOTS],
    search_limitations=(
        "rg default ignore rules apply; JSON/MD/Python/CSV text only, "
        "filename/session-ID pairs returned. "
        "No external notebooks, private conversations or other machines audited. "
        "Absence is not proof of independence."
    ),
    outcome_policy=(
        "No localization values extracted, inspected or used; "
        "not yet certified independent validation."
    ),
)
(HERE / "membership.json").write_text(json.dumps(receipt, indent=2) + "\n")
print(
    "Members",
    len(rows),
    "with prior filename matches",
    sum(bool(r["prior_matching_files"]) for r in rows),
)
