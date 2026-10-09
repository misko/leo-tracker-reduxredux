"""Freeze complete membership, archived region inputs and executable sources."""

import datetime
import hashlib
import json
import sys
from pathlib import Path

import evaluate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    assert not (HERE / "protocol.json").exists()
    old_path = HERE.parent / "2026_10_09_position_error_iter78/protocol.json"
    old = json.loads(old_path.read_text())
    files = {ROOT / p for p in old["source_sha256"]}
    files.add(old_path)
    files.add(HERE.parent / "2026_10_09_position_error_iter65/snapshot.json")
    members = []
    for binding in old["members"]:
        path = ROOT / binding["result_source"]
        result = json.loads(path.read_text())
        assert result["status"] == "complete"
        regions = {}
        for name in ("sep25", "sep50"):
            receipt = result["region_receipts"][name]
            source = (
                ROOT / receipt["path"]
                if receipt["mode"] == "archived"
                else (
                    path.parent.parent
                    / "regions"
                    / binding["member"]["inventory_label"]
                    / f"{name}.json"
                )
            )
            assert source.exists()
            regions[name] = str(source.relative_to(ROOT))
            files.add(source)
        members.append(dict(binding, regions=regions))
    files.update(HERE.glob("*.py"))
    files.add(HERE / "README.md")
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if filename and filename.endswith(".py"):
            path = Path(filename).resolve()
            if path.is_relative_to(ROOT / "reports") or "/worker/src/leo/" in str(path):
                files.add(path)
    plan = dict(
        frozen_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        members=members,
        stages=evaluate.STAGES,
        shards=2,
        seconds=90,
        iterations=600,
        membership="DS16 63 including48+15; DS17 51; DS18 34 including24+10 consumed",
        policy="README.md frozen; no truth-guided operational choice; same-start controls",
        baseline="Verified immutable deployed hard60 and regional replay receipts, not cold rerun",
        fits="Fresh downstream matched c0/fitted-c; RF off for c0, C5 RF off even with fitted-c",
        failures="Raw failures retain specified upstream fallback; missing prerequisites explicit",
        validation="Consumed development; no reserve outcomes, RF collection or deployment",
        source_sha256={
            str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in sorted(files)
        },
    )
    assert len(members) == 148
    (HERE / "protocol.json").write_text(json.dumps(plan, indent=2) + "\n")
    print("Frozen", len(members), "members", len(files), "input/source hashes")


if __name__ == "__main__":
    main()
