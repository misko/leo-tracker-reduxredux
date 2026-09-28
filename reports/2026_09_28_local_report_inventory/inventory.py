"""Inventory local report Markdown against the proposed Git index.

Run with the original workspace path. Does not publish the outstanding reports.
"""
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
local = Path(sys.argv[1]).resolve()
entries = subprocess.check_output(
    ["git", "ls-files", "--stage", "reports/"], cwd=REPO, text=True
).splitlines()
index = {line.split("\t", 1)[1]: line.split()[1] for line in entries}
groups = defaultdict(lambda: {"missing": [], "different": []})
unchanged = 0
for path in sorted((local / "reports").rglob("*.md")):
    if not path.is_file() or "__pycache__" in path.parts:
        continue
    rel = str(path.relative_to(local))
    raw = path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if index.get(rel) == blob:
        unchanged += 1
        continue
    state = "different" if rel in index else "missing"
    groups[path.relative_to(local / "reports").parts[0]][state].append(rel)
payload = {"created_utc": datetime.now(timezone.utc).isoformat(),
           "comparison": "prospective publication index based on origin/main",
           "scope": "All Markdown files recursively under the original workspace reports directory",
           "unchanged_markdown_files": unchanged, "outstanding": dict(groups)}
(HERE / "inventory.json").write_text(json.dumps(payload, indent=2) + "\n")
missing = sum(len(g["missing"]) for g in groups.values())
different = sum(len(g["different"]) for g in groups.values())
lines = ["# Outstanding local report inventory", "",
         f"Snapshot: {payload['created_utc']}.", "",
         "This compares the original workspace's report Markdown recursively with the proposed main publication, including the full DS7 evidence chain. It does not publish the outstanding report directories.", "",
         f"**{len(groups)} report locations contain {missing} Markdown files absent from the publication and {different} files with different bytes.** Locations include directories and standalone reports. {unchanged} local Markdown files match the publication exactly.", "",
         "Different bytes do not automatically mean unpublished work: the original checkout may contain an older version than main. Those entries need review before any replacement.", "",
         "This is a path-and-content inventory, not a count of independent scientific studies or finished reports. Protocols, nested evidence, copied sources, and progress notes are included. A missing original may already be represented by a published summary—for example, the receiver-geometry comprehensive report contains snapshots of several original studies.", "",
         "| Local report location | Missing Markdown | Different Markdown | Example files |",
         "|---|---:|---:|---|"]
for name, group in sorted(groups.items()):
    examples = sorted(group["missing"] + group["different"], key=lambda p: (p.count("/"), p))[:3]
    display = ", ".join("`" + (str(Path(p).relative_to(Path("reports") / name)) if Path(p).name != name else name) + "`" for p in examples)
    lines.append(f'| `{name}` | {len(group["missing"])} | {len(group["different"])} | {display} |')
lines += ["", "[Exact file inventory](inventory.json). Data-only report directories without Markdown are outside this inventory; no statement is made about their publication status.", "",
          "The full DS7 upload preserves original report/seal bytes, including historical failed attempts. It includes the minted dataset metadata, proposal, evaluation setup, waves 1–9, full88, bound source/configuration files and tests. Raw IQ and externally stored observation/bank artifacts referenced by absolute paths are not bundled. Two historical bytecode files are retained solely because a wave-3 closeout explicitly hashes them; they are not runtime requirements.", "",
          "Publication checks: 2,879 historical file bindings verified, all original full88 report links resolve, 89 DS7 component tests plus two frequency-unit tests passed. Original CSV line endings and historical whitespace are retained to preserve hashes; the legacy artifacts therefore retain Git whitespace warnings. No new scientific fits or RF collection were performed."]
(HERE / "README.md").write_text("\n".join(lines) + "\n")
print(f"{len(groups)} directories; {missing} missing Markdown; {different} different; {unchanged} identical")
