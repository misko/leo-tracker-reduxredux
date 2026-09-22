"""Phase-blind candidate selection and conversion to pure numerical inputs."""

from leo.analysis.starlink.adaptive_dual_rx_phase_extract import ReceiverPhaseSeed
from leo.analysis.starlink.relative_phase import PairedPilotProbe
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs


def relative_phase_priority(visit):
    pairs = _phase_blind_pairs(visit)
    return max(
        (min(a.fractional_margin, b.fractional_margin) for a, b, _, _ in pairs), default=None
    )


def relative_phase_probes(visit):
    output = []
    for index in sorted({p.probe_index for p in visit.probes}):
        subset = visit.model_copy(
            update={"probes": tuple(p for p in visit.probes if p.probe_index == index)}
        )
        pairs = _phase_blind_pairs(subset)
        if pairs:
            a, b, _, start = pairs[0]
            output.append(
                PairedPilotProbe(
                    start,
                    a.integer_epoch_sample,
                    tuple(
                        ReceiverPhaseSeed(
                            c.acquired_cfo_hz,
                            c.integer_epoch_sample + (c.fractional_epoch_offset_samples or 0),
                        )
                        for c in (a, b)
                    ),
                )
            )
    return tuple(output)
