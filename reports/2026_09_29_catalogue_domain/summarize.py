from study import HERE, ROOT, digest, read, save


def aggregate(rows):
    result = dict(settings=len(rows))
    for partition in ("training", "full"):
        values = [r[partition] for r in rows]
        result[partition] = dict(
            min_retained_mass=min(v["retained_mass"] for v in values),
            max_log_omitted_mass=max(v["log_omitted_mass"] for v in values),
            missing_best=sum(not v["best_retained"] for v in values),
            mass_below_99=sum(v["retained_mass"] < 0.99 for v in values),
            max_signal_probability_change=max(
                abs(v["full_signal_probability"] - v["retained_signal_probability"]) for v in values
            ),
        )
    return result


def main():
    manifest = read(HERE / "manifest.json")
    for name, h in manifest["hashes"].items():
        assert digest(ROOT / name) == h, name
    old = read(HERE.parent / "2026_09_29_full_catalogue_probe/manifest.json")
    assert manifest["units"] == old["units"] and manifest["config"] == old["config"]
    rows = []
    runtime = []
    for ds in ("DS7", "DS8", "DS9"):
        assert read(HERE / f"{ds}.receipt.json")["exit_code"] == 0
        result = read(HERE / f"{ds}.json")
        assert result["manifest_sha256"] == digest(HERE / "manifest.json")
        assert len(result["rows"]) == 126
        assert (
            len({(r["track_id"], r["east_km"], r["north_km"], r["tau_s"]) for r in result["rows"]})
            == 126
        )
        assert all(r["prediction_replay_hz"] < 1e-6 for r in result["rows"])
        rows.extend(dict(dataset=ds, **r) for r in result["rows"])
        runtime.append(result["elapsed_seconds"])
    groups = []
    for ds in ("all", "DS7", "DS8", "DS9"):
        for label in ("fitted", "center", "anchor", "interior", "outer"):
            subset = [
                r
                for r in rows
                if (ds == "all" or r["dataset"] == ds) and r["location_class"] == label
            ]
            groups.append(dict(dataset=ds, location_class=label, **aggregate(subset)))
    timing = [
        dict(
            tau_s=t,
            **aggregate([r for r in rows if r["tau_s"] == t and r["location_class"] != "outer"]),
        )
        for t in (-5.0, 0.0, 5.0)
    ]
    worst = sorted(rows, key=lambda r: r["training"]["retained_mass"])[:20]
    save(
        HERE / "summary.json",
        dict(
            groups=groups,
            local_timing=timing,
            worst_training=worst,
            elapsed_seconds_sum=sum(runtime),
            elapsed_seconds_max=max(runtime),
        ),
    )
    lines = [
        "| Region | Settings | Min train mass | Train best omitted | "
        "Min full mass | Full best omitted |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in groups:
        if r["dataset"] != "all":
            continue
        lines.append(
            f"| {r['location_class']} | {r['settings']} | "
            f"{r['training']['min_retained_mass']:.9f} | {r['training']['missing_best']} | "
            f"{r['full']['min_retained_mass']:.9f} | {r['full']['missing_best']} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("Local timing", timing)


if __name__ == "__main__":
    main()
