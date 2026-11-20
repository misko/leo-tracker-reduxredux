"""Single chronological raw lane using only its own preceding detector outputs."""

import inspect
import json
import os
import sys
from collections import Counter
from time import process_time_ns
from unittest.mock import patch

from tools.pipeline_eval.qualification import recording_to_v5 as recording
from tools.pipeline_eval.qualification import whole_memory_chain_worker as raw
from tools.pipeline_eval.variants import causal_track_scout, hinted_glrt
from tools.pipeline_eval.variants.coherent_peak_filter import Peak


def choose(candidates):
    return max(
        (c for c in candidates if c["passed_fractional_margin_gate"] is True),
        key=lambda c: (c["fractional_margin"], -c["candidate_rank"]),
        default=None,
    )


def lane(probe):
    return tuple(probe[k] for k in ("receiver_id", "channel", "actual_rf_hz", "edge"))


class Feedback:
    def __init__(self):
        self.scout = causal_track_scout.TrackScout(10_000_000)
        self.previous = -1
        self.native_cpu_ns = self.feedback_cpu_ns = 0
        self.counts = Counter()
        self.pending = None

    def begin(self, window, receivers):
        if tuple(receivers) != (0, 1) or self.pending is not None:
            raise ValueError("expected exactly one chronological dual-RX detector invocation")
        visit = int(window.acquisition["global_visit"])
        if visit <= self.previous:
            raise ValueError("past receiver data must commit before the next visit")
        self.previous = visit
        started = process_time_ns()
        probes = [recording._probe(window, rx, ()) for rx in receivers]
        centers = [self.scout.propose(lane(p), p["valid_start_counter"]) for p in probes]
        self.feedback_cpu_ns += process_time_ns() - started
        self.counts["visits"] += 1
        self.counts["proposal_lanes"] += sum(bool(x) for x in centers)
        self.counts["proposed_centers"] += sum(map(len, centers))
        self.pending = probes, centers

    def hints(self):
        if self.pending is None:
            raise ValueError("detector entered without two committed proposals")
        return tuple(items[0][0] if items else None for items in self.pending[1])

    def commit(self, output, trace):
        started = process_time_ns()
        probes, centers = self.pending
        if [row["receiver_id"] for row in output["rows"]] != [0, 1]:
            raise ValueError("native result lost a receiver")
        winners = []
        for probe, result in zip(probes, output["rows"], strict=True):
            candidates = (recording._from_native(i, c) for i, c in enumerate(result["candidates"]))
            selected = choose(c for c in candidates if c is not None)
            counter = probe["valid_start_counter"]
            point = Peak.from_candidate(probe, counter, selected) if selected else None
            self.scout.observe(lane(probe), counter, point)
            self.counts["positive_lanes"] += point is not None
            winners.append([point.epoch, point.cfo_hz] if point else None)
        applied = []
        if trace:
            for row, hint in zip(trace, self.hints(), strict=True):
                old, new = row["ordinary"], row["selected"]
                changed = old != new
                if (
                    len(old) != len(new)
                    or len(new) > 4
                    or old[:3] != new[:3]
                    or (changed and (len(new) != 4 or new[-1] != hint))
                ):
                    raise ValueError("hint ABI changed the frozen scout slot budget")
                applied.append(changed)
                self.counts["applied"] += changed
        if any(centers):
            self.counts["trace_visits"] += 1
            print(
                "hint-trace: "
                + recording.encoded(
                    dict(
                        visit=self.previous,
                        counter=probes[0]["valid_start_counter"],
                        channel=probes[0]["channel"],
                        centers=[[p[0] for p in lane] for lane in centers],
                        winners=winners,
                        applied=applied,
                        slots=trace,
                    )
                ),
                file=sys.stderr,
                flush=True,
            )
        self.feedback_cpu_ns += process_time_ns() - started
        self.pending = None


def serial_stream(coordinate):
    source = inspect.getsource(recording.stream_range)
    original = "for index in range(worker, len(segments), 2):"
    dispatch = "status = analyze_window(window, source.receiver_ids, None, policy, detector=detect)"
    if source.count(original) != 1 or source.count(dispatch) != 1:
        raise ValueError("the authenticated raw runner has a different scheduling anchor")
    code = source.replace(original, "for index in range(len(segments)):")
    code = code.replace(
        dispatch,
        (
            "status = coordinate(analyze_window, window, source.receiver_ids, None, "
            "policy, detector=detect)"
        ),
    )
    namespace = dict(vars(recording), coordinate=coordinate)
    exec(compile(code, recording.__file__, "exec"), namespace)
    return namespace["stream_range"]


def run(mode):
    from leo.analysis.starlink import native_short_window

    state = Feedback()
    native = native_short_window.NativeShortWindow

    class SerialNative(native):
        def analyze(self, samples, *, include_timings=False):
            hints = state.hints()
            if mode == "hinted" and any(h is not None for h in hints):
                if not hasattr(self, "_hint_call"):
                    self._hint_call = hinted_glrt.HintedCall(self)
                with patch.object(self, "analyze", native.analyze.__get__(self)):
                    started = process_time_ns()
                    output, trace = self._hint_call(samples, hints=hints, timings=include_timings)
                    state.native_cpu_ns += process_time_ns() - started
            else:
                started = process_time_ns()
                output = super().analyze(samples, include_timings=include_timings)
                state.native_cpu_ns += process_time_ns() - started
                trace = None
            state.commit(output, trace)
            return output

    def coordinate(analyze_window, window, *args, detector, **kwargs):
        def call(current, receivers):
            state.begin(current, receivers)
            return detector(current, receivers)

        return analyze_window(window, *args, detector=call, **kwargs)

    with (
        patch.object(recording, "stream_range", serial_stream(coordinate)),
        patch.object(native_short_window, "NativeShortWindow", SerialNative),
    ):
        raw.raw_lane()
    if state.pending is not None or state.scout.pending:
        raise ValueError("detector ended with uncommitted input")
    print(
        "hint-summary: "
        + json.dumps(
            dict(
                counts=state.counts,
                native_cpu_ns=state.native_cpu_ns,
                feedback_cpu_ns=state.feedback_cpu_ns,
                mode=mode,
            ),
            sort_keys=True,
        ),
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    selected = os.environ["LEO_HINTED_WHOLE_ROLE"]
    if selected not in {"stock", "hinted"}:
        raise ValueError("unknown private detector variant")
    run(selected)
