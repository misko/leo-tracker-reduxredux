import json

from run import HERE, ROOT, read, sha


def main():
    for name, h in read(HERE / "manifest.json")["hashes"].items():
        assert sha(ROOT / name) == h, name
    rows = []
    for ds in ("DS7", "DS8", "DS9"):
        receipt = read(HERE / f"{ds}.receipt.json")
        cases = [read(p) for p in sorted(HERE.glob(f"{ds}_corner*.json"))]
        if receipt["exit_code"] == 0:
            r = read(HERE / f"{ds}.json")
            assert r["manifest_sha256"] == sha(HERE / "manifest.json")
            assert r["cases"] == cases and len(cases) == 4
        qualified = [c for c in cases if c.get("fit", {}).get("qualified")]
        row = dict(
            dataset=ds,
            receipt=receipt,
            completed_corners=len(cases),
            qualified_corners=len(qualified),
            exceptions=[c for c in cases if "error_type" in c],
            unqualified=[c for c in cases if "fit" in c and not c["fit"]["qualified"]],
            qualified_results=[
                dict(
                    corner=c["corner"],
                    score_delta=c["score_delta"],
                    position_difference_m=c["position_difference_m"],
                    gradient_audit=c["fit"]["gradient_audit"],
                    elapsed_seconds=c["elapsed_seconds"],
                )
                for c in qualified
            ],
        )
        rows.append(row)
    with (HERE / "summary.json").open("x") as out:
        json.dump(dict(rows=rows), out, indent=2, allow_nan=False)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
