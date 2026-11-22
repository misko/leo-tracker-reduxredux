"""Publish the deployed fractional scores of the causally retained carrier."""

import ctypes as ct
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from ...qualification.full_v5_check import _probe, factor_candidate
from ...qualification.single_scan_position import Factor
from ...qualification.single_scan_trial import Native
from ..carrier_continuation import Continuation


LIBRARY_SHA256 = "a5862937b78f13d9788386d134cdbe427393dab678c858f27d4efeacdbf0efcb"
ABI_FIELDS = ("rank", "integer", "offset", "hz", "exact", "control")


def _candidate(factor):
    return factor_candidate(
        factor.rank, factor.integer, status="complete", offset=factor.offset,
        cfo=factor.hz, exact=factor.exact, control=factor.control,
        margin=factor.exact - factor.control,
    )


def _bind(library):
    layout = tuple(getattr(Factor, field).offset for field in ABI_FIELDS)
    if ct.sizeof(Factor) != 40 or layout != (0, 4, 8, 16, 24, 32):
        raise ValueError("Unexpected native factor ABI")
    measure = getattr(library, "cancellation_factors", None)
    repair = getattr(library, "experimental_repair_fractional_selection", None)
    if measure is None or repair is None:
        raise ValueError("Selected score verification requires the reviewed receiver ABI")
    measure.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.POINTER(Factor)]
    measure.restype = ct.c_int
    repair.argtypes = [ct.c_void_p, ct.POINTER(Factor)]
    repair.restype = ct.c_int
    return measure, repair


def _repaired_candidate(repair, context, factor, counts, group):
    status = repair(context, ct.byref(factor))
    if status not in (0, 1):
        raise ValueError("Could not recover the retained fractional scores")
    if counts is not None:
        counts[group] += status
        counts["already_exact"] += 1 - status
    exact = _candidate(factor)
    if not exact["passed_fractional_margin_gate"]:
        raise ValueError("Retained factor changed its margin-gate eligibility")
    return exact


@contextmanager
def detector(method, edge, *, binary=None, pilot=None, verified_library, counts=None):
    if (method != "cancellation" or binary is None or pilot is None
            or Path(binary).resolve(strict=True) != verified_library):
        raise ValueError("Selected score verification requires its checked cancellation library")
    asset = np.fromfile(pilot, dtype="<f4")
    if asset.shape != (133_413,):
        raise ValueError(f"Unexpected {edge} pilot asset geometry")
    receiver = Native(verified_library, asset)
    active = True
    try:
        measure, repair = _bind(receiver.lib)
        continuation = Continuation()

        def factors(window):
            if not active:
                raise RuntimeError("Selected score receiver context is closed")
            target, acquisition = window.target, window.acquisition
            mid = target["rf_center_hz"] - target["lnb_lo_hz"] - acquisition["actual_if_center_hz"]
            rows = []
            for lane in window.receiver_ids:
                vector = (Factor * 2)()
                count = measure(receiver.ctx, window.samples.ctypes.data, lane, mid - 800_000.,
                                mid + 800_000., vector)
                if not 0 <= count <= 2:
                    raise ValueError("Native exported factors disagree with the receiver")
                candidates = [_candidate(factor) for factor in vector[:count]]
                if any(not candidate["passed_fractional_margin_gate"] for candidate in candidates):
                    raise ValueError("Receiver admitted an unverified candidate")
                if count == 2:
                    # Continuation compares margins before it applies its vote rule.
                    if counts is not None:
                        counts["two_factor_lanes"] += 1
                    candidates = [
                        _repaired_candidate(repair, receiver.ctx, factor, counts, "two_factor_repairs")
                        for factor in vector
                    ]
                    candidates.sort(key=lambda candidate: (-candidate["fractional_margin"],
                                                            candidate["candidate_rank"]))
                row = _probe(window, lane, candidates)
                _, keep, _ = continuation.select(row)
                retained = []
                if keep is not None:
                    # The verifier workspace still holds this lane's original I/Q.
                    retained.append(candidates[keep] if count == 2 else _repaired_candidate(
                        repair, receiver.ctx, vector[keep], counts, "retained_single_repairs",
                    ))
                rows.append(dict(row, candidates=retained))
            return rows

        yield factors
    finally:
        active = False
        receiver.close()
