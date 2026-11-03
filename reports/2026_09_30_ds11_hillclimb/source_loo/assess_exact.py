"""Verify and summarize the fixed exact-deletion audit; no geography is scored."""
from pathlib import Path
import hashlib
import json
import math

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    rows = []
    bindings = {str(Path(__file__).resolve()): digest(__file__)}
    for index in (0, 16):
        phase_path = HERE / "runs" / "phase1" / f"{index:02d}.json"
        phase = json.loads(phase_path.read_text())
        bindings[str(phase_path)] = digest(phase_path)
        for family in phase["families"]:
            selection = family["selection"]
            assert selection["selection_complete"]
            for rank in ("largest", "lower_median"):
                norad = selection[f"{rank}_norad"]
                stem = f"{index:02d}_{family['family']}_{norad}"
                base = HERE / "runs" / "exact_audit"
                receipt_path = base / f"{stem}.receipt.json"
                receipt = json.loads(receipt_path.read_text())
                bindings[str(receipt_path)] = digest(receipt_path)
                for key, expected in (("index", index), ("family", family["family"]), ("norad", norad)):
                    assert receipt[key] == expected
                assert receipt["exact_audit_sha256"] == digest(HERE / "exact_audit.py")
                assert receipt["exact_protocol_sha256"] == digest(HERE / "EXACT_PROTOCOL.md")
                row = dict(index=index, family=family["family"], norad=norad,
                           rank=rank, exit_code=receipt["exit_code"], wall_s=receipt["wall_s"],
                           qualified=False, audit_pass=False)
                if receipt["exit_code"] == 0:
                    path = base / f"{stem}.json"
                    result = json.loads(path.read_text())
                    bindings[str(path)] = digest(path)
                    for source, expected in result["sources"].items():
                        assert digest(source) == expected, source
                    assert result["index"] == index and result["family"] == family["family"]
                    assert result["norad"] == norad and rank in result["selection_ranks"]
                    assert result["full_endpoint_x"] == family["endpoint_x"]
                    fold = next(f for f in family["folds"] if f["norad"] == norad)
                    assert result["influence_x"] == fold["estimate"]
                    assert result["source_track_ids"] == fold["track_ids"]
                    assert result["reference_used"] is False
                    assert result["exact_common_held"]["held_observation_count"] == result["influence_common_held"]["held_observation_count"]
                    exact, approx, full = (result[k] for k in ("exact_x", "influence_x", "full_endpoint_x"))
                    shift = math.dist(exact[:2], full[:2])
                    delta = math.dist(exact[:2], approx[:2])
                    time_delta = abs(exact[2] - approx[2])
                    held_delta = abs(result["exact_common_held"]["score"] - result["influence_common_held"]["score"])
                    limit = max(0.05, 0.1 * shift)
                    comparison = result["comparison"]
                    for key, value in (("exact_en_shift_km", shift), ("en_discrepancy_km", delta),
                                       ("en_limit_km", limit), ("time_discrepancy_s", time_delta),
                                       ("held_score_discrepancy_nat", held_delta)):
                        assert math.isclose(comparison[key], value, rel_tol=1e-12, abs_tol=1e-12)
                    tolerances = delta <= limit and time_delta <= 0.02 and held_delta <= 0.1
                    assert comparison["passes_tolerances"] == tolerances
                    optimizer = result["optimizer"]
                    boundary = any(abs(v) > bound - 0.001 for v, bound in zip(exact, (12, 12, 5)))
                    assert optimizer["boundary"] == boundary
                    qualified = bool(optimizer["success"] and not boundary
                                     and all(math.isfinite(v) for v in exact)
                                     and math.isfinite(result["exact_score"])
                                     and optimizer["gradient_max_abs"] is not None
                                     and optimizer["gradient_max_abs"] <= 0.01
                                     and optimizer["gradient_audit_max_abs"] is not None
                                     and optimizer["gradient_audit_max_abs"] <= 0.02)
                    assert optimizer["qualified"] == qualified
                    passed = qualified and tolerances
                    assert result["audit_pass"] == passed
                    row.update(qualified=qualified, audit_pass=passed,
                               en_pass=delta <= limit, time_pass=time_delta <= 0.02,
                               held_pass=held_delta <= 0.1, exact_shift_m=shift * 1000,
                               en_discrepancy_m=delta * 1000, time_discrepancy_s=time_delta,
                               held_discrepancy_nat=held_delta)
                rows.append(row)
    assert len(rows) == 16
    result = dict(schema="ds11-source-loo-exact-assessment/v1", planned_jobs=16,
                  terminal_jobs=len(rows), qualified_jobs=sum(r["qualified"] for r in rows),
                  passed_jobs=sum(r["audit_pass"] for r in rows),
                  approximation_advances=all(r["audit_pass"] for r in rows),
                  reference_used=False, rows=rows, sources=bindings)
    with (HERE / "exact-assessment.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "sources")}))


if __name__ == "__main__":
    main()
