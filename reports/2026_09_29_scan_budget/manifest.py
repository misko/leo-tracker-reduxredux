import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def groups(rows, count):
    ordered = sorted(rows, key=lambda r: (r["start_utc_ns"], r["session_id"]))
    if len(ordered) != 24 or len({r["session_id"] for r in ordered}) != 24:
        raise ValueError("Require24 unique scans")
    if count == 8:
        return [ordered[i::3] for i in range(3)]
    if count == 12:
        return [ordered[i::2] for i in range(2)]
    if count == 16:
        return [[r for j, r in enumerate(ordered) if j % 3 != i] for i in range(3)]
    if count == 24:
        return [ordered]
    raise ValueError("Unsupported scan count")


def main():
    path = HERE.parent / "2026_09_29_time_balanced_scans/manifest.json"
    source = json.loads(path.read_text())
    for name, digest in source["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    sets = []
    for ds in ("DS7", "DS8", "DS9"):
        rows = [
            r
            for s in source["sets"]
            if s["dataset"] == ds and s["arm"] == "contiguous"
            for r in s["scans"]
        ]
        for count in (8, 12, 16, 24):
            for i, group in enumerate(groups(rows, count)):
                assert len(group) == count
                times = [r["start_utc_ns"] for r in group]
                sets.append(
                    dict(
                        unit=f"{ds}_n{count}_{i}",
                        dataset=ds,
                        count=count,
                        fold=i,
                        scans=group,
                        start_span_hours=(max(times) - min(times)) / 3.6e12,
                    )
                )
    paths = [path, HERE / "manifest.py", HERE / "PROTOCOL.md"]
    result = dict(
        config=source["config"],
        sets=sets,
        hashes={
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
        },
    )
    (HERE / "manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print("Frozen", len(sets), "sets;", sum(s["count"] != 8 for s in sets), "new fits")


if __name__ == "__main__":
    main()
