"""Bind explicit full DS18-029 replay to original128 inputs and failed receipt."""

import json

from replay import HERE, OLD, ROOT, original


def main():
    old = json.loads((OLD / "protocol.json").read_text())
    original.verify(old)
    member = next(m for m in old["members"] if m["label"] == "DS18-029")
    paths = {ROOT / name for name in old["source_sha256"]}
    paths.update(HERE.glob("*.py"))
    paths.update(
        [
            HERE / "README.md",
            HERE / "mapping-audit.json",
            OLD / "protocol.json",
            OLD / "results/DS18-029/result.json",
            OLD / "results/DS18-029/rows.jsonl",
        ]
    )
    plan = {
        "schema": "iter134-sparse-event-replay-v1",
        "member": member,
        "change": "map original event visit IDs to verified public reader ordinals",
        "maximum_case_seconds": old["maximum_case_seconds"],
        "source_sha256": {str(p.relative_to(ROOT)): original.digest(p) for p in sorted(paths)},
    }
    original.write_new(HERE / "protocol.json", plan)


if __name__ == "__main__":
    main()
