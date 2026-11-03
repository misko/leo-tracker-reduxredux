"""Verify bindings and count revision support without changing selection."""

import hashlib
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent


def main():
    result = json.loads((HERE / "results.json").read_text())
    for name, digest in result["hashes"].items():
        assert hashlib.sha256((HERE.parent.parent / name).read_bytes()).hexdigest() == digest
    rows = result["rows"]
    assert len({(r["unit_id"], r["session_id"], r["track_id"], r["number"]) for r in rows}) == 3983
    out = {}
    for ds in ("all", "DS7", "DS8", "DS9"):
        subset = [r for r in rows if ds == "all" or r["unit_id"].startswith(ds)]
        value = dict(cases=len(subset), scans=len({r["session_id"] for r in subset}))
        for label in ("latest", "older_6h", "older_24h"):
            present = [r for r in subset if r["products"][label]["record"]]
            ages = [r["products"][label]["element_age_hours"] for r in present]
            changed, changed_epoch, pairs = 0, 0, 0
            for r in present:
                latest = r["products"]["latest"]
                target = r["products"][label]
                latest_snapshot = result["snapshots"][latest["snapshot"]]
                snapshot = result["snapshots"][target["snapshot"]]
                assert latest_snapshot["collected_utc_ns"] < r["start_utc_ns"] - 505_000_000_000
                if label != "latest":
                    h = 6 if label == "older_6h" else 24
                    assert (
                        snapshot["collected_utc_ns"]
                        <= latest_snapshot["collected_utc_ns"] - h * 3600 * 10**9
                    )
                if latest["record"]:
                    pairs += 1
                    changed += (
                        latest["record"]["element_sha256"] != target["record"]["element_sha256"]
                    )
                    changed_epoch += latest["record"]["epoch_ns"] != target["record"]["epoch_ns"]
            value[label] = dict(
                present=len(present),
                paired_with_latest=pairs,
                changed_elements=changed,
                changed_epochs=changed_epoch,
                median_element_age_hours=median(ages) if ages else None,
                minimum_element_age_hours=min(ages) if ages else None,
                maximum_element_age_hours=max(ages) if ages else None,
                future_epochs=sum(a < 0 for a in ages),
            )
        out[ds] = value
    (HERE / "summary.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
