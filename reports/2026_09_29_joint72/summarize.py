import math

from study import HERE, REPORTS, digest, read, save, verify


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [*a, *b])
    h = (
        math.sin((lat1 - lat2) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon1 - lon2) / 2) ** 2
    )
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(h)))


def mixture(scores):
    top = max(scores)
    return top + math.log(sum(math.exp(v - top) for v in scores) / len(scores))


def main():
    m = read(HERE / "manifest.json")
    verify(m)
    selected = read(HERE / "selected.json")
    assert selected["manifest_sha256"] == digest(HERE / "manifest.json")
    for name, h in selected["fit_hashes"].items():
        assert digest(HERE / name) == h, name
    reference_path = REPORTS / "2026_09_29_unassociated_trend/summary.json"
    reference = read(reference_path)["reference"]
    rows = []
    failures = []
    mean_deg = None
    for spec in m["targets"]:
        key = spec["unit"]
        receipt = read(HERE / f"target_{key}.receipt.json")
        if receipt["exit_code"] != 0 or not (HERE / f"{key}.json").exists():
            failures.append(dict(unit=key, receipt=receipt))
            continue
        result = read(HERE / f"{key}.json")
        assert result["selected_sha256"] == digest(HERE / "selected.json")
        assert result["manifest_sha256"] == digest(HERE / "manifest.json")
        assert result["session_id"] == spec["input"]["session_id"]
        assert result["session_id"] not in {r["session_id"] for r in m["inputs"]}
        if mean_deg is None:
            mean_deg = result["mean_estimate_deg"]
        assert mean_deg == result["mean_estimate_deg"]
        old = read(REPORTS / f"2026_09_29_out_of_pool/{key}.json")
        assert all(v["qualified"] for v in old["values"])
        controls = [v["log_score"] for v in old["values"]]
        qualified = all(v["qualified"] for v in result["arms"])
        if not qualified:
            failures.append(dict(unit=key, reason="quadrature qualification"))
        row = dict(unit=key, dataset=spec["dataset"], qualified=qualified)
        for arm, v in zip(("joint", "mean"), result["arms"], strict=True):
            for comparator, score in (
                ("n24", controls[1]),
                ("center", controls[0]),
                ("n8_mixture", mixture(controls[2:])),
            ):
                row[arm + "_minus_" + comparator] = v["log_score"] - score
        row["joint_minus_mean"] = result["arms"][0]["log_score"] - result["arms"][1]["log_score"]
        rows.append(row)
    aggregates = []
    for ds in ("DS7", "DS8", "DS9", "all"):
        subset = [r for r in rows if (ds == "all" or r["dataset"] == ds) and r["qualified"]]
        aggregate = dict(dataset=ds, targets=len(subset))
        for key in [
            a + "_minus_" + c for a in ("joint", "mean") for c in ("n24", "center", "n8_mixture")
        ] + ["joint_minus_mean"]:
            aggregate[key] = sum(r[key] for r in subset)
            aggregate[key + "_wins"] = sum(r[key] > 0 for r in subset)
        aggregates.append(aggregate)
    summary = dict(
        rows=rows,
        aggregates=aggregates,
        failures=failures,
        joint_error_m=distance(reference, selected["estimate_deg"]),
        mean_error_m=distance(reference, mean_deg) if mean_deg else None,
        reference=reference,
        reference_sha256=digest(reference_path),
    )
    save("summary.json", summary)
    lines = [
        "| Dataset | Targets | Joint vs N24 | Mean vs N24 | "
        "Joint vs center | Joint vs N8 mixture |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in aggregates:
        lines.append(
            f"| {r['dataset']} | {r['targets']} | {r['joint_minus_n24']:+.3f} | "
            f"{r['mean_minus_n24']:+.3f} | {r['joint_minus_center']:+.3f} | "
            f"{r['joint_minus_n8_mixture']:+.3f} |"
        )
    lines.extend(
        [
            "",
            "| Target | Qualified | Joint vs N24 | Mean vs N24 | Joint vs N8 mixture |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for r in rows:
        lines.append(
            f"| {r['unit']} | {r['qualified']} | {r['joint_minus_n24']:+.3f} | "
            f"{r['mean_minus_n24']:+.3f} | {r['joint_minus_n8_mixture']:+.3f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print(summary["joint_error_m"], summary["mean_error_m"], aggregates, failures)


if __name__ == "__main__":
    main()
