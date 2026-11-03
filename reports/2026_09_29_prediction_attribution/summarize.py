from collections import defaultdict

from study import HERE, ROOT, digest, read, save


def main():
    manifest = read(HERE / "manifest.json")
    for name, expected in manifest["hashes"].items():
        assert digest(ROOT / name) == expected, name
    scans = []
    tracks = []
    failures = []
    for spec in read(ROOT / manifest["source"])["sets"]:
        unit = spec["unit"]
        receipt = read(HERE / f"{unit}.receipt.json")
        p = HERE / f"{unit}.json"
        if receipt["exit_code"] != 0 or not p.exists():
            failures.append(dict(unit=unit, receipt=receipt))
            continue
        result = read(p)
        refined_path = HERE / f"{unit}.refined.json"
        if refined_path.exists():
            assert not result["qualified"]
            assert read(HERE / f"{unit}.refined.receipt.json")["exit_code"] == 0
            result = read(refined_path)
            assert result["original_sha256"] == digest(p)
            for name, expected in result["refinement_hashes"].items():
                assert digest(HERE / name) == expected
        assert result["manifest_sha256"] == digest(HERE / "manifest.json")
        if not result["qualified"]:
            failures.append(dict(unit=unit, discrepancy=result["discrepancy"]))
            continue
        high = result["orders"][-1]
        delta = high["n24"]["log_score"] - high["mixture"]["log_score"]
        assert abs(sum(high["track_delta"]) + high["kl_delta"] - delta) < 1e-7
        scans.append(
            dict(
                unit=unit,
                dataset=spec["dataset"],
                log_score_delta=delta,
                track_sum=sum(high["track_delta"]),
                kl_delta=high["kl_delta"],
            )
        )
        for i, metadata in enumerate(result["tracks"]):
            tracks.append(
                dict(
                    unit=unit,
                    dataset=spec["dataset"],
                    session_id=spec["input"]["session_id"],
                    **metadata,
                    contribution=high["track_delta"][i],
                    n24_signal=high["n24"]["signal_responsibility"][i],
                    mixture_signal=high["mixture"]["signal_responsibility"][i],
                )
            )
    groups = []
    if not failures:
        for keys in (("dataset",), ("receiver_id",), ("rf_hz",), ("dataset", "receiver_id")):
            grouped = defaultdict(list)
            for row in tracks:
                grouped[tuple(row[k] for k in keys)].append(row)
            for key, rows in sorted(grouped.items()):
                losses = [r for r in rows if r["contribution"] < 0]
                groups.append(
                    dict(
                        group_by=list(keys),
                        key=list(key),
                        tracks=len(rows),
                        contribution=sum(r["contribution"] for r in rows),
                        negative_tracks=len(losses),
                        gross_loss=-sum(r["contribution"] for r in losses),
                        signal_delta=sum(r["n24_signal"] - r["mixture_signal"] for r in rows),
                    )
                )
    losses = sorted((r for r in tracks if r["contribution"] < 0), key=lambda r: r["contribution"])
    save(
        HERE / "summary.json",
        dict(
            scans=scans,
            tracks=tracks,
            groups=groups,
            failures=failures,
            complete=not failures,
            top_losses=losses[:20],
        ),
    )
    print("Qualified", len(scans), "failures", failures)
    if failures:
        return
    lines = [
        "| Dataset | N24 − mixture log score | Track contribution | KL contribution |",
        "|---|---:|---:|---:|",
    ]
    for ds in ("DS7", "DS8", "DS9"):
        rows = [r for r in scans if r["dataset"] == ds]
        lines.append(
            f"| {ds} | {sum(r['log_score_delta'] for r in rows):+.3f} | "
            f"{sum(r['track_sum'] for r in rows):+.3f} | {sum(r['kl_delta'] for r in rows):+.3f} |"
        )
    lines.extend(
        [
            "",
            "Track contributions exclude the separately reported KL term.",
            "",
            "| Group | Tracks | Negative tracks | Net contribution | Gross loss magnitude |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for g in groups:
        label = ", ".join(f"{k}={v}" for k, v in zip(g["group_by"], g["key"], strict=True))
        lines.append(
            f"| {label} | {g['tracks']} | {g['negative_tracks']} | "
            f"{g['contribution']:+.3f} | {g['gross_loss']:.3f} |"
        )
    lines.extend(
        [
            "",
            "Largest posterior-dependent negative contributions (diagnostic only):",
            "",
            "| Scan | Track | RX | RF GHz | Contribution | N24 signal P | Mixture signal P |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in losses[:20]:
        lines.append(
            f"| {row['unit']} | {row['track_id']} | {row['receiver_id']} | "
            f"{row['rf_hz'] / 1e9:.3f} | {row['contribution']:+.3f} | "
            f"{row['n24_signal']:.3f} | {row['mixture_signal']:.3f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:5]))


if __name__ == "__main__":
    main()
