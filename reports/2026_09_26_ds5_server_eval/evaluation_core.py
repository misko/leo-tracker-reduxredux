"""Research-only comparison and single-worker arrival replay; no detector/I/O.

Inputs must already use a common rate-independent timing coordinate. The
reference is a detector comparator, not real-signal ground truth.
"""
import math
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True)
class Candidate:
    fractional_complete: bool
    margin: float
    cfo_hz: float
    epoch_seconds: float
    window_index: int

    def __post_init__(self):
        if not all(math.isfinite(x) for x in (self.margin, self.cfo_hz, self.epoch_seconds)):
            raise ValueError("candidate values must be finite")
        if self.window_index < 0:
            raise ValueError("window index must be nonnegative")

    @property
    def positive(self):
        return self.fractional_complete and self.margin > 0.025


def matches(reference, proposed, *, period_seconds=1 / 750,
            maximum_timing_error_seconds=2e-6, maximum_cfo_error_hz=8000):
    """Diagnostic identity gate, with circular timing on the pilot lattice.

    Different observation windows are not comparable here. Tracking with different
    windows requires an explicit causal trajectory association instead.
    """
    if (not all(math.isfinite(x) for x in (period_seconds, maximum_timing_error_seconds,
                                          maximum_cfo_error_hz))
            or period_seconds <= 0 or maximum_timing_error_seconds < 0
            or maximum_cfo_error_hz < 0):
        raise ValueError("matching bounds must be nonnegative and period positive")
    delta = abs((proposed.epoch_seconds - reference.epoch_seconds + period_seconds / 2)
                % period_seconds - period_seconds / 2)
    return (reference.window_index == proposed.window_index
            and abs(proposed.cfo_hz - reference.cfo_hz) <= maximum_cfo_error_hz
            and delta <= maximum_timing_error_seconds)


def compare_cases(reference, proposed):
    """Maps case IDs to candidate lists or None (unprocessed).

Missing or unknown output is not absence. The unit of retention is a case with
at least one matched reference-positive candidate, not a count of satellites.
    """
    if reference.keys() != proposed.keys():
        raise ValueError("case inventories must match, including unknown cases")
    result = dict(cases=len(reference), reference_positive_cases=0,
                  retained_reference_positive_cases=0, lost_reference_positive_cases=0,
                  additional_positive_cases=0, unknown_cases=0,
                  reference_unknown_cases=0)
    for key, baseline in reference.items():
        candidates = proposed[key]
        if baseline is None:
            result['reference_unknown_cases'] += 1
        if candidates is None:
            result['unknown_cases'] += 1
        positive_baseline = [c for c in (baseline or ()) if c.positive]
        positive_proposed = [c for c in (candidates or ()) if c.positive]
        if positive_baseline:
            result['reference_positive_cases'] += 1
            retained = any(matches(b, p) for b in positive_baseline for p in positive_proposed)
            result['retained_reference_positive_cases' if retained
                   else 'lost_reference_positive_cases'] += 1
        elif baseline is not None and positive_proposed:
            result['additional_positive_cases'] += 1
    n = result['reference_positive_cases']
    result['reference_relative_retention'] = (
        result['retained_reference_positive_cases'] / n if n else None)
    return result


@dataclass(frozen=True)
class VisitJob:
    session_id: str
    visit_index: int
    start_seconds: float
    end_seconds: float
    receiver_service_ms: tuple[float, ...]
    processed: bool = True

    def __post_init__(self):
        values = (self.start_seconds, self.end_seconds, *self.receiver_service_ms)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("nonfinite arrival or cost")
        if self.end_seconds <= self.start_seconds or any(v < 0 for v in self.receiver_service_ms):
            raise ValueError("invalid source span or service cost")
        if self.processed and not self.receiver_service_ms:
            raise ValueError("processed jobs require receiver costs")


def replay_serial_worker(jobs, *, speed_factor=1.0):
    """FIFO replay of completed recorded dwells, serial receivers, one worker.

Each independent session starts with an empty queue. Costs include all
preprocessing supplied by the caller. speed_factor is an illustrative scenario,
not a conversion from desktop timing to ARM. Unprocessed arrivals stay unknown.
    """
    if not math.isfinite(speed_factor) or speed_factor <= 0:
        raise ValueError("speed factor must be finite and positive")
    finishes, previous_end, seen = {}, {}, set()
    rows = []
    for job in jobs:
        key = (job.session_id, job.visit_index)
        if key in seen or job.start_seconds < previous_end.get(job.session_id, -math.inf):
            raise ValueError("duplicate, overlapping or out-of-order visits")
        seen.add(key)
        previous_end[job.session_id] = job.end_seconds
        if not job.processed:
            rows.append({'session_id': job.session_id, 'visit_index': job.visit_index,
                         'status': 'unknown', 'queue_ms': None, 'completion_age_ms': None})
            continue
        ready = job.end_seconds
        begin = max(ready, finishes.get(job.session_id, ready))
        service_ms = sum(job.receiver_service_ms) / speed_factor
        finish = begin + service_ms / 1000
        finishes[job.session_id] = finish
        rows.append({'session_id': job.session_id, 'visit_index': job.visit_index,
                     'status': 'processed', 'service_ms': service_ms,
                     'queue_ms': (begin - ready) * 1000,
                     'completion_age_ms': (finish - job.start_seconds) * 1000,
                     'post_dwell_latency_ms': (finish - ready) * 1000})
    processed = [row for row in rows if row['status'] == 'processed']
    return {'scope': 'recorded-arrival single-worker cost replay, not hardware qualification',
            'visits': len(rows), 'processed_visits': len(processed),
            'unknown_visits': len(rows) - len(processed),
            'median_service_ms': (
                median([r['service_ms'] for r in processed]) if processed else None),
            'maximum_queue_ms': max((r['queue_ms'] for r in processed), default=None),
            'maximum_completion_age_ms': max(
                (r['completion_age_ms'] for r in processed), default=None),
            'rows': rows}
