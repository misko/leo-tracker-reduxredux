import gzip
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "2026_10_06_rate64_edge_review" / "data"
OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(parents=True, exist_ok=True)
metrics = json.loads((BASE / "metrics.json").read_text())
audit = {
    r["session_id"]: r
    for r in json.loads(gzip.decompress((BASE / "edge-audit.json.gz").read_bytes()))
}
selected = []
for rate in (2500000, 10000000):
    for edge in ("lower", "upper"):
        recent = sorted(
            [r for r in metrics if r["rate"] == rate and r["edge"] == edge],
            key=lambda r: r["captured_at"],
            reverse=True,
        )[:8]
        ranked = sorted(recent, key=lambda r: r["glrt"]["pass_fraction"])
        dev = ranked[len(ranked) // 2]
        # Fixed hash order gives a new scan, independent of score within pool.
        evaluation = min(
            (r for r in recent if r["session_id"] != dev["session_id"]),
            key=lambda r: hashlib.sha256(
                ("20261006-edge-followup:" + r["session_id"]).encode()
            ).hexdigest(),
        )
        for split, scan in [("development", dev), ("evaluation", evaluation)]:
            a = audit[scan["session_id"]]
            examples = [
                {**v, "lane": k} for k, v in sorted(a["examples"].items()) if v["channel"] in (1, 4)
            ]
            selected.append(
                {
                    "split": split,
                    "session_id": scan["session_id"],
                    "rate": rate,
                    "edge": edge,
                    "captured_at": scan["captured_at"],
                    "examples": examples,
                }
            )
spec = {
    "schema": "report-only-rate64-followup-v1",
    "seed": 20261006,
    "scientific_source": "/opt/leo-adaptive-memory/9181d637d/src",
    "source_baseline": "9181d637d",
    "previous_report_commit": "956afb7d7b31bfdd000a6b07509ad3ed639bf55e",
    "selection": (
        "Original four diagnostic scans are development. A hash-selected different "
        "scan per rate/edge from the original recent-eight pool is evaluation. "
        "Examples are first strong and marginal published winners after 60 s in CH1/CH4. "
        "This is a selected-candidate diagnostic, not an unbiased detection evaluation."
    ),
    "gate": 0.025,
    "probe_ms": 20,
    "candidate_budget": 8,
    "bulk_root": "/srv/bulk/leo",
    "scans": selected,
}
(OUT / "experiment-spec.json").write_text(json.dumps(spec, indent=2) + "\n")
print([(r["split"], r["rate"], r["edge"], r["session_id"], len(r["examples"])) for r in selected])
