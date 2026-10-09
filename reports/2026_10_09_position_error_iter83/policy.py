"""Uniform research escalation decisions; no reference-position inputs."""

import math

ARMS = ("fitted-c", "zero-c")


def needs_extra_search(fits, threshold=10.0):
    """Missing or nonstationary initial joint fits also request shared extra work."""
    for arm in ARMS:
        fit = fits.get(arm)
        if fit is None or not fit["converged"]:
            return True
        relative = fit["vector"][8:]
        if not relative or not all(math.isfinite(v) for v in relative):
            return True
        energy = sum(v * v for v in relative) / len(relative) / 4
        if energy > threshold:
            return True
    return False


def key(row):
    return row["fit"]["objective"], row["index"], row["order"]


def winner(rows, arm):
    eligible = [r for r in rows if r["arm"] == arm and r["fit"]["converged"]
                and math.isfinite(r["fit"]["objective"])]
    return min(eligible, key=key) if eligible else None


def retry_inventory(rows):
    """At most two states per arm, shared into both arms; retain original eligibility."""
    selected = []
    for arm in ARMS:
        best = winner(rows, arm)
        if best is not None:
            selected.append(best)
        failed = [r for r in rows if r["arm"] == arm and not r["fit"]["converged"]
                  and math.isfinite(r["fit"]["objective"])
                  and (best is None or r["fit"]["objective"] < best["fit"]["objective"])]
        if failed:
            selected.append(min(failed, key=key))
    return selected


def endpoint_sources(rows):
    """Preserve every region and both source types; stable first feasible arm only."""
    selected = {}
    for index, row in enumerate(rows):
        if row["start"] not in ("association", "zero-timing") or row["status"] != "feasible":
            continue
        identity = row["region"], row["start"]
        selected.setdefault(identity, index)
    return list(selected.values())
