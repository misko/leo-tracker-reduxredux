"""Preserve old winners while adding wider-spaced regional finalists."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026_10_08_position_error_iter06"))
from additive_policy import select  # noqa: E402


def select_documents(documents):
    if tuple(documents) != ("baseline", "sep25", "sep50"):
        raise ValueError("Require explicit baseline, sep25, sep50 priority order")
    chosen, sources = {}, {}
    for arm in ("fitted-c", "zero-c"):
        winner = None
        source = "baseline"
        for name, document in documents.items():
            candidate = next(
                a["selected"] for a in document["methods"][0]["arms"] if a["name"] == arm
            )
            if name == "baseline":
                winner = candidate
            else:
                winner, changed = select(winner, candidate)
                if changed == "additional":
                    source = name
        chosen[arm], sources[arm] = winner, source
    return chosen, sources
