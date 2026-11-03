import json
import math

from run import HERE, REPORTS, ROOT, read, sha


def distance(a, b):
    p, q, r, s = map(math.radians, [*a, *b])
    return (
        2
        * 6371008.8
        * math.asin(
            math.sqrt(
                math.sin((p - r) / 2) ** 2 + math.cos(p) * math.cos(r) * math.sin((q - s) / 2) ** 2
            )
        )
    )


def main():
    for name, h in read(HERE / "manifest.json")["hashes"].items():
        assert sha(ROOT / name) == h, name
    refpath = REPORTS / "2026_09_29_unassociated_trend/summary.json"
    reference = read(refpath)["reference"]
    rows, failures = [], []
    for ds in ("DS7", "DS8", "DS9"):
        receipt = read(HERE / f"{ds}.receipt.json")
        if receipt["exit_code"] != 0:
            failures.append(dict(dataset=ds, receipt=receipt))
            continue
        r = read(HERE / f"{ds}.json")
        assert r["manifest_sha256"] == sha(HERE / "manifest.json")
        assert len(r["targets"]) == 8
        assert not set(r["source_sessions"]) & {t["session_id"] for t in r["targets"]}
        scores = {
            name: sum(t["scores"][name]["log_score"] for t in r["targets"])
            for name in ("early", "middle", "cumulative")
        }
        deltas = {
            f"{a}_minus_{b}": [
                t["scores"][a]["log_score"] - t["scores"][b]["log_score"] for t in r["targets"]
            ]
            for a, b in (("middle", "early"), ("cumulative", "early"), ("cumulative", "middle"))
        }
        checks = [v for t in r["targets"] for v in t["scores"].values()]
        source = read(HERE / f"{ds}.source.json")
        rows.append(
            dict(
                dataset=ds,
                qualified=all(v["qualified"] for v in checks),
                reference_errors_m={
                    name: distance(a["estimate_deg"], reference) for name, a in r["arms"].items()
                },
                scores=scores,
                differences={k: sum(v) for k, v in deltas.items()},
                wins={k: sum(x > 0 for x in v) for k, v in deltas.items()},
                per_target_differences=deltas,
                max_quadrature_difference=max(v["quadrature_difference"] for v in checks),
                refinements=sum("initial" in v for v in checks),
                qualified_source_starts=sum(s["qualified"] for s in source["starts"]),
                elapsed_seconds=r["elapsed_seconds"],
            )
        )
    result = dict(
        rows=rows, failures=failures, reference=reference, reference_source_sha256=sha(refpath)
    )
    with (HERE / "summary.json").open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
