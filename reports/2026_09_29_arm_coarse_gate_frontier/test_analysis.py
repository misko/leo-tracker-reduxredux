import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze import BASELINE, COHORT, apply, candidate_rate, frozen


def test_gate_preserves_real_candidate_objects_and_dynamic_inventory():
    manifest = json.loads((COHORT / "manifest.json").read_text())
    selected = manifest["selected"]
    native = frozen.load_native(COHORT / "rows.jsonl")
    rates = candidate_rate(selected)
    case = next(case for case, rate in rates.items() if rate == 2500000)
    one = {case: copy.deepcopy(native[case])}
    gated, retained, by_rate = apply(one, {case: 2500000},
        lambda row, index, rate: row[index]["coarse_score"] >= 0.2)
    original = [candidate for row in one[case].values() for candidate in row["candidates"]]
    actual = [candidate for row in gated[case].values() for candidate in row["candidates"]]
    assert retained == len(actual) == by_rate["2500000"]
    assert all(candidate in original for candidate in actual)
    assert all(row["candidate_count"] == len(row["candidates"])
               for row in gated[case].values())


def test_frozen_one_to_one_matcher_observes_filtered_inventory_without_scores():
    manifest = json.loads((COHORT / "manifest.json").read_text())
    selected = manifest["selected"]
    native = frozen.load_native(COHORT / "rows.jsonl")
    baseline = frozen.load_baseline(BASELINE)
    rates = candidate_rate(selected)
    # Selection is coarse-only. No result score is constructed or changed.
    gated, _, _ = apply(native, rates,
        lambda row, index, rate: row[index]["coarse_score"] >= 0.152)
    summary = frozen.summarize(selected, baseline, gated)
    assert summary["totals"]["candidates"] == 123904  # immutable reference inventory
    assert summary["totals"]["recovered_positive_hits"] == 19226
