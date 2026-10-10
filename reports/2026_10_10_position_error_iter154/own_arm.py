"""Conditional retained-state repair; pure ports, no production imports or I/O."""

import copy
import math


def evidence(value):
    """Keep invalid numerical evidence JSON-safe, never usable as a candidate."""
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {key: evidence(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [evidence(item) for item in value]
    return copy.deepcopy(value)


def validate_fit(fit, point, arm, size=None):
    if arm not in ("fitted-c", "zero-c"):
        raise ValueError("unknown discovery arm")
    if len(point) != 2 or not all(math.isfinite(x) for x in point):
        raise ValueError("invalid retained point")
    vector = fit["vector"]
    if len(vector) < 8 or (size is not None and len(vector) != size):
        raise ValueError("coarse vector dimension changed")
    if not all(math.isfinite(x) for x in vector) or not math.isfinite(fit["objective"]):
        raise ValueError("nonfinite fit")
    if list(vector[:2]) != list(point):
        raise ValueError("retained position changed")
    if fit.get("rf_arm", arm) != arm:
        raise ValueError("fit arm changed")
    if arm == "zero-c" and vector[6] != 0:
        raise ValueError("zero-c lock changed")
    if abs(vector[3]) > 60 or abs(vector[5]) > 60:
        raise ValueError("receiver slope outside hard60")


def qualified(check, fit, arm):
    """Require an independently repriced, finite full own-arm KKT receipt."""
    if check["rf_arm"] != arm:
        raise ValueError("audit arm changed")
    if not math.isfinite(check["objective"]) or not math.isfinite(check["stationarity"]):
        raise ValueError("nonfinite independent audit")
    if check["stationarity"] < 0 or abs(check["objective"] - fit["objective"]) > 1e-6:
        raise ValueError("invalid independent audit")
    return bool(check["feasible"] and check["qualified"] and check["stationarity"] <= 0.001)


def repair_then_transition(model, original, point, arm, *, audit, bounded, transition):
    """Call an explicitly supplied150 transition only after own-arm admission.

    Ports consume/return plain JSON-compatible fit dictionaries. The eventual
    bounded adapter must serialize real PositionFit/diagnostics before return.
    """
    original, point = copy.deepcopy(original), list(point)
    receipt = dict(original=evidence(original), discovery_arm=arm, own_audit=None,
                   repair=None, admitted=None, handoff=None, status="invalid-original")
    try:
        validate_fit(original, point, arm)
        check = audit(model, copy.deepcopy(original), arm)
        receipt["own_audit"] = evidence(check)
        own_ok = qualified(check, original, arm)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        return dict(receipt, error=repr(error))
    candidate = copy.deepcopy(original)
    if not own_ok:
        receipt["repair"] = dict(fit=None, solver=None, audit=None)
        try:
            candidate, solver = bounded(
                model, copy.deepcopy(original["vector"]), rf_arm=arm,
                fixed_position=True, slope_half_width_hz_s=60,
                maximum_seconds=5, maximum_iterations=200,
            )
            receipt["repair"].update(fit=evidence(candidate), solver=evidence(solver))
            if candidate is None:
                raise ValueError("bounded repair returned no state")
            validate_fit(candidate, point, arm, len(original["vector"]))
            check = audit(model, copy.deepcopy(candidate), arm)
            receipt["repair"]["audit"] = evidence(check)
            if not qualified(check, candidate, arm):
                return dict(receipt, status="own-arm-unqualified")
            if check["objective"] > receipt["own_audit"]["objective"] + 1e-6:
                return dict(receipt, status="own-arm-objective-increased")
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, TimeoutError) as error:
            return dict(receipt, status="own-arm-repair-failed", error=repr(error))
    candidate = copy.deepcopy(candidate)
    candidate["converged"] = True
    receipt["admitted"] = candidate
    try:
        receipt["handoff"] = transition(model, copy.deepcopy(candidate), point.copy(), arm)
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, TimeoutError) as error:
        return dict(receipt, status="downstream-transition-failed", error=repr(error))
    # This status certifies admission only, not downstream success/localization.
    return dict(receipt, status="own-arm-admitted")
