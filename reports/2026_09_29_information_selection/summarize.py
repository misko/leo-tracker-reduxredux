import hashlib
import json
import math
import statistics
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(p):
    return json.loads(p.read_text())


def error(point, reference):
    a, b, c, d = map(math.radians, [*point, *reference])
    return (
        2
        * 6371008.8
        * math.asin(
            math.sqrt(
                math.sin((a - c) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((b - d) / 2) ** 2
            )
        )
    )


def main():
    manifest = read(HERE / "manifest.json")
    for name, h in manifest["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
    poolmanifest = read(HERE.parent / "2026_09_29_scan_budget/manifest.json")
    refpath = HERE.parent / "2026_09_29_unassociated_trend/summary.json"
    reference = read(refpath)["reference"]
    rows, failures = [], []
    for ds in ("DS7", "DS8", "DS9"):
        receipt = read(HERE / f"{ds}.receipt.json")
        if receipt["exit_code"] != 0:
            failures.append(dict(dataset=ds, receipt=receipt))
            continue
        r = read(HERE / f"{ds}.json")
        assert (
            r["manifest_sha256"]
            == hashlib.sha256((HERE / "manifest.json").read_bytes()).hexdigest()
        )
        if r["selected"] is None:
            failures.append(dict(dataset=ds, reason="No qualified optimizer endpoint"))
            continue
        pool = next(s for s in poolmanifest["sets"] if s["dataset"] == ds and s["count"] == 24)
        ids = [s["input"]["session_id"] for s in pool["scans"]]
        assert [ids[i] for i in r["selected_indices"]] == r["selected_sessions"]
        matrices = np.array(r["information"])
        selected_info = matrices[r["selected_indices"]].sum(axis=0)
        controls = []
        for i in range(3):
            old = read(HERE.parent / f"2026_09_29_time_balanced_scans/grid_{ds}_balanced_{i}.json")
            assert old["selected"]["qualified"]
            indices = [ids.index(s) for s in old["sessions"]]
            info = matrices[indices].sum(axis=0)
            controls.append(
                dict(
                    index=i,
                    error_m=error(old["selected"]["estimate_deg"], reference),
                    determinant_ratio=float(np.linalg.det(selected_info) / np.linalg.det(info)),
                    weak_information_ratio=float(
                        np.linalg.eigvalsh(selected_info)[0] / np.linalg.eigvalsh(info)[0]
                    ),
                    target_delta=sum(t["n8_deltas"][i] for t in r["targets"]),
                )
            )
        assert len(r["targets"]) == 5
        times = [pool["scans"][i]["start_utc_ns"] for i in r["selected_indices"]]
        rows.append(
            dict(
                dataset=ds,
                qualified=all(t["result"]["qualified"] for t in r["targets"]),
                selected_error_m=error(r["selected"]["estimate_deg"], reference),
                balanced_median_error_m=statistics.median(c["error_m"] for c in controls),
                controls=controls,
                n24_score_delta=sum(t["n24_delta"] for t in r["targets"]),
                n8_mixture_delta=sum(t["n8_mixture_delta"] for t in r["targets"]),
                n8_mean_score_delta=statistics.mean(c["target_delta"] for c in controls),
                span_hours=(max(times) - min(times)) / 3.6e12,
                matrix_discrepancy=r["matrix_discrepancy"],
                qualified_starts=sum(s["qualified"] for s in r["starts"]),
                elapsed_seconds=r["elapsed_seconds"],
            )
        )
    result = dict(
        rows=rows,
        failures=failures,
        reference=reference,
        reference_source_sha256=hashlib.sha256(refpath.read_bytes()).hexdigest(),
    )
    with (HERE / "summary.json").open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
