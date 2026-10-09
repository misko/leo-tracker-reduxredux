"""Require complete model/arm coverage before a paired comparison."""

MODELS = ("hard", "smooth")
ARMS = ("fitted-c", "zero-c")


def paired_indices(indices, receipts):
    return [i for i in indices if all((m, i, a) in receipts for m in MODELS for a in ARMS)]


def winner(rows):
    eligible = [r for r in rows if r.get("fit", {}).get("converged")]
    return min(eligible, key=lambda r: (r["fit"]["objective"], r["index"])) if eligible else None
