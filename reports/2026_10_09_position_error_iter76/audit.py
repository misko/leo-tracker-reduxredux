"""Frozen full148 extra-search flag audit; no new localization or exclusions."""

import hashlib
import json
from pathlib import Path

from policy import timing_metric, trigger

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(p):
    return json.loads(p.read_text())


def main():
    plan = read(HERE / "protocol.json")
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    if (HERE / "results.json").exists():
        raise FileExistsError("Preserve first full-cohort flag audit")
    cohort = read(ROOT / "reports/2026_10_09_position_error_iter65/snapshot.json")
    rows = []
    for source in cohort["cases"]:
        result = read(ROOT / source["result_source"])
        joint = result["upstream"]["stages"].get("joint-100", {})
        metrics = {arm: timing_metric(joint.get(arm)) for arm in ("fitted-c", "zero-c")}
        flags = {str(t): trigger(metrics, t) for t in plan["thresholds"]}
        # Only after flags are fixed do reference errors enter the audit record.
        rows.append(
            dict(
                member=source["member"],
                metrics=metrics,
                flags=flags,
                errors_km={a: source["arms"][a]["candidate"]["error_km"] for a in metrics},
            )
        )
    assert len(rows) == 148
    (HERE / "results.json").write_text(json.dumps(dict(rows=rows), indent=2) + "\n")
    print("Flagged all148 consumed members; no position result or membership changed")


if __name__ == "__main__":
    main()
