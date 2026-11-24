"""Expose exact retained curve rows at the two unchanged charted screens."""

from contextlib import contextmanager
from hashlib import sha256
from math import isfinite
from pathlib import Path
import sys
from unittest.mock import patch


FINISH_PIN = "7d8d5a65ceb0e11150e28d0dbbddeabb7741ef1408ded6272500e4f0e012c708"
RETAINED_PIN = "9d5047f873a22790c4f0818877b09270ee91a0761a9a3d7204c8a849639ee656"


class ReachedSecondGate(RuntimeError):
    """Diagnostic-only stop after observing the original post-salvage gate."""

def finite(value):
    return float(value) if isfinite(value) else None


def read_gates(gates):
    result = []
    for row in gates["tracks"]:
        ids = tuple(row["observation_ids"])
        if len(ids)!=row["points"]:
            raise ValueError("Curve gate no longer binds its actual active observations")
        conditional = row["conditional_residual_gate"]
        result.append(dict(component=row["component"],norad=int(row["norad"]),candidate_index=int(row["candidate_index"]),
                           points=int(row["points"]),compatible=bool(row["compatible"]),observation_ids=ids,
                           aliases_changed=int(row["aliases_changed"]),profile_rms_hz=finite(row["profile_rms_hz"]),
                           profile_bias_hz=finite(row["profile_bias_hz"]), conditional=dict(
                               compatible=bool(conditional["compatible"]),rms_hz=finite(conditional["rms_hz"]),
                               mean_hz=finite(conditional["mean_hz"]),diagnostics={
                                   k:bool(v) if k=="noise_screen_pass" else finite(v)
                                   for k,v in conditional["diagnostics"].items()})))
    if (len({r["component"] for r in result})!=len(result)
            or len({oid for r in result for oid in r["observation_ids"]})!=sum(r["points"] for r in result)
            or sum(r["points"] for r in result if r["compatible"])!=gates["accepted_points"]):
        raise ValueError("Curve gate summary differs from its active row membership")
    return result


def observe(propose, operation, emit, *, stop_after_second=False):
    screens = iter(("first", "after_salvage"))

    def drop(keep, rows, slices, gates):
        result = operation(keep,rows,slices,gates)
        # Ignore secondary use through provisional rescue, where this same
        # helper is called from another lexical frame.
        if sys._getframe(1).f_code is propose.__code__:
            emitted = read_gates(gates)
            if sorted(row["component"] for row in emitted if not row["compatible"]) != result[1]:
                raise ValueError("The measured mask disagrees with its original gate dispositions")
            stage = next(screens)
            emit(dict(screen=stage,tracks=emitted))
            if stop_after_second and stage=="after_salvage":
                raise ReachedSecondGate("Observed original second curved support screen")
        return result
    return drop


@contextmanager
def binding(finish, emit, *, stop_after_second=False):
    """Enter before the frozen charted stack wraps its proposal function."""
    from leo.analysis.localization_v3 import conservative_recovery

    finish_file = Path(finish.__file__).resolve()
    retained_file = Path(conservative_recovery.__file__).resolve()
    for file,pin,operation in ((finish_file,FINISH_PIN,finish.propose),
                               (retained_file,RETAINED_PIN,conservative_recovery.retained_metrics)):
        if (sha256(file.read_bytes()).hexdigest()!=pin or Path(operation.__code__.co_filename).resolve()!=file):
            raise ValueError("Expected the ordinary pinned proposal and retained gate")
    observer = observe(finish.propose,finish.drop_failing,emit,stop_after_second=stop_after_second)
    with patch.object(finish,"drop_failing",observer):
        yield
