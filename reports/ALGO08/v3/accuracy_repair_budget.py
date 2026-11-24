"""Price simultaneous timing and per-recording accuracy improvements on measured pairs."""

from math import fsum
from statistics import median


def acceptable_pair(installed, candidate, tolerance_km):
    """Preserve both released fixes and bound excess error wherever the reference is known."""
    for arm in ("c0", "fitted_c"):
        if installed[arm + "_fix"] and not candidate[arm + "_fix"]:
            return False
        before, after = (row[arm + "_error_km"] for row in (installed, candidate))
        if before is not None and (after is None or after > before + tolerance_km):
            return False
    return True


def repair_budget(pairs, tolerance_km, candidate_time_fraction):
    """Bound the least number of additional recordings that would need acceptable outputs.

    An oracle picks a build before execution. Every repair keeps the modelled
    candidate clock. Two separate greedy optima bound the joint optimum below.
    A route reaching both timing gates supplies an upper bound.
    """
    if not pairs or tolerance_km < 0 or not 0 <= candidate_time_fraction <= 1:
        raise ValueError("Expected measured pairs, nonnegative tolerance and time fraction in [0,1]")
    base = [a["elapsed_s"] for a, _ in pairs]
    fast = [min(t, candidate_time_fraction * b["elapsed_s"]) for t, (_, b) in zip(base, pairs, strict=True)]
    allowed = [acceptable_pair(a, b, tolerance_km) for a, b in pairs]
    unresolved = [i for i, ok in enumerate(allowed) if not ok]
    choices = [i for i in unresolved if fast[i] < base[i]]
    installed_total = fsum(base)
    original = [fast[i] if ok else base[i] for i, ok in enumerate(allowed)]

    def evaluate(order):
        trial = original.copy()
        first_sum = first_median = None
        for count in range(len(order) + 1):
            if count:
                i = order[count - 1]
                trial[i] = fast[i]
            if first_sum is None and fsum(trial) <= installed_total / 2:
                first_sum = count
            if first_median is None and median(t / b for t, b in zip(trial, base, strict=True)) <= .5:
                first_median = count
            if first_sum is not None and first_median is not None:
                return first_sum, first_median, count
        return first_sum, first_median, None

    # Every unresolved recording initially has ratio one. Replacing the largest
    # absolute savings optimizes the sum at each count. Replacing the smallest
    # ratios minimizes every order statistic, including an even-panel median.
    sum_order = sorted(choices, key=lambda i: fast[i] - base[i])
    median_order = sorted(choices, key=lambda i: fast[i] / base[i])
    sum_min, _, sum_witness = evaluate(sum_order)
    _, median_min, median_witness = evaluate(median_order)
    lower = upper = None
    if sum_min is not None and median_min is not None:
        lower = max(sum_min, median_min)
        upper = min(sum_witness, median_witness)
    return dict(pairs=len(pairs), tolerance_km=tolerance_km, candidate_time_fraction=candidate_time_fraction,
                outside_tolerance=len(unresolved), required_installed_s=fsum(base[i] for i in unresolved),
                installed_total_s=installed_total, wall_without_repairs_s=fsum(original),
                min_repairs_for_sum=sum_min, min_repairs_for_median=median_min,
                joint_lower_bound=lower, joint_upper_bound=upper)
