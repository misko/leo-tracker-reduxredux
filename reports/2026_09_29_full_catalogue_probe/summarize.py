from study import HERE, ROOT, digest, read, save


def main():
    manifest = read(HERE / "manifest.json")
    for name, h in manifest["hashes"].items():
        assert digest(ROOT / name) == h, name
    rows = []
    for unit in manifest["units"]:
        ds = unit["dataset"]
        receipt = read(HERE / f"{ds}.receipt.json")
        assert receipt["exit_code"] == 0
        result = read(HERE / f"{ds}.json")
        assert result["manifest_sha256"] == digest(HERE / "manifest.json")
        assert set(r["track_id"] for r in result["rows"]) == set(unit["track_ids"])
        for r in result["rows"]:
            assert r["prediction_replay_hz"] < 1e-6
            assert 0 <= r["training"]["retained_mass"] <= 1 + 1e-10
            assert 0 <= r["full"]["retained_mass"] <= 1 + 1e-10
            rows.append(dict(dataset=ds, **r))
    save(
        HERE / "summary.json",
        dict(
            rows=rows,
            tracks=len(rows),
            training_best_retained=sum(r["training"]["best_retained"] for r in rows),
            full_best_retained=sum(r["full"]["best_retained"] for r in rows),
        ),
    )
    lines = [
        "| Dataset | Track | Catalogue objects | Valid | Visible | "
        "Retained visible | Training mass | Full mass |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['dataset']} | {r['track_id']} | {r['catalogue_size']} | {r['valid']} | "
            f"{r['visible']} | {r['retained_visible']} | {r['training']['retained_mass']:.12f} | "
            f"{r['full']['retained_mass']:.12f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print("Verified", len(rows), "full-catalogue comparisons")


if __name__ == "__main__":
    main()
