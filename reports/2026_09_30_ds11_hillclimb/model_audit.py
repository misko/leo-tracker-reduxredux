"""Strict raw-model assessment across a declared DS11 panel.

Unlike the policy audit, this module never substitutes the IID result for an
unqualified challenger.  It reports all attempted scans, exposes aggregate
metrics only when the complete declared panel is matched, and separately
labels metrics on the subset where both endpoints qualified.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys

import aggregate
import harness
from policy_audit import (
    _load_baseline,
    _record_source,
    bind_additional_plans,
    validate_result_selection,
    verify_sources,
)


HERE = Path(__file__).resolve().parent
PANELS = {"original32": 32, "additional12": 12}


def validate_receipt(receipt, family, variant, index):
    assert receipt["family"] == family
    assert receipt["variant"] == variant
    assert receipt["index"] == index
    assert isinstance(receipt["exit_code"], int)
    assert math.isfinite(receipt["wall_s"]) and receipt["wall_s"] >= 0.0


def _metadata_paths(family, base, index, *, additional):
    """Return explicit meanings for digest-valued model metadata."""
    incumbent = base / "runs" / f"{index:02d}_iid.json"
    paths = {
        "incumbent_iid_sha256": incumbent,
        "identity_sidecar_sha256": (
            base / "catalogue_identities.json"
            if additional
            else HERE / "source_balance" / "catalogue_identities.json"
        ),
        "screen_frozen_model_sha256": HERE / "source_balance" / "model.py",
        "model_sha256": HERE / family / "model.py",
    }
    if additional:
        paths.update({
            "incumbent_iid_receipt_sha256": (
                base / "runs" / f"{index:02d}_iid.receipt.json"
            ),
            "plan_sha256": base / "plan.json",
            "adapter_sha256": HERE / "source_balance" / "additional_adapter.py",
            "additional_adapter_sha256": (
                HERE / "source_balance" / "additional_adapter.py"
            ),
            "wrapper_sha256": HERE / family / "additional_wrapper.py",
            "screen_frozen_source_temper_sha256": HERE / family / "model.py",
            "additional_runner_sha256": HERE / family / "additional_runner.py",
        })
    return paths


def _required_metadata(family, *, additional):
    if family not in {"source_balance", "source_count", "source_temper"}:
        return set()
    required = {"identity_sidecar_sha256", "incumbent_iid_sha256"}
    if family == "source_temper":
        required.add("screen_frozen_model_sha256")
    if additional:
        required.update({
            "incumbent_iid_receipt_sha256",
            "plan_sha256",
            "adapter_sha256",
        })
        if family == "source_temper":
            required.update({
                "wrapper_sha256",
                "additional_adapter_sha256",
                "screen_frozen_source_temper_sha256",
            })
    return required


def validate_model_metadata(
    result, family, variant, base, index, hashes, *, additional, qualified
):
    metadata = result.get("metadata", {})
    if "variant" in metadata:
        assert metadata["variant"] == variant
    paths = _metadata_paths(family, base, index, additional=additional)
    if qualified:
        missing = _required_metadata(family, additional=additional) - metadata.keys()
        assert not missing, f"missing model metadata bindings: {sorted(missing)}"

    source_digests = set(result.get("sources", {}).values())
    for key, expected in metadata.items():
        if not key.endswith("_sha256"):
            continue
        path = paths.get(key)
        if path is not None:
            assert path.exists(), f"metadata path does not exist: {path}"
            actual = _record_source(path, hashes)
            assert expected == actual, key
        else:
            # New families may add a digest binding before this general audit
            # knows its semantic name.  It must still bind one consumed source.
            assert expected in source_digests, f"unresolved metadata digest: {key}"


def _load_attempts(family, variant, base, stages, hashes, *, additional):
    plan = json.loads((base / "plan.json").read_text())
    attempts = {}
    for stage in stages:
        folder = HERE / family / "runs" / stage
        for receipt_path in sorted(folder.glob(f"{variant}_??.receipt.json")):
            receipt = json.loads(receipt_path.read_text())
            index = receipt["index"]
            assert index not in attempts, f"duplicate terminal attempt for index {index}"
            assert receipt_path.name == f"{variant}_{index:02d}.receipt.json"
            validate_receipt(receipt, family, variant, index)
            _record_source(receipt_path, hashes)
            if "runner_sha256" in receipt:
                runner = HERE / family / "additional_runner.py"
                assert receipt["runner_sha256"] == _record_source(runner, hashes)

            result_path = receipt_path.with_name(f"{variant}_{index:02d}.json")
            result = json.loads(result_path.read_text()) if result_path.exists() else None
            if result is None:
                assert receipt["exit_code"] != 0, "successful receipt has no result"
                structurally_qualified = False
            else:
                assert result["family"] == family
                assert result["variant"] == variant
                assert result["index"] == index
                assert result["stage"] == stage
                assert result["session"] == plan["inputs"][index]["session_id"]
                assert result.get("sources"), "model result has no source binding"
                verify_sources(result["sources"], hashes)
                structurally_qualified = validate_result_selection(result)
                qualified = bool(receipt["exit_code"] == 0 and structurally_qualified)
                validate_model_metadata(
                    result,
                    family,
                    variant,
                    base,
                    index,
                    hashes,
                    additional=additional,
                    qualified=qualified,
                )
                _record_source(result_path, hashes)
            qualified = bool(
                result is not None
                and receipt["exit_code"] == 0
                and structurally_qualified
            )
            attempts[index] = {
                "stage": stage,
                "receipt": receipt,
                "result": result,
                "qualified": qualified,
            }
    assert set(attempts) == set(range(len(plan["inputs"])))
    return attempts


def summarize_partition(rows):
    matched = [
        row for row in rows
        if row["model_qualified"] and row["baseline_qualified"]
    ]
    model_failures = [row["index"] for row in rows if not row["model_qualified"]]
    baseline_failures = [
        row["index"] for row in rows if not row["baseline_qualified"]
    ]
    complete = len(matched) == len(rows)
    whole = aggregate.summarize_rows(rows) if complete else None
    reasons = []
    if model_failures:
        reasons.append(f"unqualified model indices {model_failures}")
    if baseline_failures:
        reasons.append(f"unqualified IID baseline indices {baseline_failures}")
    summary = {
        "attempts": len(rows),
        "model_qualified": len(rows) - len(model_failures),
        "model_failures": len(model_failures),
        "model_failure_indices": model_failures,
        "baseline_qualified": len(rows) - len(baseline_failures),
        "baseline_failures": len(baseline_failures),
        "baseline_failure_indices": baseline_failures,
        "whole_panel_status": "complete" if complete else "unavailable",
        "whole_panel_metrics": whole,
        "whole_panel_unavailable_reason": None if complete else "; ".join(reasons),
        "matched_qualified_denominator": len(matched),
        "matched_qualified_metrics": (
            aggregate.summarize_rows(matched) if matched else None
        ),
    }
    # Plot-compatible aggregate keys exist only at the full declared denominator.
    if whole is not None:
        summary.update(whole)
    return summary


def _compare_legacy(family, variant, expected, stages, summaries, hashes):
    path = HERE / family / f"aggregate-{variant}-{expected}.json"
    if not path.exists():
        return None
    legacy = json.loads(path.read_text())
    assert legacy["family"] == family
    assert legacy["variant"] == variant
    assert legacy["stages"] == stages
    verify_sources(legacy["source_sha256"], hashes)
    _record_source(path, hashes)
    for name, old in legacy["summaries"].items():
        new = summaries[name]["whole_panel_metrics"]
        assert new is not None, "legacy aggregate claimed an incomplete full panel"
        assert new.keys() == old.keys()
        for key, value in old.items():
            if isinstance(value, float):
                assert math.isclose(new[key], value, rel_tol=1e-12, abs_tol=1e-9), key
            else:
                assert new[key] == value, key
    return {"status": "matches", "path": str(path), "sha256": harness.digest(path)}


def evaluate(family, variant, panel, stages, output=None):
    assert panel in PANELS
    expected = PANELS[panel]
    additional = panel == "additional12"
    base = HERE / "additional" if additional else harness.BASE
    hashes = {}
    plan = (
        bind_additional_plans(base, hashes)
        if additional
        else json.loads((base / "plan.json").read_text())
    )
    assert len(plan["inputs"]) == expected
    _record_source(base / "plan.json", hashes)
    attempts = _load_attempts(
        family, variant, base, stages, hashes, additional=additional
    )

    rows = []
    for index, entry in enumerate(plan["inputs"]):
        baseline, baseline_qualified, baseline_exit = _load_baseline(
            base,
            index,
            entry["session_id"],
            hashes,
            additional=additional,
        )
        attempt = attempts[index]
        result = attempt["result"]
        selected = result["selected"] if attempt["qualified"] else None
        incumbent = baseline["selected"] if baseline_qualified else None
        if selected is not None:
            assert "estimate_deg" in selected
            assert "common_iid" in selected and "incumbent_common_iid" in selected
        rows.append({
            "index": index,
            "stage": attempt["stage"],
            "session": entry["session_id"],
            "attempted": True,
            "qualified": attempt["qualified"],
            "model_qualified": attempt["qualified"],
            "baseline_qualified": baseline_qualified,
            "selection": "model" if attempt["qualified"] else "model_failure",
            "model_exit_code": attempt["receipt"]["exit_code"],
            "baseline_exit_code": baseline_exit,
            "error_m": harness.distance(selected["estimate_deg"]) if selected else None,
            "baseline_error_m": (
                harness.distance(incumbent["estimate_deg"]) if incumbent else None
            ),
            "common_iid_held_gain": (
                selected["common_iid"]["held"]
                - selected["incumbent_common_iid"]["held"]
                if selected else None
            ),
            "runtime_s": attempt["receipt"]["wall_s"],
        })

    partitions = {"all": rows}
    if expected == 32:
        partitions["screen"] = [row for row in rows if row["index"] in harness.SCREEN]
        partitions["replication"] = [
            row for row in rows if row["index"] not in harness.SCREEN
        ]
    summaries = {
        name: summarize_partition(part) for name, part in partitions.items()
    }
    legacy = _compare_legacy(
        family, variant, expected, stages, summaries, hashes
    )
    _record_source(Path(__file__), hashes)
    document = {
        "schema": "ds11-raw-model-assessment/v1",
        "family": family,
        "variant": variant,
        "panel": panel,
        "stages": stages,
        "summaries": summaries,
        "legacy_aggregate_comparison": legacy,
        "rows": rows,
        "source_sha256": hashes,
    }
    if output is None:
        output = HERE / family / f"model-assessment-{variant}-{panel}.json"
    with Path(output).open("x") as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
    print(json.dumps(summaries, indent=2))
    return document


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: model_audit.py FAMILY VARIANT original32|additional12 STAGE[,STAGE]"
        )
    evaluate(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split(","))
