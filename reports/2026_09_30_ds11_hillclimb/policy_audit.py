"""Strict audit of the frozen source/IID qualification-only policy.

This leaves the preliminary ``policy.py`` outputs intact.  It independently
binds terminal attempts, result provenance, the IID fallback, and (for the
additional panel) both the frozen sampling plan and assembled derived inputs.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import aggregate
import harness


HERE = Path(__file__).resolve().parent
FAMILY = "source_balance"
VARIANT = "source_receiver_equal"


def select(challenger, incumbent):
    """Frozen qualification-only rule; scores and position errors do not enter."""
    if incumbent is None or not incumbent.get("qualified", False):
        return None, "failure"
    if challenger is not None and challenger.get("qualified", False):
        return challenger, "challenger"
    return incumbent, "iid_fallback"


def _record_source(path, hashes):
    value = harness.digest(path)
    hashes[str(path)] = value
    return value


def verify_sources(sources, hashes):
    for name, expected in sources.items():
        actual = harness.digest(name)
        assert actual == expected, name
        hashes[str(name)] = actual


def validate_result_selection(record):
    """Require ``selected`` to be exactly the best qualified start."""
    valid = [row for row in record["starts"] if row["qualified"]]
    if record.get("selected") is None:
        assert not valid, "qualified start omitted from selected result"
        return False
    assert aggregate.validate_result(record)
    assert "estimate_deg" in record["selected"]
    return True


def validate_baseline_record(record, index, session, hashes, *, require_sources):
    assert record["index"] == index
    assert record["session"] == session
    assert record["method"] == "iid"
    if require_sources:
        assert record.get("sources"), "additional IID result has no source binding"
        verify_sources(record["sources"], hashes)
    return validate_result_selection(record)


def bind_additional_plans(base, hashes):
    frozen_path = HERE / "additional-plan.json"
    assembled_path = base / "plan.json"
    frozen = json.loads(frozen_path.read_text())
    assembled = json.loads(assembled_path.read_text())
    _record_source(frozen_path, hashes)
    _record_source(assembled_path, hashes)
    verify_sources(frozen["source_sha256"], hashes)
    verify_sources(assembled["source_sha256"], hashes)
    assert assembled["source_sha256"][str(frozen_path)] == harness.digest(frozen_path)
    assert assembled["config"] == frozen["config"]
    assert len(assembled["inputs"]) == frozen["count"] == len(frozen["captures"])
    for index, (entry, capture) in enumerate(
        zip(assembled["inputs"], frozen["captures"], strict=True)
    ):
        assert entry["session_id"] == capture["session_id"], index
        assert entry["manifest_sha256"] == capture["manifest_sha256"], index
        for artifact in entry["artifacts"]:
            assert "sha256:" + harness.digest(artifact["path"]) == artifact["sha256"]
            hashes[str(artifact["path"])] = artifact["sha256"].removeprefix("sha256:")
    return assembled


def validate_challenger_metadata(result, base, incumbent_path, hashes, *, additional):
    metadata = result["metadata"]
    assert metadata["variant"] == VARIANT
    expected = {
        "incumbent_iid_sha256": incumbent_path,
    }
    if additional:
        expected.update({
            "screen_frozen_model_sha256": HERE / "source_balance" / "model.py",
            "adapter_sha256": HERE / "source_balance" / "additional_adapter.py",
            "plan_sha256": base / "plan.json",
            "identity_sidecar_sha256": base / "catalogue_identities.json",
            "additional_runner_sha256": HERE / "additional_fit.py",
            "additional_policy_sha256": HERE / "additional-policy.md",
        })
    else:
        expected["identity_sidecar_sha256"] = (
            HERE / "source_balance" / "catalogue_identities.json"
        )
    for key, path in expected.items():
        actual = _record_source(path, hashes)
        assert metadata[key] == actual, key


def _load_challengers(base, stages, hashes, *, additional):
    plan = json.loads((base / "plan.json").read_text())
    results = {}
    for stage in stages:
        folder = HERE / FAMILY / "runs" / stage
        for receipt_path in sorted(folder.glob(f"{VARIANT}_??.receipt.json")):
            receipt = json.loads(receipt_path.read_text())
            index = receipt["index"]
            assert index not in results
            assert receipt_path.name == f"{VARIANT}_{index:02d}.receipt.json"
            assert receipt["family"] == FAMILY
            assert receipt["variant"] == VARIANT
            _record_source(receipt_path, hashes)
            result_path = receipt_path.with_name(f"{VARIANT}_{index:02d}.json")
            result = json.loads(result_path.read_text()) if result_path.exists() else None
            if result is None:
                assert receipt["exit_code"] != 0, "successful challenger receipt has no result"
            qualified = False
            if result is not None:
                assert result["family"] == FAMILY
                assert result["variant"] == VARIANT
                assert result["index"] == index
                assert result["stage"] == stage
                assert result["session"] == plan["inputs"][index]["session_id"]
                verify_sources(result["sources"], hashes)
                incumbent_path = base / "runs" / f"{index:02d}_iid.json"
                validate_challenger_metadata(
                    result, base, incumbent_path, hashes, additional=additional
                )
                structurally_qualified = validate_result_selection(result)
                qualified = bool(receipt["exit_code"] == 0 and structurally_qualified)
                _record_source(result_path, hashes)
            results[index] = {
                "receipt": receipt,
                "result": result,
                "qualified": qualified,
            }
    assert set(results) == set(range(len(plan["inputs"])))
    return results


def _load_baseline(base, index, session, hashes, *, additional):
    result_path = base / "runs" / f"{index:02d}_iid.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else None
    exit_code = None
    terminal = True
    if additional:
        receipt_path = base / "runs" / f"{index:02d}_iid.receipt.json"
        receipt = json.loads(receipt_path.read_text())
        assert receipt_path.name == f"{index:02d}_iid.receipt.json"
        assert receipt["index"] == index
        exit_code = receipt["exit_code"]
        terminal = exit_code == 0
        _record_source(receipt_path, hashes)
        if result is None:
            assert not terminal, "successful IID receipt has no result"
    else:
        assert result is not None, "original-panel IID result is missing"
    qualified = False
    if result is not None:
        structurally_qualified = validate_baseline_record(
            result, index, session, hashes, require_sources=additional
        )
        qualified = bool(terminal and structurally_qualified)
        _record_source(result_path, hashes)
    return result, qualified, exit_code


def summarize_partition(rows):
    matched = [
        row for row in rows
        if row["qualified"] and row["baseline_qualified"]
    ]
    complete = len(matched) == len(rows)
    whole = aggregate.summarize_rows(rows) if complete else None
    summary = {
        "attempts": len(rows),
        "policy_qualified": sum(row["qualified"] for row in rows),
        "policy_failures": sum(not row["qualified"] for row in rows),
        "raw_challenger_qualified": sum(row["raw_challenger_qualified"] for row in rows),
        "iid_fallbacks": sum(row["selection"] == "iid_fallback" for row in rows),
        "whole_panel_status": "complete" if complete else "unavailable",
        "whole_panel_metrics": whole,
        "whole_panel_unavailable_reason": (
            None if complete else "one or more policy or IID baseline outputs are unqualified"
        ),
        "matched_qualified_denominator": len(matched),
        "matched_qualified_metrics": aggregate.summarize_rows(matched) if matched else None,
    }
    # Preserve the preliminary policy's summary field names for existing plots
    # only when those values really have the full declared denominator.
    if whole is not None:
        summary.update(whole)
    return summary


def evaluate(base, stages, output, *, additional):
    hashes = {}
    plan = (
        bind_additional_plans(base, hashes)
        if additional
        else json.loads((base / "plan.json").read_text())
    )
    _record_source(base / "plan.json", hashes)
    attempts = _load_challengers(base, stages, hashes, additional=additional)
    rows = []
    for index, entry in enumerate(plan["inputs"]):
        baseline, baseline_qualified, baseline_exit = _load_baseline(
            base, index, entry["session_id"], hashes, additional=additional
        )
        incumbent = baseline["selected"] if baseline_qualified else None
        attempt = attempts[index]
        challenger = (
            attempt["result"]["selected"] if attempt["qualified"] else None
        )
        selected, kind = select(challenger, incumbent)
        rows.append({
            "index": index,
            "session": entry["session_id"],
            "qualified": selected is not None,
            "selection": kind,
            "baseline_qualified": baseline_qualified,
            "baseline_exit_code": baseline_exit,
            "raw_challenger_qualified": attempt["qualified"],
            "challenger_exit_code": attempt["receipt"]["exit_code"],
            "error_m": harness.distance(selected["estimate_deg"]) if selected else None,
            "baseline_error_m": (
                harness.distance(incumbent["estimate_deg"]) if incumbent else None
            ),
            "common_iid_held_gain": (
                challenger["common_iid"]["held"]
                - challenger["incumbent_common_iid"]["held"]
                if challenger else 0.0
            ),
            "runtime_s": attempt["receipt"]["wall_s"],
        })

    parts = {"all": rows}
    if len(rows) == 32:
        parts["screen"] = [row for row in rows if row["index"] in harness.SCREEN]
        parts["replication"] = [row for row in rows if row["index"] not in harness.SCREEN]
    summaries = {name: summarize_partition(part) for name, part in parts.items()}
    whole = summaries["all"]["whole_panel_metrics"]
    passed = None
    if additional:
        passed = bool(
            len(rows) == 12
            and whole is not None
            and whole["qualified"] == 12
            and whole["paired_wins"] >= 6
            and whole["median_m"] < whole["baseline_median_m"]
            and whole["p90_m"] < whole["baseline_p90_m"]
        )
    _record_source(Path(__file__), hashes)
    _record_source(HERE / "additional-policy.md", hashes)
    document = {
        "schema": "ds11-qualified-source-policy-audit/v1",
        "policy": "qualified source_receiver_equal else qualified original IID",
        "panel": "additional12" if additional else "original32",
        "summaries": summaries,
        "additional_replication_passed": passed,
        "rows": rows,
        "source_sha256": hashes,
    }
    with output.open("x") as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    additional = len(sys.argv) > 1 and sys.argv[1] == "additional"
    evaluate(
        HERE / "additional" if additional else harness.BASE,
        ["additional"] if additional else ["wave1", "wave1_replication"],
        HERE / (
            "policy-additional12-audited.json"
            if additional else "policy-original32-audited.json"
        ),
        additional=additional,
    )
