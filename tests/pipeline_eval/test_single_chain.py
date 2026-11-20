"""Check that one-receiver experiments keep the recorded sample and probe authorities."""

from copy import deepcopy

import numpy as np
import pytest

from tools.pipeline_eval.qualification.single_chain_trial import compare_measurement
from tools.pipeline_eval.variants.single_chain import analyze_native, project_document


@pytest.mark.parametrize("receiver", [0, 1])
def test_native_receives_only_the_requested_physical_lane(receiver):
    samples = np.arange(32, dtype="<i2").reshape(8, 2, 2)
    original = samples.copy()

    class Detector:
        receiver_count = 1

        def analyze(self, selected, *, include_timings):
            assert selected.shape == (8, 1, 2)
            assert selected.dtype == samples.dtype
            assert selected.flags.c_contiguous and include_timings
            np.testing.assert_array_equal(selected[:, 0], samples[:, receiver])
            return dict(rows=[dict(receiver_id=0, candidates=["one"])], detector_cpu_ms=4)

    result = analyze_native(Detector(), samples, receiver, include_timings=True)

    assert result == dict(rows=[dict(receiver_id=receiver, candidates=["one"])], detector_cpu_ms=4)
    np.testing.assert_array_equal(samples, original)


def test_native_rejects_dual_context_before_running_detector():
    class Dual:
        receiver_count = 2

    with pytest.raises(ValueError, match="single-receiver native context"):
        analyze_native(Dual(), np.zeros((8, 2, 2), dtype="<i2"))


def test_factor_projection_empties_unmeasured_lane_without_changing_recorded_authority():
    probes = [
        dict(
            receiver_id=rx,
            visit_index=visit,
            channel=channel,
            valid_start_counter=counter,
            candidates=[dict(candidate_rank=2, fractional_tracking_cfo_hz=200 * (rx + 1))],
        )
        for visit, channel, counter in ((0, 1, 553), (2, 8, 2045))
        for rx in (0, 1)
    ]
    document = dict(
        source=dict(
            probes=probes,
            radio_id="radio-a",
            analysis_manifest_sha256="analysis",
            raw_recording_authority_digest="sealed-input",
        ),
        provenance=dict(window_count=3, excluded_windows=[dict(visit=1)]),
        clock_anchor=dict(sample_counter=553),
        delivery_clocks=[13, 32, 45],
        last_sample_counter=2445,
    )
    original = deepcopy(document)
    rx0 = project_document(document)
    rx1 = project_document(document, 1)

    assert document == original
    for receiver, selected in enumerate((rx0, rx1)):
        assert selected == project_document(document, receiver)
        assert selected["source"]["analysis_manifest_sha256"] != "analysis"
        assert selected["source"]["raw_recording_authority_digest"] == "sealed-input"
        assert selected["clock_anchor"] == document["clock_anchor"]
        assert selected["delivery_clocks"] == document["delivery_clocks"]
        assert selected["last_sample_counter"] == document["last_sample_counter"]
        assert (
            selected["provenance"]["excluded_windows"] == document["provenance"]["excluded_windows"]
        )
        assert selected["source"]["probes"] == [
            probe if probe["receiver_id"] == receiver else dict(probe, candidates=[])
            for probe in probes
        ]
    assert rx0["source"]["analysis_manifest_sha256"] != rx1["source"]["analysis_manifest_sha256"]


def test_complete_native_parity_requires_same_counter_and_empty_unmeasured_factors():
    document = dict(
        source=dict(
            analysis_manifest_sha256="archived",
            probes=[
                dict(
                    visit_index=5,
                    receiver_id=rx,
                    channel=4,
                    valid_start_counter=987,
                    candidates=[dict(fractional_tracking_cfo_hz=rx)],
                )
                for rx in (0, 1)
            ],
        ),
        provenance=dict(
            window_count=1, processed_windows=1, invalid_capture=0, excluded_windows=[]
        ),
        clock_anchor=dict(sample_counter=987),
        delivery_clocks=[13],
        last_sample_counter=200_987,
    )
    measured = deepcopy(project_document(document))
    assert compare_measurement(document, measured) == dict(
        measured_probes=1,
        measured_candidates=1,
        exact_measured_probes=1,
        candidate_list_mismatches=[],
    )

    measured["source"]["probes"][0]["candidates"][0]["fractional_tracking_cfo_hz"] = 4
    difference = compare_measurement(document, measured)
    assert difference["exact_measured_probes"] == 0
    assert difference["candidate_list_mismatches"][0]["visit"] == 5

    changed_clock = dict(measured, last_sample_counter=200_986)
    with pytest.raises(ValueError, match="recording authorities differ"):
        compare_measurement(document, changed_clock)

    measured["source"]["probes"][1]["candidates"] = [dict(fractional_tracking_cfo_hz=7)]
    with pytest.raises(ValueError, match="RX1 probe slot empty"):
        compare_measurement(document, measured)
