from study import HERE, ROOT, digest, read, save


def main():
    manifest = read(HERE / "manifest.json")
    for name, expected in manifest["hashes"].items():
        assert digest(ROOT / name) == expected, name
    rows = []
    failures = []
    for unit in sorted({r["unit"] for r in manifest["targets"]}):
        receipt = read(HERE / f"{unit}.receipt.json")
        if receipt["exit_code"] != 0:
            failures.append(dict(unit=unit, receipt=receipt))
            continue
        result = read(HERE / f"{unit}.json")
        assert result["manifest_sha256"] == digest(HERE / "manifest.json")
        if not result["qualified"]:
            failures.append(dict(unit=unit, reason="numerical qualification"))
            continue
        a, b = result["orders"][-1]["arms"]
        for left, right in zip(a, b, strict=True):
            assert left["track_id"] == right["track_id"] and left["numbers"] == right["numbers"]
            source = next(
                r
                for r in manifest["targets"]
                if r["unit"] == unit and r["track_id"] == left["track_id"]
            )
            same = left["top_number"] == right["top_number"]
            rows.append(
                dict(
                    source,
                    n24_number=left["top_number"],
                    mixture_number=right["top_number"],
                    n24_candidate_probability=left["top_probability"],
                    mixture_candidate_probability=right["top_probability"],
                    same_map=same,
                    stable_confident=same
                    and min(left["top_probability"], right["top_probability"]) >= 0.9,
                    total_variation=0.5
                    * sum(
                        abs(p - q)
                        for p, q in zip(left["conditional"], right["conditional"], strict=True)
                    ),
                )
            )
    rows.sort(key=lambda r: r["contribution"])
    save(
        HERE / "summary.json",
        dict(rows=rows, failures=failures, complete=not failures and len(rows) == 20),
    )
    lines = [
        "| Scan | Track | RX | N24 catalogue # (P) | "
        "N8 mixture catalogue # (P) | Stable ≥0.9 | TV |",
        "|---|---|---:|---|---|---|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['unit']} | {r['track_id']} | {r['receiver_id']} | "
            f"{r['n24_number']} ({r['n24_candidate_probability']:.4f}) | "
            f"{r['mixture_number']} ({r['mixture_candidate_probability']:.4f}) | "
            f"{r['stable_confident']} | {r['total_variation']:.4f} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print(
        "Failures",
        failures,
        "same MAP",
        sum(r["same_map"] for r in rows),
        "stable confident",
        sum(r["stable_confident"] for r in rows),
        "of",
        len(rows),
    )


if __name__ == "__main__":
    main()
