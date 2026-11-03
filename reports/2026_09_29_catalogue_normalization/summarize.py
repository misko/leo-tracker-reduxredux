from study import HERE, ROOT, digest, read, save


def main():
    m = read(HERE / "manifest.json")
    for name, h in m["hashes"].items():
        assert digest(ROOT / name) == h, name
    rows = []
    rankings = []
    counts = []
    failures = []
    for unit in m["units"]:
        ds = unit["dataset"]
        receipt = read(HERE / f"{ds}.receipt.json")
        if receipt["exit_code"] != 0:
            failures.append(dict(dataset=ds, receipt=receipt))
            continue
        result = read(HERE / f"{ds}.json")
        assert result["manifest_sha256"] == digest(HERE / "manifest.json")
        assert len(result["rows"]) == 15 * len(unit["track_ids"])
        assert max(r["error"] for r in result["score_replay"]) < 1e-7
        assert set(r["track_id"] for r in result["rows"]) == set(unit["track_ids"])
        counts.append(
            dict(
                dataset=ds,
                tracks=len(unit["track_ids"]),
                settings=len(result["rows"]),
                training_missing_best=sum(
                    not r["training"]["best_retained"] for r in result["rows"]
                ),
                full_missing_best=sum(not r["full"]["best_retained"] for r in result["rows"]),
                elapsed_seconds=result["elapsed_seconds"],
            )
        )
        for partition in ("training", "full"):
            for tau in (-5.0, 0.0, 5.0):
                case = []
                for label in ("center", "n24", "n8_0", "n8_1", "n8_2"):
                    subset = [
                        r
                        for r in result["rows"]
                        if r["location_class"] == label and r["tau_s"] == tau
                    ]
                    assert len(subset) == len(unit["track_ids"])
                    values = {
                        name: sum(r[partition][name] for r in subset)
                        for name in (
                            "retained_log_score",
                            "denominator_only_log_score",
                            "exact_full_log_score",
                        )
                    }
                    row = dict(
                        dataset=ds,
                        partition=partition,
                        tau_s=tau,
                        location=label,
                        **values,
                        denominator_effect=values["denominator_only_log_score"]
                        - values["retained_log_score"],
                        omitted_effect=values["exact_full_log_score"]
                        - values["denominator_only_log_score"],
                    )
                    assert row["denominator_effect"] <= 1e-7 and row["omitted_effect"] >= -1e-7
                    case.append(row)
                center = case[0]
                for row in case:
                    row["retained_vs_center"] = (
                        row["retained_log_score"] - center["retained_log_score"]
                    )
                    row["exact_vs_center"] = (
                        row["exact_full_log_score"] - center["exact_full_log_score"]
                    )
                    row["relative_score_change"] = (
                        row["exact_vs_center"] - row["retained_vs_center"]
                    )
                rows.extend(case)
                rankings.append(
                    dict(
                        dataset=ds,
                        partition=partition,
                        tau_s=tau,
                        retained_winner=max(case, key=lambda r: r["retained_log_score"])[
                            "location"
                        ],
                        exact_winner=max(case, key=lambda r: r["exact_full_log_score"])["location"],
                        max_relative_change=max(abs(r["relative_score_change"]) for r in case),
                        max_omitted_effect=max(r["omitted_effect"] for r in case),
                    )
                )
    save(
        HERE / "summary.json", dict(rows=rows, rankings=rankings, counts=counts, failures=failures)
    )
    lines = [
        "| Dataset | Partition | Time s | Retained winner | Full winner | "
        "Max relative change | Max omitted effect |",
        "|---|---|---:|---|---|---:|---:|",
    ]
    for r in rankings:
        lines.append(
            f"| {r['dataset']} | {r['partition']} | {r['tau_s']:g} | {r['retained_winner']} | "
            f"{r['exact_winner']} | {r['max_relative_change']:.6f} | "
            f"{r['max_omitted_effect']:.6f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print("Counts", counts, "Failures", failures)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
