import numpy as np
import pytest

from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (
    ReceiverPhaseSeed,
    shared_frame_starts,
)
from leo.analysis.starlink.relative_phase import (
    PairedPilotProbe,
    extract_relative_phase,
    refined_pilot,
)
from leo.analysis.starlink.templates import qin_edge_pilot_frame


@pytest.mark.parametrize("edge", ["lower", "upper"])
@pytest.mark.parametrize("authority_error", [-140.0, 100.0])
@pytest.mark.parametrize("rate", [2500000, 10000000])
def test_refinement_recovers_frame_reference(edge, authority_error, rate):
    epoch = round(0.016 * rate)
    count = round(0.04 * rate)
    delta = -619159.5
    frequency = -82137.25
    phase = 0.73
    template = np.asarray(qin_edge_pilot_frame(rate, edge), complex)
    iq = np.zeros((count, 2), complex)
    for start in shared_frame_starts(count, rate, epoch, frame_radius=16):
        indexes = start + np.arange(len(template))
        iq[indexes, 0] = template * np.exp(2j * np.pi * frequency * indexes / rate)
        iq[indexes, 1] = template * np.exp(
            1j * (phase + 2 * np.pi * (frequency + delta) * indexes / rate)
        )
    probe = PairedPilotProbe(
        0,
        epoch,
        (ReceiverPhaseSeed(-82000.0, 0), ReceiverPhaseSeed(-82000.0 + delta + authority_error, 0)),
    )
    observation = refined_pilot(iq, rate, edge, probe, delta + authority_error)
    error = np.angle(
        np.exp(
            1j
            * (
                observation.wrapped_phase_rad
                - phase
                - 2 * np.pi * delta * observation.center_sample / rate
            )
        )
    )
    assert abs(np.degrees(error)) < 0.05
    assert abs(observation.relative_frequency_hz - delta) < 0.1


def test_phase_requires_training_evidence():
    with pytest.raises(ValueError, match="training-half"):
        extract_relative_phase(np.zeros((300000, 2), complex), 2500000, "upper", ())
