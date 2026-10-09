"""Retry inventory selected solely by score and qualification."""


def select(rows):
    selected = []
    for arm in ("fitted-c", "zero-c"):
        candidates = [r for r in rows if r["arm"] == arm]
        qualified = [r for r in candidates if r["fit"]["converged"]]
        def key(r):
            return r["fit"]["objective"], r["index"], r["order"]
        best = min(qualified, key=key)
        selected.append(best)
        failed = [
            r
            for r in candidates
            if not r["fit"]["converged"] and r["fit"]["objective"] < best["fit"]["objective"]
        ]
        if failed:
            selected.append(min(failed, key=key))
    return selected
