"""Research-only centre restart of a legal ordinary matched-support repair."""

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np


ARMS = ("c0", "fitted_c")
SOURCES = (
    "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708",  # arm_finish
    "3ec955b211a1c4b48fe18c66d9374a78fd393d3b068ffed1c7a9fe42d035629b",  # signed update
    "429c230cb01438a4889f6e77256b7f00df4435b3522632bbef8cc2a83d223ca1",  # original paired gates
)


def eligible(measured):
    repair = measured.get("repair", {})
    signed = measured.get("signed", {})
    return (repair.get("status") == "complete" and repair.get("attempted_refits") == 1
            and signed.get("status") == "unqualified" and signed.get("selection", {}).get("qualified") is False)


def ordered_owners(record):
    return tuple((role, line["component"], line["norad"], tuple(line["observation_ids"]))
                 for role, rows in (("conditional", record["gates"]["tracks"]),
                                    ("predictive", record["linear_gates"]))
                 for line in rows)


def reset_pair(ordinary, audit, arm_finish, pair_passes, readout):
    scan, node, keep, powers, means, model, entries = (ordinary[key] for key in (
        "scan", "node", "keep", "powers", "means", "model", "entries"))
    previous = ordinary["arms"]
    fitted, arm_clocks = {}, {}
    audit["arm_clocks"] = arm_clocks
    for arm in ARMS:
        started = perf_counter(), process_time()
        try:
            reference = np.zeros_like(previous[arm]["phase_reference"], dtype=float)
            fitted[arm] = arm_finish(scan, node, keep, arm, reference, powers, means, model, entries, np.zeros(2))
        finally:
            arm_clocks[arm] = dict(elapsed_s=perf_counter()-started[0], cpu_s=process_time()-started[1])
    audit["finish"] = {arm: readout(fitted[arm]) for arm in ARMS}
    same = {arm: ordered_owners(previous[arm]) == ordered_owners(fitted[arm]) for arm in ARMS}
    audit["same_ordered_owners"] = same
    if (all(same.values()) and
            pair_passes(fitted, include_linear=bool(entries), half_width_km=scan.search_region.half_width_km)):
        audit["status"] = "accepted"
        return dict(ordinary, arms=fitted)
    audit["status"] = "original_pair_retained"
    return ordinary


def with_reset(update, arm_finish, pair_passes, readout, *, enabled=False):
    if not enabled:
        return update
    paid = False

    def run(prepared, ordinary, measured, *, fit_pair=None):
        nonlocal paid
        baseline = update(prepared, ordinary, measured, fit_pair=fit_pair)
        if baseline is not ordinary or paid or not eligible(measured):
            measured["ordinary_centre_reset"] = {"status": "already_paid" if paid else "ineligible"}
            return baseline
        paid = True
        audit = measured["ordinary_centre_reset"] = {"status": "started"}
        started = perf_counter(), process_time()
        try:
            return reset_pair(ordinary, audit, arm_finish, pair_passes, readout)
        except (ArithmeticError, AssertionError, KeyError, TypeError, ValueError, np.linalg.LinAlgError) as exc:
            audit.update(status="original_pair_retained", reason=f"{type(exc).__name__}: {exc}")
            return ordinary
        finally:
            audit["elapsed_s"] = perf_counter()-started[0]
            audit["cpu_s"] = process_time()-started[1]

    return run


@contextmanager
def binding(*, enabled=False):
    if not enabled:
        yield
        return
    import blind_joint_finish as finish
    import blind_joint_signed as signed
    from leo.analysis.localization_v3 import history_policy

    for module, pin in zip((finish, signed, history_policy), SOURCES, strict=True):
        if sha256(Path(module.__file__).read_bytes()).hexdigest() != pin:
            raise ValueError("The frozen charted repair kernels or gates changed")
    updated = with_reset(signed.update, finish.arm_finish, history_policy.pair_passes, finish.readout, enabled=True)
    with patch.object(signed, "update", updated):
        yield
