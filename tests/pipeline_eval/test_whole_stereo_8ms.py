import importlib
from copy import deepcopy
from pathlib import Path

import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
    return [importlib.import_module(name) for name in ("whole_stereo_8ms", "whole_stereo_8ms_trial")]


def sample():
    from full_short_run import checked_recipe
    from leo.contracts.digests import canonical_digest
    from whole_stereo_blocks import signature

    recipe = checked_recipe(eight_ms=True)
    pin = canonical_digest(recipe)
    admitted = tuple(v for v in range(10) if v != 5)
    factor = dict(passed_fractional_margin_gate=True, candidate_rank=0, fractional_tracking_cfo_hz=-1234.)
    rows = [dict(visit_index=v, receiver_id=r, edge="lower", channel=1, actual_rf_hz=10.7e9,
                 valid_start_counter=2_000_000*v, payload_start_sample=2_000_000*v,
                 candidates=[] if v == 2 else [dict(factor)]) for v in admitted for r in (0,1)]
    source = dict(qualified=True, probes=rows, raw_recording_authority_digest="original")
    source["analysis_manifest_sha256"] = signature(source,pin,rows)
    native = dict(source=source, delivery_clocks=list(range(10)), provenance=dict(detector_sha256=pin,
                   scope="cancellation", window_count=10, processed_windows=9, excluded_windows=[{"visit": 5}]))
    return native, recipe


def test_dropped_signed_measurements_cannot_affect_projected_packet(modules):
    from whole_stereo_blocks import signature

    prepare = modules[0].input_stream
    source, recipe = sample()
    paid, _, witness = prepare(source, recipe)
    assert witness["skipped_stereo_visits"] == [3, 7]
    assert witness["paid_native_lanes"] == {"full": 4, "short_primary": 10}
    assert paid["delivery_clocks"] == source["delivery_clocks"]
    assert [r["visit_index"] for r in paid["source"]["probes"] if not r["candidates"]] == [2, 2, 3, 3, 7, 7]
    changed = deepcopy(source)
    for row in changed["source"]["probes"]:
        if row["visit_index"] in witness["skipped_stereo_visits"]:
            row["candidates"][0]["fractional_tracking_cfo_hz"] += 994_000
    source_data = changed["source"]
    source_data["analysis_manifest_sha256"] = signature(source_data, changed["provenance"]["detector_sha256"], source_data["probes"])
    assert prepare(changed, recipe)[0] == paid


def test_repeat_rejects_non_native_8ms_recipe_and_prices_only_short_work(modules):
    native, recipe = sample()
    with pytest.raises(ValueError, match="complete original signed 20/8 ms"):
        modules[0].input_stream(native, dict(recipe, aperture_samples=[200_000, 120_000]))
    _, _, part = modules[0].input_stream(native, recipe)
    archived = dict(acquire=dict(cpu_ns=20e9), native=dict(native_calls={"full":4,"short_primary":14},
                    native_cpu_ns={"full":6e9,"short_primary":7e9}))
    costs = modules[0].price(archived, part, 1.)
    assert costs["short_cpu_pool_s"] == 7.
    assert costs["modeled_short_credit_cpu_s"] == 2.
    assert costs["modeled_incremental_after_planning_cpu_s"] == 1.


def test_omitted_branch_requires_both_arms_no_worse_than_both_controls(modules):
    after = {"c0": {"error_m": 10}, "fitted_c": {"error_m": 11}}
    both = dict(decision="complete", candidate=after, controls={"named": after, "all8": after})
    assert modules[1].followup(both) == "omitted"
    assert modules[1].followup(dict(both, decision="withheld")) == "weak"
    worse = dict(after, fitted_c={"error_m": 12})
    assert modules[1].followup(dict(both, candidate=worse)) == "weak"
