import hashlib
import math

from run import HERE, REPORTS, ROOT, read


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
    import json

    manifest = read(HERE / "manifest.json")
    for name, h in manifest["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == h, name
    refpath = REPORTS / "2026_09_29_unassociated_trend/summary.json"
    reference = read(refpath)["reference"]
    rows, failures = [], []
    for unit in manifest["units"]:
        ds = unit["dataset"]
        receipt = read(HERE / f"{ds}.receipt.json")
        if receipt["exit_code"] != 0:
            failures.append(dict(dataset=ds, receipt=receipt))
            continue
        r = read(HERE / f"{ds}.json")
        assert (
            r["manifest_sha256"]
            == hashlib.sha256((HERE / "manifest.json").read_bytes()).hexdigest()
        )
        assert r["selection"]["examined"] == 495
        assert [t["unit"] for t in r["targets"]] == [t["unit"] for t in unit["targets"]]
        assert all(t["start_utc_ns"] > unit["source_end_utc_ns"] for t in r["targets"])
        arms = dict(
            prefix8=r["prefix8"],
            prefix12=r["scout"]["selected"],
            selected8=r["reduced"]["selected"],
        )
        totals = {arm: sum(t["scores"][arm]["log_score"] for t in r["targets"]) for arm in arms}
        checks = [v for t in r["targets"] for v in t["scores"].values()]
        rows.append(
            dict(
                dataset=ds,
                qualified=all(v["qualified"] for v in checks),
                errors_m={
                    arm: distance(value["estimate_deg"], reference) for arm, value in arms.items()
                },
                compression_shift_m=distance(
                    arms["prefix12"]["estimate_deg"], arms["selected8"]["estimate_deg"]
                ),
                target_count=len(r["targets"]),
                target_scores=totals,
                selected_minus_prefix12=totals["selected8"] - totals["prefix12"],
                selected_minus_prefix8=totals["selected8"] - totals["prefix8"],
                prefix12_minus_prefix8=totals["prefix12"] - totals["prefix8"],
                source_span_hours=(
                    unit["scans"][-1]["start_utc_ns"] - unit["scans"][0]["start_utc_ns"]
                )
                / 3.6e12,
                qualified_starts=sum(
                    s["qualified"] for arm in ("scout", "reduced") for s in r[arm]["starts"]
                ),
                max_quad=max(v["quadrature_difference"] for v in checks),
                refinements=sum("initial" in v for v in checks),
                elapsed_seconds=r["elapsed_seconds"],
            )
        )
    result = dict(
        rows=rows,
        failures=failures,
        reference=reference,
        reference_source_sha256=hashlib.sha256(refpath.read_bytes()).hexdigest(),
    )
    with (HERE / "summary.json").open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
