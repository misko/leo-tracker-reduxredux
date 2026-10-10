"""Pure bounded visit/window adapter. Concrete read-only storage stays outside."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Window:
    window_id: str
    visit: int
    receiver: int
    probe_start_sample: int
    epoch_sample: int
    offset_samples: float
    acquired_cfo_hz: float
    original_cfo_hz: float
    original_exact: float
    original_control: float
    original_passed: bool
    edge: str = "lower"
    probe_count: int | None = None


def replay(
    windows,
    *,
    expected_ids,
    sample_rate_hz,
    receiver_ids,
    visit_sample_counts,
    read_visit,
    evaluate,
    maximum_visit_bytes,
):
    """Yield every original selected row exactly once, including explicit failures.

    read_visit(visit) returns int16[n,rx,IQ]; evaluate(complex_probe, window, fs)
    owns baseline parity then frozen refinement. No re-acquisition/selection.
    The returned IQ is released before reading the next visit.
    """
    ids = [w.window_id for w in windows]
    if len(ids) != len(set(ids)) or set(ids) != set(expected_ids) or len(ids) != len(expected_ids):
        raise ValueError("original selected membership differs")
    if maximum_visit_bytes <= 0:
        raise ValueError("positive visit resource cap required")
    for visit in sorted({w.visit for w in windows}):
        selected = [w for w in windows if w.visit == visit]
        reason = None
        if sample_rate_hz not in (2_500_000, 10_000_000):
            reason = "unsupported-sample-rate"
        elif visit not in visit_sample_counts:
            reason = "missing-visit-length"
        elif visit_sample_counts[visit] * len(receiver_ids) * 2 * 2 > maximum_visit_bytes:
            reason = "visit-resource-cap"
        if reason:
            for w in selected:
                yield {"window_id": w.window_id, "status": reason}
            continue
        raw = None
        try:
            raw = read_visit(visit)
            if raw.dtype != np.int16 or raw.shape != (
                visit_sample_counts[visit],
                len(receiver_ids),
                2,
            ):
                raise ValueError("unexpected public visit array")
        except Exception as exc:
            del raw
            for w in selected:
                yield {
                    "window_id": w.window_id,
                    "status": "visit-read-failed",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            continue
        try:
            for w in selected:
                probe = None
                try:
                    if w.receiver not in receiver_ids or not w.original_passed:
                        raise ValueError("original selection/admission mismatch")
                    if not np.isfinite(
                        [
                            w.offset_samples,
                            w.acquired_cfo_hz,
                            w.original_cfo_hz,
                            w.original_exact,
                            w.original_control,
                        ]
                    ).all():
                        raise ValueError("nonfinite original candidate")
                    start = w.probe_start_sample
                    count = w.probe_count if w.probe_count is not None else sample_rate_hz // 50
                    if count != sample_rate_hz // 50:
                        raise ValueError("original probe is not supported20ms geometry")
                    stop = start + count
                    if start < 0 or stop > len(raw) or not 0 <= w.epoch_sample < count:
                        raise ValueError("original probe/epoch outside source")
                    iq = raw[start:stop, receiver_ids.index(w.receiver)]
                    probe = iq[:, 0].astype(float) + 1j * iq[:, 1].astype(float)
                    del iq
                    result = evaluate(probe, w, sample_rate_hz)
                    yield {"window_id": w.window_id, "status": "complete", "result": result}
                except Exception as exc:
                    yield {
                        "window_id": w.window_id,
                        "status": "parity-or-window-failed",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                finally:
                    del probe
        finally:
            del raw
