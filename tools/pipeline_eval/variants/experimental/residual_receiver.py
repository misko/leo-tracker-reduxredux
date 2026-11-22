"""Use the reviewed full and primary-only entry points on live admitted lanes."""

import ctypes as ct
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import process_time_ns

from . import residual_schedule

DETECTOR_SHA256 = "1b4c43dc1f2edc64ead9c4b9c0f4d724f79f623e04a13f40812a1d4bb40345a5"
SCHEDULE_SHA256 = "1261e213195c906854ea13b5562e838990a78a04768906e6d0319e772e345eda"


def require_native_pin(digest):
    if digest != DETECTOR_SHA256:
        raise ValueError("Conditional residual requires the reviewed exact fractional native build")


def verify_schedule(path):
    if sha256(path.read_bytes()).hexdigest() != SCHEDULE_SHA256:
        raise ValueError("The frozen residual schedule changed")


class ResidualReceiver:
    def __init__(self):
        self._active = False
        self.policy = None
        self.query_cpu_ns = 0

    @contextmanager
    def detector(self, method, edge, *, binary=None, pilot=None):
        import numpy as np

        from ...qualification.full_v5_check import _probe, factor_candidate
        from ...qualification.single_scan_position import Factor
        from ...qualification.single_scan_trial import Native

        if self._active or method != "cancellation" or binary is None or pilot is None:
            raise ValueError("Conditional residual requires one pinned cancellation context")
        verify_schedule(Path(residual_schedule.__file__))
        require_native_pin(sha256(Path(binary).read_bytes()).hexdigest())
        asset = np.fromfile(pilot, dtype="<f4")
        if asset.shape != (133413,):
            raise ValueError("Invalid receiver pilot asset")
        native = Native(binary, asset)
        try:
            entries = {
                True: native.lib.cancellation_factors,
                False: native.lib.cancellation_primary_factors,
            }
            for entry in entries.values():
                entry.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double,
                                  ct.POINTER(Factor)]
                entry.restype = ct.c_int
            policy = self.policy = residual_schedule.Replay("conditional")
            self._active = True
            self.query_cpu_ns = 0

            def receive(window):
                if not self._active or self.policy is not policy:
                    raise RuntimeError("Conditional residual receiver scope has closed")
                samples = window.samples
                lanes = tuple(window.receiver_ids)
                if (lanes != (0, 1) or window.sample_rate_hz != 10_000_000
                        or samples.shape != (200_000, 2, 2) or samples.dtype != np.dtype("<i2")
                        or not samples.flags.c_contiguous or window.target["edge"] != edge):
                    raise ValueError("Expected two ordered CI16 antennas at the active pilot edge")
                target, acquisition = window.target, window.acquisition
                center = (target["rf_center_hz"] - target["lnb_lo_hz"]
                          - acquisition["actual_if_center_hz"])
                lo, hi = center - 800000, center + 800000
                if not (-5e6 <= lo < hi <= 5e6 and hi - lo <= 1600000):
                    raise ValueError("Native exported factors disagree with the receiver")
                rows = []
                for lane in lanes:
                    row = _probe(window, lane, [])

                    def measure(residual_enabled, lane=lane):
                        vector = (Factor * 2)()
                        started = process_time_ns()
                        count = entries[residual_enabled](
                            native.ctx, samples.ctypes.data, lane, lo, hi, vector,
                        )
                        self.query_cpu_ns += process_time_ns() - started
                        if not 0 <= count <= 2:
                            raise ValueError("Native exported factors disagree with the receiver")
                        candidates = [
                            factor_candidate(
                                f.rank, f.integer, status="complete", offset=f.offset, cfo=f.hz,
                                exact=f.exact, control=f.control, margin=f.exact - f.control,
                            )
                            for f in vector[:count]
                        ]
                        if any(not f["passed_fractional_margin_gate"] for f in candidates):
                            raise ValueError("Receiver admitted an unverified candidate")
                        return candidates

                    _, _, selected = policy.visit(row, measure)
                    rows.append(dict(row, candidates=selected))
                return rows

            yield receive
        finally:
            self._active = False
            native.close()

    def receipt(self):
        reasons = self.policy.reasons
        return dict(
            factor_calls=sum(reasons.values()),
            residual_requests=reasons["sentinel"] + reasons["activity"],
            primary_only_requests=reasons["skip"],
            schedule_reasons=dict(reasons),
            query_cpu_ns=self.query_cpu_ns,
        )
