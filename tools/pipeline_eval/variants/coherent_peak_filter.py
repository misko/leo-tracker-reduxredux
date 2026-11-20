"""Suppress ambiguous ordinary peaks using two earlier visits of the same RF lane."""

from collections import defaultdict, deque
from dataclasses import dataclass

FRAME_RATE_HZ = 750
FOLD_HZ = 1 / 4.4e-6
MAX_GAP_S = 2.6
MAX_CFO_RATE_HZ_S = 6500
MAX_EPOCH_DRIFT_FRACTION = 350 / 10_000_000


def wrapped(value, period):
    return (value + period / 2) % period - period / 2


@dataclass(frozen=True)
class Peak:
    visit: int
    counter: int
    epoch: float
    cfo_hz: float

    @classmethod
    def from_candidate(cls, probe, counter, candidate):
        return cls(
            probe["visit_index"],
            counter,
            candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"],
            candidate["fractional_tracking_cfo_hz"],
        )


def step(left, right, rate):
    samples = right.counter - left.counter
    seconds = samples / rate
    if left.visit == right.visit or not 0 < seconds <= MAX_GAP_S:
        return None
    delta_hz = wrapped(right.cfo_hz - left.cfo_hz, FOLD_HZ)
    epoch = wrapped(samples + right.epoch - left.epoch, rate / FRAME_RATE_HZ)
    if (
        abs(delta_hz) > MAX_CFO_RATE_HZ_S * seconds
        or abs(epoch) > rate * MAX_EPOCH_DRIFT_FRACTION * seconds
    ):
        return None
    return seconds, delta_hz, epoch


def continuation(previous, first_step, current, rate, rf, probe_seconds):
    second_step = step(previous, current, rate)
    if second_step is None:
        return False
    dt0, cfo0, epoch0 = first_step
    dt1, cfo1, epoch1 = second_step
    # Delay's derivative is minus fractional Doppler. Subtracting the two
    # interval slopes eliminates a constant oscillator/sample-clock error.
    expected = dt1 * (epoch0 / dt0 - rate * (cfo0 + cfo1) / (2 * rf))
    residual = wrapped(epoch1 - expected, rate / FRAME_RATE_HZ)
    # A sample at each phase endpoint and one inverse-probe-duration CFO bin.
    tolerance = 2 * (1 + dt1 / dt0) + rate * dt1 / (rf * probe_seconds)
    return abs(residual) <= tolerance


def filter_document(document):
    """Scan source order, retaining original factors on ambiguity or missing support."""
    source = document["source"]
    rate = source["sample_rate_hz"]
    probe_seconds = source["probe_ms"] / 1000
    lanes = defaultdict(lambda: deque(maxlen=2))
    probes = []
    counts = dict(
        probes=len(source["probes"]),
        candidate_rows_before=0,
        passing_before=0,
        passing_after=0,
        positive_probes=0,
        ambiguous_probes=0,
        anchored_ambiguous_probes=0,
        reduced_probes=0,
        changed_winners=0,
    )
    last = {}
    for probe in source["probes"]:
        rf = probe["actual_rf_hz"]
        key = probe["receiver_id"], probe["channel"], rf
        counter = probe["valid_start_counter"] + round(probe["probe_start_ms"] * rate / 1000)
        if key in last and counter <= last[key]:
            raise ValueError("ordinary probe counters must increase within an RF lane")
        last[key] = counter
        candidates = probe["candidates"]
        passing = [p for p in candidates if p["passed_fractional_margin_gate"] is True]
        counts["candidate_rows_before"] += len(candidates)
        counts["passing_before"] += len(passing)
        counts["passing_after"] += len(passing)
        if passing:
            counts["positive_probes"] += 1
            winner = max(passing, key=lambda p: (p["fractional_margin"], -p["candidate_rank"]))
            history = lanes[key]
            if len(passing) > 1:
                counts["ambiguous_probes"] += 1
                initial = step(*history, rate) if len(history) == 2 else None
                if initial is not None:
                    counts["anchored_ambiguous_probes"] += 1
                    supported = [
                        peak
                        for peak in passing
                        if continuation(
                            history[-1],
                            initial,
                            Peak.from_candidate(probe, counter, peak),
                            rate,
                            rf,
                            probe_seconds,
                        )
                    ]
                    if len(supported) == 1:
                        keep = supported[0]
                        probe = dict(
                            probe,
                            candidates=[
                                p
                                for p in candidates
                                if p is keep or p["passed_fractional_margin_gate"] is not True
                            ],
                        )
                        counts["reduced_probes"] += 1
                        counts["changed_winners"] += keep is not winner
                        counts["passing_after"] -= len(passing) - 1
            # Keep strict winners as anchors. A past intervention cannot seed
            # its own future support or manufacture a new positive probe.
            if history and history[-1].visit == probe["visit_index"]:
                history[-1] = Peak.from_candidate(probe, counter, winner)
            else:
                history.append(Peak.from_candidate(probe, counter, winner))
        probes.append(probe)
    return dict(document, source=dict(source, probes=probes)), counts
