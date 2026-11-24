from copy import deepcopy

import pytest

from leo.contracts.digests import canonical_digest
from reports.ALGO08.v3 import cropped_physical_iq_gate as gate
from tools.pipeline_eval.variants.capture_bursts import inventories, select_document


def test_saved_crop_keeps_clock_and_stereo_content_and_counts_quality_exclusions(monkeypatch):
    monkeypatch.setattr(gate, "MEMBER_VISITS", 2)
    rows = [dict(visit_index=visit, receiver_id=radio, channel=1, edge="lower", actual_rf_hz=11_500_000_000,
                 valid_start_counter=visit*400_000, payload_start_sample=visit*200_000, candidates=[dict(rank=0)])
            for visit in (0, 1, 2, 3, 5) for radio in (0, 1)]
    source = dict(probes=rows, raw_recording_authority_digest=gate.AUTHORITY, input_manifest_sha256=gate.INVENTORY)
    source["analysis_manifest_sha256"] = canonical_digest(["cancellation", gate.AUTHORITY, gate.DETECTOR[7:], rows])
    native = dict(source=source, clock_anchor={"sample_counter": 0}, delivery_clocks=list(range(6)),
                  provenance=dict(detector_sha256=gate.DETECTOR, excluded_windows=[{"visit": 4}], window_count=6,
                                  processed_windows=5))
    before = deepcopy(native)
    projected, retained, excludes = gate.project(native, (0, 2), canonical_digest, inventories, select_document)
    assert native == before
    assert retained == [0, 1, 5] and excludes == 1
    assert projected["clock_anchor"] == native["clock_anchor"]
    assert projected["delivery_clocks"] == native["delivery_clocks"]
    assert projected["source"]["analysis_manifest_sha256"] != source["analysis_manifest_sha256"]
    assert projected["source"]["probes"] == [row if row["visit_index"] in retained else dict(row, candidates=[])
                                             for row in rows]
    with pytest.raises(ValueError, match="every original visit"):
        gate.project(native, (0, 3), canonical_digest, inventories, select_document)
