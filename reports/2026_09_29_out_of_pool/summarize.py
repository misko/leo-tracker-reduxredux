"""Verify sealed evidence and summarize complete-case predictive scores."""

import math

from study import HERE, ROOT, digest, read, save


def mixture(values):
    top = max(values)
    return top + math.log(sum(math.exp(v - top) for v in values) / len(values))


def main():
    manifest_path = HERE / "manifest.json"
    manifest = read(manifest_path)
    for name, expected in manifest["hashes"].items():
        assert digest(ROOT / name) == expected, name
    rows, missing = [], []
    for spec in manifest["sets"]:
        path = HERE / f"{spec['unit']}.json"
        receipt = read(HERE / f"{spec['unit']}.receipt.json")
        if not path.exists() or receipt["exit_code"] != 0:
            missing.append(dict(unit=spec["unit"], receipt=receipt))
            continue
        result = read(path)
        assert result["manifest_sha256"] == digest(manifest_path)
        assert result["session_id"] == spec["input"]["session_id"]
        assert result["session_id"] not in spec["source_sessions"]
        assert len(result["values"]) == 5
        qualified = all(v["qualified"] for v in result["values"])
        scores = [v["log_score"] for v in result["values"]]
        center, n24 = scores[:2]
        ensemble = mixture(scores[2:])
        rows.append(
            dict(
                unit=spec["unit"],
                dataset=spec["dataset"],
                session_id=result["session_id"],
                qualified=qualified,
                center=center,
                n24=n24,
                n8_mixture=ensemble,
                n24_minus_center=n24 - center,
                n24_minus_n8_mixture=n24 - ensemble,
                max_quadrature_difference=max(v["quadrature_difference"] for v in result["values"]),
                max_scalar_error=max(v["scalar_replay_error"] for v in result["values"]),
                refined=sum("initial" in v for v in result["values"]),
                tracks=result["tracks"],
                observations=result["observations"],
                elapsed_seconds=result["elapsed_seconds"],
            )
        )
    aggregates = []
    for ds in ("DS7", "DS8", "DS9"):
        subset = [r for r in rows if r["dataset"] == ds]
        valid = len(subset) == 5 and all(r["qualified"] for r in subset)
        aggregate = dict(dataset=ds, qualified=valid)
        if valid:
            for key in ("n24_minus_center", "n24_minus_n8_mixture"):
                aggregate[key] = sum(r[key] for r in subset)
                aggregate[key + "_wins"] = sum(r[key] > 0 for r in subset)
        aggregates.append(aggregate)
    save(HERE / "summary.json", dict(rows=rows, missing=missing, aggregates=aggregates))
    lines = [
        "| Dataset | N24 − center log score | Wins / 5 | N24 − N8 mixture log score | Wins / 5 |",
        "|---|---:|---:|---:|---:|",
    ]
    for a in aggregates:
        if a["qualified"]:
            lines.append(
                f"| {a['dataset']} | {a['n24_minus_center']:+.3f} | {a['n24_minus_center_wins']} | "
                f"{a['n24_minus_n8_mixture']:+.3f} | {a['n24_minus_n8_mixture_wins']} |"
            )
        else:
            lines.append(f"| {a['dataset']} | Incomplete/unqualified | — | — | — |")
    lines.extend(
        [
            "",
            "Positive favors N24. Log scores are in natural-log units, not metres.",
            "",
            "| Target | Session | N24 − center | N24 − N8 mixture | Qualified |",
            "|---|---|---:|---:|---|",
        ]
    )
    for r in rows:
        lines.append(
            f"| {r['unit']} | {r['session_id']} | {r['n24_minus_center']:+.3f} | "
            f"{r['n24_minus_n8_mixture']:+.3f} | {r['qualified']} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:6]))


if __name__ == "__main__":
    main()
