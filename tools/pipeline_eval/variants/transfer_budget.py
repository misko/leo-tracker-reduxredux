"""Admission and a local deadline for compact conservative recovery."""

RECOVERY_LIMIT_S = 55


def admits_recovery(evidence):
    """Require a strict majority of the nominated observations to support the seed."""
    return 2 * evidence["accepted_points"] > evidence["tracked_points"] > 0
