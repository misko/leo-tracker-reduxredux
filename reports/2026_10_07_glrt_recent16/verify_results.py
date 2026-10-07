"""Streamed inventory, provenance, coverage, and saved-choice audit."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(path.read_text())


def check_digest(path, expected):
    assert digest(path) == expected.removeprefix("sha256:"), str(path)


def check_choice(case):
    """Check candidate-bank closure and fixed hypotheses without rescoring IQ."""
    bank = {item["candidate_id"]: item for item in case["candidate_bank"]}
    assert len(bank) == case["available_candidate_count"]
    unavailable = {item["candidate_rank"] for item in case["unavailable_candidates"]}
    assert not unavailable.intersection(bank)
    assert len(bank) + len(unavailable) == case["saved_candidate_count"]
    if case["status"] != "complete":
        assert not bank and case["status"] == "no_available_candidates"
        return 0
    result = case["evaluation"]
    assert result["status"] == "complete" and result["candidate_count"] == len(bank)
    baseline = result["baseline_winner"]
    assert baseline == result["methods"]["current_coherent_margin"]["winner"]
    common = result["methods"]["current_coherent_margin"]["common_confirmation"]
    for method, item in result["methods"].items():
        rows = item["ranking"]
        assert {entry["candidate_id"] for entry in rows} == set(bank)
        assert len(rows) == len(bank)
        assert item["winner"] == rows[0]
        assert rows == sorted(rows, key=lambda r: (-r["score"], r["candidate_rank"]))
        for entry in rows:
            source = bank[entry["candidate_id"]]
            for key in ("candidate_rank", "epoch_sample", "seed_cfo_hz"):
                assert entry[key] == source[key]
            assert entry["total_cfo_hz"] == entry["seed_cfo_hz"] + entry["residual_cfo_hz"]
        winner = item["winner"]
        later = item["own_fixed_confirmation"]
        assert later["total_cfo_hz"] == winner["total_cfo_hz"]
        assert later["residual_cfo_hz"] == winner["residual_cfo_hz"]
        for reference, values in item["common_confirmation"].items():
            assert values["baseline"] == common[reference]["baseline"]
            for choice in ("baseline", "winner"):
                score = values[choice]
                assert score["margin"] == score["exact_score"] - score["control_score"]
            assert values["margin_difference"] == (
                values["winner"]["margin"] - values["baseline"]["margin"]
            )
            if method == "current_coherent_margin":
                assert values["margin_difference"] == 0
    return len(result["methods"])


def verify():
    folder = HERE / "local/full"
    selection = read(HERE / "selection.json")
    index = read(folder / "index.json")
    assert len(selection["scans"]) == index["complete_scans"] == len(index["receipts"]) == 16
    inventory = {row["session_id"]: row for row in selection["scans"]}
    assert len(inventory) == 16
    history_path = HERE / "receipts/history.json"
    check_digest(history_path, selection["history_receipt_sha256"])
    history = {row["session_id"]: row for row in read(history_path)["items"]}
    complete = []
    for sid, metadata in history.items():
        status = read(HERE / "receipts" / f"{sid}-analysis.json")
        assert status["session_id"] == sid
        assert status["input_manifest_sha256"] == metadata["input_manifest_sha256"]
        if (
            status["metrics_manifest_sha256"]
            and status["checkpoint_visits"] == status["total_visits"]
            and status["total_visits"] > 0
        ):
            complete.append(metadata)
    expected = sorted(complete, key=lambda r: (r["captured_at"], r["session_id"]), reverse=True)[
        :16
    ]
    assert [r["session_id"] for r in expected] == list(inventory)
    sources, paths, totals, scans = {}, {}, Counter(), []
    for scan in selection["scans"]:
        directory = folder / scan["label"]
        receipt = read(directory / "receipt.json")
        assert receipt["status"] == "complete" and not receipt["errors"]
        assert receipt["scan"] == scan
        assert receipt in index["receipts"]
        check_digest(HERE / scan["analysis_receipt"], scan["analysis_receipt_sha256"])
        check_digest(HERE / "selection.json", receipt["selection_sha256"])
        check_digest(directory / "results.jsonl.gz", receipt["archive_sha256"])
        for path, expected_hash in receipt["source_sha256"].items():
            if path in sources:
                assert sources[path] == expected_hash
            sources[path] = expected_hash
        counts, cases, visits, raw_hashes = Counter(), set(), set(), {}
        with gzip.open(directory / "results.jsonl.gz", "rt") as stream:
            for line in stream:
                case = json.loads(line)
                assert case["scan_id"] == scan["session_id"]
                assert case["case_id"] not in cases
                cases.add(case["case_id"])
                visit = case["visit_index"]
                visits.add(visit)
                assert case["first_window_start_ms"] == 120 * case["probe_index"]
                assert case["later_window_start_ms"] == case["first_window_start_ms"] + 40
                if visit in raw_hashes:
                    assert raw_hashes[visit] == case["raw_visit_sha256"]
                raw_hashes[visit] = case["raw_visit_sha256"]
                counts["method_choices_checked"] += check_choice(case)
                counts["cases"] += 1
                counts[case["status"]] += 1
                counts["saved_candidates"] += case["saved_candidate_count"]
                counts["available_candidates"] += case["available_candidate_count"]
                counts["unavailable_candidates"] += len(case["unavailable_candidates"])
        coverage = receipt["coverage"]
        assert len(visits) == coverage["visits_processed"] == scan["total_visits"]
        assert counts["cases"] == coverage["probes_written"] == coverage["probes_expected"]
        assert counts["complete"] == coverage["probes_complete"]
        assert counts["no_available_candidates"] == coverage["empty_banks"]
        for key in ("saved_candidates", "available_candidates", "unavailable_candidates"):
            assert counts[key] == coverage[key]
        errors = receipt["baseline_max_errors"]
        assert max(errors[key] for key in ("exact_score", "control_score", "score")) < 1e-8
        assert errors["total_cfo_hz"] < 1e-3
        totals.update(counts)
        scans.append(
            {
                "label": scan["label"],
                "counts": dict(counts),
                "visits": len(visits),
                "baseline_max_errors": errors,
            }
        )
        paths[str(directory / "results.jsonl.gz")] = receipt["archive_sha256"]
    for path, expected_hash in sources.items():
        check_digest(Path(path), expected_hash)
    result = {
        "passed": True,
        "scans": scans,
        "totals": dict(totals),
        "newest16_at_frozen_receipts_verified": True,
        "source_sha256": sources,
        "result_sha256": paths,
        "verification_source_sha256": digest(Path(__file__)),
    }
    (HERE / "local/verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": True, "scans": len(scans), "totals": dict(totals)}, indent=2))


if __name__ == "__main__":
    verify()
