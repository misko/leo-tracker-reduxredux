import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = HERE.parent / "2026_09_29_out_of_pool"


def logsum(values):
    top = max(values)
    return top + math.log(sum(math.exp(v - top) for v in values))


def posterior(values):
    total = logsum(values)
    return [math.exp(v - total) for v in values]


def scores(matrix):
    if not matrix or len({len(row) for row in matrix}) != 1 or not matrix[0]:
        raise ValueError("Nonempty rectangular score matrix required")
    if not all(math.isfinite(v) for row in matrix for v in row):
        raise ValueError("Finite log densities required")
    k = len(matrix[0])
    logk = math.log(k)
    summed = [sum(row[i] for row in matrix) for i in range(k)]
    per_scan = [posterior(row) for row in matrix]
    return dict(
        shared=logsum(summed) - logk,
        independent=sum(logsum(row) - logk for row in matrix),
        component_sums=summed,
        shared_posterior=posterior(summed),
        scan_posteriors=per_scan,
        top_components=[max(range(k), key=lambda i: row[i]) for row in matrix],
        independent_posterior_same_component_probability=sum(
            math.prod(row[i] for row in per_scan) for i in range(k)
        ),
    )


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifest = read(SOURCE / "manifest.json")
    sealed = read(SOURCE / "evidence-sha256.json")["sha256"]
    paths = [
        SOURCE / "manifest.json",
        SOURCE / "evidence-sha256.json",
        HERE / "study.py",
        HERE / "PROTOCOL.md",
    ]
    assert (
        digest(SOURCE / "manifest.json")
        == sealed[str((SOURCE / "manifest.json").relative_to(ROOT))]
    )
    results = []
    for ds in ("DS7", "DS8", "DS9"):
        specs = [s for s in manifest["sets"] if s["dataset"] == ds]
        assert len(specs) == 5
        raw = []
        for spec in specs:
            p = SOURCE / f"{spec['unit']}.json"
            d = read(p)
            paths.append(p)
            assert digest(p) == sealed[str(p.relative_to(ROOT))]
            assert d["manifest_sha256"] == digest(SOURCE / "manifest.json")
            assert d["session_id"] == spec["input"]["session_id"]
            assert d["session_id"] not in spec["source_sessions"]
            assert all(v["qualified"] for v in d["values"])
            assert spec["positions"] == specs[0]["positions"]
            raw.append(d)
        variants = []
        for field in ("log_score", "audit_log_score"):
            assert not any("initial" in v for d in raw for v in d["values"])
            matrix = [[v[field] for v in d["values"][2:]] for d in raw]
            result = scores(matrix)
            n24 = sum(d["values"][1][field] for d in raw)
            result.update(
                n24=n24,
                shared_minus_n24=result["shared"] - n24,
                independent_minus_n24=result["independent"] - n24,
                independent_minus_shared=result["independent"] - result["shared"],
            )
            variants.append(result)
        difference = max(
            abs(variants[0][key] - variants[1][key])
            for key in ("shared_minus_n24", "independent_minus_n24", "independent_minus_shared")
        )
        results.append(
            dict(
                dataset=ds,
                targets=[s["unit"] for s in specs],
                positions=specs[0]["positions"][2:],
                primary=variants[0],
                audit=variants[1],
                max_comparison_change=difference,
            )
        )
    result = dict(results=results, hashes={str(p.relative_to(ROOT)): digest(p) for p in paths})
    with (HERE / "results.json").open("x") as f:
        json.dump(result, f, indent=2, allow_nan=False)
    lines = [
        "| Dataset | Shared N8 − N24 | Per-scan N8 − N24 | "
        "Per-scan − shared | Per-target winning N8 index |",
        "|---|---:|---:|---:|---|",
    ]
    for row in results:
        r = row["primary"]
        lines.append(
            f"| {row['dataset']} | {r['shared_minus_n24']:+.3f} | "
            f"{r['independent_minus_n24']:+.3f} | "
            f"{r['independent_minus_shared']:+.3f} | {r['top_components']} |"
        )
    (HERE / "TABLE.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
