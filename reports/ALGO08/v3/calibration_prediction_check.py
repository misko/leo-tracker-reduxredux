"""Read the paired predictive-frequency cost from standard publication evidence."""

from math import isfinite


def predictive_mse(conditional_rms, all_owned_rms, conditional, predictive):
    if (conditional <= 0 or predictive <= 0 or
            any(not isfinite(x) or x < 0 for x in (conditional_rms, all_owned_rms))):
        raise ValueError("Need finite, nonempty conditional and predictive partitions")
    total = (conditional + predictive) * all_owned_rms**2
    remaining = total - conditional * conditional_rms**2
    if remaining < -1e-12 * total:
        raise ValueError("The reported conditional and all-owner RMS are incompatible")
    return max(0., remaining) / predictive


def assess(arms, owners_matched):
    """Flag twofold predictive power inflation when the fitted arm improved in-sample."""
    fixed, fitted = (arms[key] for key in ("c0", "fitted_c"))
    roster = tuple((arm["conditional_count"], arm["predictive_count"]) for arm in (fixed, fitted))
    if not owners_matched or roster[0] != roster[1] or min(roster[0]) <= 0:
        return {"status": "unavailable", "reason": "unmatched_or_empty_partition"}
    if any(arm["all_owned_rms_hz"] is None for arm in (fixed, fitted)):
        return {"status": "unavailable", "reason": "missing_all_owned_residual"}
    a, b = (predictive_mse(arm["conditional_rms_hz"], arm["all_owned_rms_hz"], *roster[0])
            for arm in (fixed, fitted))
    improves = fitted["conditional_rms_hz"] < fixed["conditional_rms_hz"]
    suspect = improves and b > 2*a
    return dict(status="suspect" if suspect else "pass", conditional_improves=improves,
                predictive_mse={"c0": a, "fitted_c": b}, fitted_over_c0=b/a if a else None)
