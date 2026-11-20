import copy
import gzip
import json
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification import fifth_completion as trial
from tools.pipeline_eval.qualification import fifth_completion_results as results


def test_roster_is_the_complete_frozen_difference():
    stock = [f"case-{i:02d}" for i in range(12)]
    previous = [*stock[:2], *[f"earlier-{i}" for i in range(6)]]
    assert trial.roster(list(reversed(stock)), stock, previous) == stock[2:]
    with pytest.raises(ValueError, match="two shared cases"):
        trial.roster(stock, stock, [*previous[1:], "earlier-new"])
    with pytest.raises(ValueError, match="two shared cases"):
        trial.roster(stock, [*stock[1:], stock[-1]], previous)


def document():
    return dict(
        clock_anchor={"utc_ns": 123},
        delivery_clocks=[{"counter": 200}],
        last_sample_counter=456,
        provenance=dict(run_id="stock", detector_sha256="000", excluded_windows=[5]),
        source=dict(
            analysis_manifest_sha256="111",
            timing="sample counter",
            probes=[
                dict(visit_index=0, channel=7, receiver_id=0, candidates=[]),
                dict(visit_index=0, channel=7, receiver_id=1, candidates=[]),
            ],
        ),
    )


def test_check_both_receiver_positions_on_even_ungated_probes():
    stock = document()
    new = copy.deepcopy(stock)
    new["source"]["analysis_manifest_sha256"] = "222"
    new["provenance"].update(run_id="fifth", detector_sha256="333")
    new["source"]["probes"][0]["candidates"].append(
        dict(candidate_rank=0, passed_fractional_margin_gate=True, fractional_margin=0.04)
    )
    audit = results.comparable_probes(stock, new)
    assert audit["probes"] == 2
    assert audit["new_positive_probes"] == 1
    assert audit["lost_positive_probes"] == 0
    new["source"]["probes"].reverse()
    with pytest.raises(ValueError, match="probe metadata or order"):
        results.comparable_probes(stock, new)
    new["source"]["probes"].reverse()
    new["provenance"]["excluded_windows"] = [6]
    with pytest.raises(ValueError, match="exclusions"):
        results.comparable_probes(stock, new)


def test_native_hash_is_bound_to_uncompressed_measurement(tmp_path):
    data = json.dumps(document()).encode()
    path = tmp_path / "native.json.gz"
    path.write_bytes(gzip.compress(data, mtime=0))
    assert results.native_data(path, sha256(data).hexdigest()) == document()
    with pytest.raises(ValueError, match="uncompressed bytes"):
        results.native_data(path, sha256(path.read_bytes()).hexdigest())


def test_pairwise_calibration_deltas_never_impute_failed_position():
    rows = [
        dict(
            id="case",
            arm=arm,
            method=method,
            status="timed_out" if error is None else "ok",
            error_km=error,
            conditional_rms_hz=error,
            frequency_score=error,
            observations=error,
            tracks=error,
        )
        for arm, a, b in (("c0", 3, 2), ("fitted_c", None, 4))
        for method, error in ((trial.METHOD, a), (results.PRIMARY, b))
    ]
    pairs, summary = results.paired_scores(rows)
    assert [(r["delta_error_km"], r["fifth_status"]) for r in pairs] == [
        (1, "ok"),
        (None, "timed_out"),
    ]
    assert summary["c0"]["error_km"]["n"] == 1
    assert summary["fitted_c"]["error_km"]["n"] == 0
