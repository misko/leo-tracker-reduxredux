from copy import deepcopy

import numpy as np

from tools.research.evaluate_random_source_phase import _evaluate_receiver, _pairs


def _rows():
    rows = []
    for group in range(6):
        for index in range(6):
            sample = group * 15 + index + 2
            time = sample / 750
            phase = 2 * np.pi * (1000 * time + 0.5 * 2000 * time**2)
            z = np.exp(1j * phase)
            fold = dict(
                channel_vector=[[z.real, z.imag]] * 8,
                absolute_cfo_hz=1000 + 2000 * time,
                exact_coherence=0.9,
                control_coherence=0.01,
            )
            rows.append(
                dict(
                    receiver_id=0,
                    group_id=group,
                    frame=dict(
                        frame_start_sample=sample,
                        reference_sample=sample,
                        training_supported=True,
                        even=deepcopy(fold),
                        odd=deepcopy(fold),
                    ),
                )
            )
    return rows


def test_held_odd_mutation_cannot_change_frequency_or_phase_rate_fit():
    rows = _rows()
    baseline = _evaluate_receiver(rows, 750, 0)
    changed = deepcopy(rows)
    for index, row in enumerate(changed):
        z = np.exp(1j * (index * 0.47))
        row["frame"]["odd"]["channel_vector"] = [[z.real, z.imag]] * 8
        row["frame"]["odd"]["absolute_cfo_hz"] += 10000
    altered = _evaluate_receiver(changed, 750, 0)
    for key in ("linear_cfo_at_reference_hz", "linear_cfo_rate_hz_s", "fitted_phase_bias_hz"):
        assert baseline[key] == altered[key]
    assert (
        baseline["phase_informed_rate"]["selected_rate_hz_s"]
        == altered["phase_informed_rate"]["selected_rate_hz_s"]
    )
    assert altered["held_odd_cfo_rms_hz"]["linear"] > 9000
    assert baseline["held_odd_cfo_rms_hz"]["linear"] < 1e-8


def test_pairing_does_not_bridge_unsupported_frame():
    rows = _rows()[:6]
    rows[2]["frame"]["training_supported"] = False
    pairs = _pairs(rows, "even", (0,), 750)
    assert len(pairs) == 2
    assert all(p["right_reference_sample"] - p["left_reference_sample"] == 1 for p in pairs)
