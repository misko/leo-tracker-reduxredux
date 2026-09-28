"""Export the reviewed report backlog without replacing existing main content.

Usage: python export.py ORIGINAL_WORKSPACE
This copies evidence only; it never runs analysis, RF, deployment or recovery.
"""
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEST = HERE.parents[1]
SOURCE = Path(sys.argv[1]).resolve()
inventory = json.loads((DEST / "reports/2026_09_28_local_report_inventory/inventory.json").read_text())
remote = set(subprocess.check_output(
    ["git", "ls-tree", "-r", "--name-only", "origin/main"], cwd=DEST, text=True
).splitlines())
text_extensions = {".md", ".json", ".csv", ".tsv", ".txt", ".py", ".c", ".h", ".inc",
                   ".patch", ".png", ".svg", ".html", ".js", ".sh", ".sha256"}
named = {"SHA256SUMS", "SOURCE_LOCK", "SOURCES.sha256", ".gitignore"}
copied, omitted, existing, missing = {}, {}, [], []


def reason(path):
    parts = path.relative_to(SOURCE).parts
    name = path.name.lower()
    if path.suffix == ".md":
        return None
    if "2026_09_27_ds7_satellite_annotations" in parts and name in ("inputs.json", "table-script.js"):
        return "host-specific preparation index or redundant HTML-generation intermediate"
    if "2026_09_28_ds8_post_ds7" in parts and "local" in parts:
        return "unsealed mint intermediate; complete sealed metadata retained"
    if any(p in parts for p in ("__pycache__", ".pytest_cache", "build", "work", "vendor")):
        return "working/cache/build artifact"
    if path.suffix not in text_extensions and path.name not in named:
        return "raw/derived numerical array, binary, log or working artifact"
    if "2026_09_28_ds7_glrt_benchmark" in parts:
        return "active benchmark; only the reviewed scoring specification is published"
    if "2026_09_27_sac_reno_last24" in parts and path.suffix == ".json":
        return "large API snapshot; publish timestamped tables/CSVs and retain source snapshot locally"
    if "2026_09_27_plutoplus_static_arm" in parts and path.suffix == ".json":
        if not any(k in name for k in ("summary", "validation", "assessment", "audit", "comparison", "receipt", "results", "manifest", "config")):
            return "per-case performance shard; summarized by retained report/receipts"
    if "2026_09_27_server_scan_speed" in parts and name == "paired-full.json":
        return "full per-case performance shard; paired summary retained"
    if "partial" in name and path.suffix == ".json":
        return "partial working output; final evidence and failure reports retained"
    if path.stat().st_size > 50_000_000:
        return "large working artifact; retained locally"
    return None


def copy(path, direct_link=False):
    rel = str(path.relative_to(SOURCE))
    if rel in remote:
        existing.append(rel)
        return
    if rel in copied:
        return
    why = reason(path)
    if why:
        omitted[rel] = {"reason": why, "bytes": path.stat().st_size}
        return
    data = path.read_bytes()
    out = DEST / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, out)
    copied[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                   "source_mtime_ns": path.stat().st_mtime_ns}


for group, entries in inventory["outstanding"].items():
    if not entries["missing"]:
        continue
    root = SOURCE / "reports" / group
    paths = [root] if root.is_file() else sorted(root.rglob("*"))
    for path in paths:
        if path.is_file():
            if group == "2026_09_28_ds7_glrt_benchmark" and path.name != "SCORING.md":
                omitted[str(path.relative_to(SOURCE))] = {"reason": "active work outside the reviewed backlog", "bytes": path.stat().st_size}
            else:
                copy(path)

# Include repository-relative report/document dependencies when available;
# never copy external paths or live runtime changes implicitly.
checked = set()
while True:
    pending = [p for p in copied if p.endswith(".md") and p not in checked]
    if not pending:
        break
    for rel in pending:
        checked.add(rel)
        for target in re.findall(r"\]\(([^)]+)\)", (SOURCE / rel).read_text()):
            target = target.split("#", 1)[0].strip("<>")
            if not target or "://" in target or target.startswith("/"):
                continue
            path = ((SOURCE / rel).parent / target).resolve()
            if not path.is_relative_to(SOURCE):
                continue
            relative = str(path.relative_to(SOURCE))
            if relative in remote or relative in copied:
                continue
            if path.is_file() and relative.startswith(("reports/", "docs/")):
                copy(path, direct_link=True)
            elif not path.exists():
                missing.append({"report": rel, "target": target})

for rel, item in copied.items():
    assert hashlib.sha256((DEST / rel).read_bytes()).hexdigest() == item["sha256"]
required = [p for g in inventory["outstanding"].values() for p in g["missing"]]
assert all(p in copied or p in remote for p in required)
payload = {"created_utc": datetime.now(timezone.utc).isoformat(),
           "scope": "129 reviewed missing Markdown files plus selected supporting evidence and available documentation dependencies",
           "source_workspace": str(SOURCE), "files": copied, "omitted": omitted,
           "already_on_main_preserved": sorted(set(existing)),
           "unresolved_relative_links": missing,
           "raw_iq_read": False, "scientific_fits_run": False}
(HERE / "publication-manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
print(json.dumps({"copied_files": len(copied), "copied_MB": sum(v["bytes"] for v in copied.values()) / 1e6,
                  "omitted_files": len(omitted), "unresolved_links": missing}, indent=2))
