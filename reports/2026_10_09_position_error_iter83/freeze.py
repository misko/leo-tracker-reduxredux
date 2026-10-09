"""Freeze all148 policy decisions and source closure before new recovery fits."""

import datetime
import hashlib
import json
import sys
from pathlib import Path

# isort: off
from policy import needs_extra_search
import engine
# isort: on

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    assert not (HERE / "protocol.json").exists()
    old_path = HERE.parent / "2026_10_09_position_error_iter78/protocol.json"
    old = engine.read(old_path)
    files = {ROOT / p for p in old["source_sha256"]}
    files.add(old_path)
    members = []
    for binding in old["members"]:
        result = engine.read(ROOT / binding["result_source"])
        initial = result["upstream"]["stages"].get("joint-100", {})
        requested = needs_extra_search(initial)
        members.append(dict(binding, requested_extra_search=requested))
    files.update(HERE.glob("*.py"))
    files.add(HERE / "README.md")
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if filename and filename.endswith(".py"):
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT / "reports") or "/worker/src/leo/" in str(path):
                files.add(path)
    for name in ("protocol.json", "protocol.sha256", "freeze.py"):
        files.add(HERE.parent / "2026_10_08_position_error_iter01" / name)
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        members=members, shards=2, invocation_seconds=600,
        threshold=10, region_count=32, regional_seconds=20, association_seconds=60,
        common_fit_seconds=90, maximum_iterations=600,
        scope="Consumed full148 uniform triggered regional recovery; no independent validation",
        control="Fixed iteration65 pipeline with satellite-slope0.25; all148 retained",
        candidate="Trigger from initial joint-100 timing strain or missing/unqualified fits; "
        "shared ordinary inventory, common bank, proposals, continuation, bounded restarts. "
        "Qualified common-model winner if available, otherwise fixed prior fallback.",
        constraints="Reference coordinates/errors evaluation-only. No oracle starts, "
        "no error-based per-scan tuning, no comparison across different model scores. "
        "Matched c arms, all regional/input/fit failures retained. No RF/reserve outcome access.",
        execution="At most two single-thread workers; resume bounded invocations only after "
        "their authoritative handles terminate. Retain immutable receipts; no live source edits.",
        source_sha256={str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p):
                       hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},
    )
    assert len(members) == 148
    (HERE / "protocol.json").write_text(json.dumps(plan, indent=2) + "\n")
    print("members", len(members), "triggered", [b["member"]["inventory_label"]
                                                for b in members if b["requested_extra_search"]])


if __name__ == "__main__":
    main()
