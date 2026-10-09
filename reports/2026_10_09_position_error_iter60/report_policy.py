"""Require complete model/arm coverage before a paired comparison."""

MODELS = ("hard", "smooth")
ARMS = ("fitted-c", "zero-c")


def paired_indices(indices, receipts):
    return [i for i in indices if all((m, i, a) in receipts for m in MODELS for a in ARMS)]


def winner(rows):
    eligible = [r for r in rows if r.get("fit", {}).get("converged")]
    return min(eligible, key=lambda r: (r["fit"]["objective"], r["index"])) if eligible else None


def compare_pairs(hard, smooth):
    counts = dict(
        improved=0, regressed=0, tied=0, gained_convergence=0, lost_convergence=0, both_failed=0
    )
    for before, after in zip(hard, smooth, strict=True):
        assert before["index"] == after["index"]
        a, b = before["fit"]["converged"], after["fit"]["converged"]
        if a and b:
            delta = after["error_km"] - before["error_km"]
            key = "improved" if delta < -0.001 else "regressed" if delta > 0.001 else "tied"
        else:
            key = "gained_convergence" if b else "lost_convergence" if a else "both_failed"
        counts[key] += 1
    return counts
