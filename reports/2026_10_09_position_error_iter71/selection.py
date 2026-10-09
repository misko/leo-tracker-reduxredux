"""Score-only deterministic selection of qualified fits."""


def winner(rows, arm):
    eligible = [r for r in rows if r["arm"] == arm and r["fit"]["converged"]]
    return min(eligible, key=lambda r: (r["fit"]["objective"], r["order"])) if eligible else None
