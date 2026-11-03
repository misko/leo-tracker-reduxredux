import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent


def balanced(rows):
    if len(rows) != 24 or len({r["session_id"] for r in rows}) != 24:
        raise ValueError("Require24 unique scans")
    ordered = sorted(rows, key=lambda r: (r["start_utc_ns"], r["session_id"]))
    groups = [ordered[i::3] for i in range(3)]
    assert all(len(g) == 8 for g in groups)
    for group in groups:
        assert all(
            sum(r["window"] == w for r in group) in (2, 3) for w in ("early", "middle", "late")
        )
    return groups


def main():
    source = HERE.parent / "2026_09_29_donor_residual_transfer/plan.json"
    plan = json.loads(source.read_text())
    sets, hashes = (
        [],
        {str(source.relative_to(ROOT)): hashlib.sha256(source.read_bytes()).hexdigest()},
    )
    for ds in (7, 8, 9):
        rows = []
        for window in ("early", "middle", "late"):
            unit = next(u for u in plan["units"] if u["unit_id"] == f"DS{ds}_{window}_8")
            selected = []
            for entry in unit["group"]["inputs"]:
                artifact = next(a for a in entry["artifacts"] if a["kind"] == "observations")
                path = Path(artifact["path"])
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                assert "sha256:" + digest == artifact["sha256"]
                hashes[str(path.relative_to(ROOT))] = digest
                doc = json.loads(path.read_text())
                row = dict(
                    session_id=doc["session_id"],
                    start_utc_ns=doc["start_utc_ns"],
                    window=window,
                    input=entry,
                )
                rows.append(row)
                selected.append(row)
            sets.append(
                dict(
                    unit=f"DS{ds}_contiguous_{window}",
                    dataset=f"DS{ds}",
                    arm="contiguous",
                    scans=selected,
                )
            )
        for i, group in enumerate(balanced(rows)):
            sets.append(
                dict(unit=f"DS{ds}_balanced_{i}", dataset=f"DS{ds}", arm="balanced", scans=group)
            )
    for unit in sets:
        times = [r["start_utc_ns"] for r in unit["scans"]]
        unit["start_span_hours"] = (max(times) - min(times)) / 3.6e12
    paths = [HERE / "manifest.py", HERE / "PROTOCOL.md"]
    hashes.update(
        {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    )
    (HERE / "manifest.json").write_text(
        json.dumps(dict(config=plan["config"], sets=sets, hashes=hashes), indent=2) + "\n"
    )
    print([(s["unit"], round(s["start_span_hours"], 3)) for s in sets])


if __name__ == "__main__":
    main()
