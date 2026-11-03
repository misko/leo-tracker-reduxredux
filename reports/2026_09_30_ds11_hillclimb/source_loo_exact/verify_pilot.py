"""Read-only numerical/provenance audit of the exact source-holdout pilot."""
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAMILIES = ("iid_t4_scale100", "source_receiver_equal", "robust_t8_scale100", "robust_t4_scale200")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    sources = {str(Path(__file__).resolve()): digest(__file__)}
    rows, replays, coverages = [], [], []
    for family in FAMILIES:
        path = HERE / "runs" / "pilot" / f"00_{family}.json"
        receipt_path = path.with_suffix(".receipt.json")
        receipt = json.loads(receipt_path.read_text())
        assert receipt["index"] == 0 and receipt["family"] == family
        assert receipt["run_sha256"] == digest(HERE / "run.py")
        assert receipt["protocol_sha256"] == digest(HERE / "PROTOCOL.md")
        sources[str(receipt_path)] = digest(receipt_path)
        if receipt["exit_code"] != 0:
            rows.append(dict(family=family, qualified=False, folds=None, qualified_folds=None,
                             common_held_sum=None, wall_s=receipt["wall_s"],
                             exit_code=receipt["exit_code"], result_available=False))
            continue
        row = json.loads(path.read_text())
        assert row["index"] == 0 and row["family"] == family and not row["reference_used"]
        sources[str(path)] = digest(path)
        sources[str(receipt_path)] = digest(receipt_path)
        for source, expected in row["sources"].items():
            assert digest(source) == expected, source
        assignments = row["assignments"]
        norads = sorted({a["norad"] for a in assignments if a["unambiguous"]})
        expected_groups = {n: [a["track_id"] for a in assignments if a["unambiguous"] and a["norad"] == n]
                           for n in norads}
        expected_groups = {n: ids for n, ids in expected_groups.items() if len(ids) >= 2}
        assert row["eligible_source_count"] == len(expected_groups)
        assert [f["norad"] for f in row["folds"]] == list(expected_groups)
        for fold in row["folds"]:
            assert fold["track_ids"] == expected_groups[fold["norad"]]
            assert fold["retained_track_count"] == len(assignments) - len(fold["track_ids"])
            optimizer = fold["optimizer"]
            if "failure" not in fold:
                x = fold["x"]
                boundary = any(abs(v) > limit - 0.001 for v, limit in zip(x, (12, 12, 5)))
                assert optimizer["boundary"] == boundary
                qualified = bool(optimizer["success"] and not boundary
                                 and all(math.isfinite(v) for v in x)
                                 and math.isfinite(fold["retained_score"])
                                 and optimizer["gradient_max_abs"] is not None
                                 and optimizer["gradient_max_abs"] <= 0.01
                                 and optimizer["gradient_audit_max_abs"] is not None
                                 and optimizer["gradient_audit_max_abs"] <= 0.02)
                assert optimizer["qualified"] == qualified
            prior = HERE.parent / "source_loo" / "runs" / "exact_audit" / f"00_{family}_{fold['norad']}.json"
            if prior.exists():
                old = json.loads(prior.read_text())
                assert old["full_endpoint_x"] == row["full_endpoint_x"]
                assert old["source_track_ids"] == fold["track_ids"]
                delta = max(abs(a - b) for a, b in zip(old["exact_x"], fold["x"]))
                held_delta = abs(old["exact_common_held"]["score"] - fold["common_held_score"])
                assert delta <= 1e-6 and held_delta <= 1e-6
                sources[str(prior)] = digest(prior)
                replays.append(dict(family=family, norad=fold["norad"], max_coordinate_delta=delta,
                                    held_score_delta=held_delta))
        qualified = all(f["optimizer"]["qualified"] for f in row["folds"])
        assert row["family_qualified"] == qualified
        if qualified:
            assert math.isclose(row["common_held_sum"], sum(f["common_held_score"] for f in row["folds"]), abs_tol=1e-8)
        else:
            assert row["common_held_sum"] is None
        coverages.append(row["coverage"])
        rows.append(dict(family=family, qualified=qualified, folds=len(row["folds"]),
                         qualified_folds=sum(f["optimizer"]["qualified"] for f in row["folds"]),
                         common_held_sum=row["common_held_sum"], wall_s=receipt["wall_s"],
                         exit_code=0, result_available=True))
    assert len(replays) == 2 * len(coverages)
    coverage_matches = bool(len(coverages) == 4 and all(c == coverages[0] for c in coverages))
    selectable = coverage_matches and all(r["qualified"] for r in rows)
    selected = max(rows, key=lambda r: r["common_held_sum"])["family"] if selectable else None
    output = dict(schema="ds11-source-loo-exact-pilot-verification/v1", reference_used=False,
                  coverage_matches=coverage_matches, selectable=selectable, selected_family=selected,
                  families=rows, overlap_replays=replays, sources=sources)
    with (HERE / "pilot-verification.json").open("x") as stream:
        json.dump(output, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in output.items() if k not in ("sources", "overlap_replays")}))


if __name__ == "__main__":
    main()
