from copy import deepcopy

import numpy as np
import pytest

from tools.pipeline_eval.qualification import capture_raw_boundary as raw
from tools.pipeline_eval.qualification import capture_raw_positive as coverage


def example_probe(receiver=0, visit=0, epoch=13):
    return dict(
        visit_index=visit,
        receiver_id=receiver,
        valid_start_counter=10_000,
        candidates=[dict(integer_epoch_sample=epoch, passed_fractional_margin_gate=True)],
    )


def test_raw_fingerprint_detects_adc_order_and_support_change():
    iq = np.arange(72, dtype="<i2").reshape(18, 2, 2)
    assert raw.fingerprint(iq) == raw.fingerprint(iq.copy())
    assert raw.fingerprint(iq) != raw.fingerprint(iq[:, ::-1])
    assert raw.fingerprint(iq) != raw.fingerprint(iq[1:])


def test_metadata_comparison_keeps_clock_authority_separate_from_candidates():
    capture = dict(
        source={"probes": [example_probe()]},
        clock_anchor={},
        delivery_clocks=["A"],
        last_sample_counter=20_000,
    )
    ordinary = deepcopy(capture)
    ordinary["source"]["probes"][0]["candidates"] = []
    assert raw.compare_clocks(capture, ordinary)["changed_metadata"] == 0
    ordinary["source"]["probes"][0]["valid_start_counter"] += 1
    ordinary["delivery_clocks"] = ["B"]
    report = raw.compare_clocks(capture, ordinary)
    assert report["changed_metadata"] == 1
    assert report["exact"] == dict(
        clock_anchor=True, delivery_clocks=False, last_sample_counter=True
    )


def test_duplicate_probe_keys_fail_and_positive_check_preserves_order():
    duplicate = {"source": {"probes": [example_probe(), example_probe()]}}
    with pytest.raises(ValueError, match="one scheduled probe"):
        raw.index_probes(duplicate)
    cohort = [
        dict(policy_status="processed", production=[example_probe(visit=i)]) for i in range(4)
    ]
    cohort[0]["production"][0]["candidates"][0]["passed_fractional_margin_gate"] = False
    assert [row["production"][0]["visit_index"] for row in coverage.positive_visits(cohort)] == [
        1,
        2,
    ]
