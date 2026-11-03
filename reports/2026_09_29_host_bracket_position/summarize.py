"""Score all declared panels, retaining missing and unqualified outcomes."""

import hashlib
import json
import math
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
reference_path = HERE.parent / "2026_09_29_unassociated_trend/summary.json"
source = json.loads(reference_path.read_text())
reference = source["reference"]


def distance(estimate):
    a, b = map(math.radians, reference)
    c, d = map(math.radians, estimate)
    h = math.sin((a - c) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((b - d) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))


rows = []
receipts = json.loads((HERE / "receipts.json").read_text())
assert len(receipts) == 9
for receipt in receipts:
    key = receipt["unit"]
    path = HERE / f"{key}.json"
    row = dict(unit=key, **{k: v for k, v in receipt.items() if k != "unit"}, audited=False)
    if not path.exists():
        rows.append(row)
        continue
    r = json.loads(path.read_text())
    for name, digest in r["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    base = next(v for v in source["rows"] if v["unit"] == key + "_q020")
    old_error = distance(r["baseline_estimate_deg"])
    assert abs(old_error - base["error_m"]) < 1e-4
    row.update(
        baseline_error_m=old_error,
        tracks=r["tracks"],
        qualified_starts=sum(s["qualified"] for s in r["starts"]),
        seconds=r["elapsed_seconds"],
    )
    s = r["selected"]
    if s is not None:
        old_rows = {(v["session_id"], v["track_id"]): v for v in r["baseline"]["rows"]}
        new_rows = {(v["session_id"], v["track_id"]): v for v in r["held"]["rows"]}
        assert set(old_rows) == set(new_rows)
        assert all(
            old_rows[k]["held_observations"] == new_rows[k]["held_observations"] for k in old_rows
        )
        row.update(
            audited=bool(
                r["audit"]["passed"] and receipt["exit_code"] == 0 and not receipt["timeout"]
            ),
            error_m=distance(s["estimate_deg"]),
            training_change_nats=s["score"] - r["baseline"]["score"],
            held_change_nats=sum(
                new_rows[k]["held_log_score"] - old_rows[k]["held_log_score"] for k in old_rows
            ),
            active_capture_bounds=s["active_capture_bounds"],
            bias_s=s["z"][2],
            projected_gradient=s["projected_gradient"],
            gradient_discrepancy=r["audit"]["max_gradient_difference"],
        )
    rows.append(row)
summary = {}
for ds in ("DS7", "DS8", "DS9"):
    group = [r for r in rows if r["unit"].startswith(ds)]
    valid = [r for r in group if r["audited"]]
    summary[ds] = dict(
        planned=3,
        audited=len(valid),
        baseline_median_m=median(r["baseline_error_m"] for r in group)
        if all("baseline_error_m" in r for r in group)
        else None,
        model_median_m=median(r["error_m"] for r in valid) if len(valid) == 3 else None,
    )
hashes = {
    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
    for p in [HERE / "summarize.py", HERE / "receipts.json"] + sorted(HERE.glob("DS*_8.json"))
}
hashes[str(reference_path.relative_to(ROOT))] = hashlib.sha256(
    reference_path.read_bytes()
).hexdigest()
(HERE / "summary.json").write_text(
    json.dumps(
        dict(reference=reference, hashes=hashes, rows=rows, datasets=summary),
        indent=2,
        allow_nan=False,
    )
    + "\n"
)
lines = [
    "| Panel | Baseline m | Bracket model m | Held change nats | Active capture bounds | Audit |",
    "|---|---:|---:|---:|---:|---|",
]
for r in rows:

    def fmt(k, r=r):
        return f"{r[k]:.2f}" if k in r else "—"

    lines.append(
        f"| {r['unit']} | {fmt('baseline_error_m')} | {fmt('error_m')} | "
        f"{fmt('held_change_nats')} | {r.get('active_capture_bounds', '—')} | "
        f"{'Pass' if r['audited'] else 'Unvalidated'} |"
    )
(HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
print(json.dumps(summary, indent=2))
