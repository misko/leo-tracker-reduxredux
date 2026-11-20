"""Confirm two current-primary pilot epochs against the partner's own CI16."""

import ctypes as ct
from threading import Lock
from time import perf_counter_ns, thread_time_ns

import numpy as np

ENTRY = "leo_single_rx_glrt_analyze_partner_v1"
RATE = 10_000_000
FRAME = round(RATE / 750)
MARGIN = 0.025


def primary_centers(row):
    passing = []
    for rank, candidate in enumerate(row["candidates"]):
        fit = candidate["fractional_epoch"]
        if fit["status"] == "complete" and fit["margin"] >= MARGIN:
            epoch = int(np.floor(candidate["epoch"] + fit["offset_samples"] + 0.5)) % FRAME
            passing.append((-fit["margin"], rank, epoch))
    centers = []
    for _, _, epoch in sorted(passing):
        if all(min(abs(epoch - prior), FRAME - abs(epoch - prior)) > 2 for prior in centers):
            centers.append(epoch)
            if len(centers) == 2:
                break
    return tuple(centers)


class PartnerLocal:
    """One reusable native workspace, a fixed primary lane and copied physical rows."""

    def __init__(self, library, edge, *, local=True):
        from leo.analysis.starlink.native_short_window import (
            _ROW_COUNTS,
            _ROW_TIMINGS,
            NativeShortWindow,
            _candidate,
            _Result,
        )
        from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame

        self.lock = Lock()
        exact, control = (
            np.asarray(qin_edge_pilot_frame(RATE, edge, symbol_roll=roll), dtype="<c16")
            for roll in (0, CONTROL_SYMBOL_ROLL)
        )
        self.native = NativeShortWindow(
            str(library),
            exact,
            control,
            sample_rate_hz=RATE,
            receiver_count=1,
            fractional_epoch=True,
        )
        self.partner = None
        self.counts, self.timings, self.decode = _ROW_COUNTS, _ROW_TIMINGS, _candidate
        if local:
            try:
                self.partner = getattr(self.native._library, ENTRY)
                self.partner.argtypes = (
                    ct.c_void_p,
                    ct.c_void_p,
                    ct.c_size_t,
                    ct.POINTER(ct.c_int32),
                    ct.c_size_t,
                    ct.POINTER(_Result),
                )
                self.partner.restype = ct.c_int
                self.out = _Result()
            except BaseException:
                self.native.close()
                raise

    def _local_row(self, samples, centers, trace):
        seeds = (ct.c_int32 * len(centers))(*centers)
        self.native._check(
            self.partner(
                self.native._context,
                samples.ctypes.data,
                len(samples),
                seeds,
                len(centers),
                ct.byref(self.out),
            )
        )
        if self.out.row_count != 1:
            raise RuntimeError("unexpected local partner receiver count")
        row = self.out.rows[0]
        if row.candidate_count != len(centers):
            raise RuntimeError("unexpected local partner candidate count")
        decoded = {name: getattr(row, name) for name in self.counts}
        decoded["candidates"] = [self.decode(value) for value in row.candidates[: len(centers)]]
        if trace:
            decoded["timings_ms"] = {key: getattr(row, key + "_ms") for key in self.timings}
        return decoded

    def analyze(self, dual_ci16, primary=0, *, mode="local", trace=False):
        """Return the native short-window document in physical lane order.

        The optional trace returns boundary and per-lane clocks. Controls
        `full-on-hit` and `full` run ordinary acquisition on the partner.
        """
        if dual_ci16.dtype != np.dtype("<i2") or dual_ci16.shape != (200000, 2, 2):
            raise ValueError("expected two lanes of 20 ms CI16 at 10 MS/s")
        if not dual_ci16.flags.c_contiguous or primary not in (0, 1):
            raise ValueError("expected contiguous CI16 and a physical primary lane")
        if mode not in ("local", "full-on-hit", "full") or (
            mode == "local" and self.partner is None
        ):
            raise ValueError("unsupported partner mode")
        wall, cpu = perf_counter_ns(), thread_time_ns()
        with self.lock:
            first = np.ascontiguousarray(dual_ci16[:, primary : primary + 1, :])
            document = self.native.analyze(first, include_timings=trace)
            primary_row = document["rows"][0]
            primary_row["receiver_id"] = primary
            seeds = primary_centers(primary_row)
            mid_wall, mid_cpu = perf_counter_ns(), thread_time_ns()
            if seeds or mode == "full":
                other = np.ascontiguousarray(dual_ci16[:, 1 - primary : 2 - primary, :])
                partner = (
                    self._local_row(other, seeds, trace)
                    if mode == "local"
                    else self.native.analyze(other, include_timings=trace)["rows"][0]
                )
            else:
                partner = dict.fromkeys(self.counts, 0)
                partner["candidates"] = []
                if trace:
                    partner["timings_ms"] = dict.fromkeys(self.timings, 0.0)
            partner["receiver_id"] = 1 - primary
            rows = (primary_row, partner) if primary == 0 else (partner, primary_row)
            document.update(receiver_count=2, rows=list(rows))
            if mode == "local":
                document["algorithm_id"] = "wide-regional-partner-local-v1"
            end_wall, end_cpu = perf_counter_ns(), thread_time_ns()
            if not trace:
                return document
            document["detector_cpu_ms"] = sum(row["timings_ms"]["total_cpu"] for row in rows)
            return document, dict(
                seeds=seeds,
                primary_wall_ns=mid_wall - wall,
                primary_cpu_ns=mid_cpu - cpu,
                partner_wall_ns=end_wall - mid_wall,
                partner_cpu_ns=end_cpu - mid_cpu,
                wall_ns=end_wall - wall,
                cpu_ns=end_cpu - cpu,
            )

    def close(self):
        with self.lock:
            self.native.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
