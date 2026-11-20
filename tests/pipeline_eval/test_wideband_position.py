from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.wideband_position import compose


def _probe(visit, receiver):
    return dict(
        visit_index=visit,
        receiver_id=receiver,
        valid_start_counter=visit * 200_000,
        candidates=[dict(candidate_rank=0, fractional_tracking_cfo_hz=1.0)],
    )


def _input():
    document = dict(
        source=dict(
            probes=[_probe(visit, receiver) for visit in (0, 1, 2) for receiver in (0, 1)],
            input_manifest_sha256="capture",
            analysis_manifest_sha256="archive-analysis",
        ),
        provenance=dict(run_id="original", excluded_windows=[{"visit": 3}]),
        delivery_clocks=[{"clock": 99}],
    )
    receipt = dict(
        producer=dict(run_id="original", input_manifest_sha256="capture"),
        windows=[
            dict(
                visit=visit,
                iq_sha256=f"iq-{visit}",
                sample_start=visit * 200_000,
                production=[_probe(visit, rx) for rx in (0, 1)],
                wideband=[_probe(visit, rx) for rx in (0, 1)],
            )
            for visit in (0, 2)
        ],
        archive_sha256="archive",
        replay_sha256="kernel",
    )
    return document, receipt


def test_splice_retains_native_float_changes_only_on_measured_probes():
    document, receipt = _input()
    before = deepcopy(document)
    fresh = receipt["windows"][0]["wideband"][1]["candidates"][0]
    fresh["fractional_tracking_cfo_hz"] += 1e-12
    result, audit = compose(document, receipt)
    assert document == before
    assert result["source"]["probes"][1]["candidates"][0] == fresh
    assert result["source"]["probes"][1]["candidates"][0]["fractional_tracking_cfo_hz"] != 1
    assert result["source"]["probes"][2:4] == before["source"]["probes"][2:4]
    assert result["delivery_clocks"] == before["delivery_clocks"]
    assert result["provenance"]["excluded_windows"] == before["provenance"]["excluded_windows"]
    assert audit["changed_probe_rows"] == 1
    assert audit["changed_candidate_fields"] == {"fractional_tracking_cfo_hz": 1}


def test_splice_rejects_drifted_archive_or_candidate_support():
    document, receipt = _input()
    with pytest.raises(ValueError, match="no native numerical change"):
        compose(document, receipt)
    receipt["windows"][0]["wideband"][1]["valid_start_counter"] += 1
    with pytest.raises(ValueError, match="different probe support"):
        compose(document, receipt)
    receipt["windows"][0]["wideband"][1]["valid_start_counter"] -= 1
    document["source"]["probes"][0]["candidates"][0]["fractional_tracking_cfo_hz"] += 1
    with pytest.raises(ValueError, match="differs from the archive"):
        compose(document, receipt)
