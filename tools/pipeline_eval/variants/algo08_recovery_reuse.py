"""Reuse the last stable paired gate when salvage returns the same input."""

from contextlib import contextmanager
from functools import wraps
import pickle
from unittest.mock import patch

import numpy as np


def scope(operation, counts):
    stable = None

    @wraps(operation)
    def gate(scan, node, keep, stage, max_rounds=4, *, rounds=5, iterations=48,
             on_round=None, map_arms=None):
        nonlocal stable
        previous, stable = stable, None
        budget = max_rounds, rounds, iterations
        ordinary = on_round is None and map_arms is None
        if ordinary and stage == "salvage_refit" and previous is not None:
            old_scan, old_budget, node_bytes, mask, result = previous
            if (scan is old_scan and budget == old_budget
                    and keep.dtype == mask.dtype and np.array_equal(keep, mask)
                    and pickle.dumps(node, protocol=5) == node_bytes):
                problem, _, pair, history, _ = result
                counts["reused_pairs"] += 1
                # This invocation starts with the final stable mask. Its only
                # round has the same active points and no rejected components.
                return problem, keep, pair, [dict(history[-1], epoch=0)], True
        result = operation(scan, node, keep, stage, max_rounds, rounds=rounds,
                           iterations=iterations, on_round=on_round, map_arms=map_arms)
        counts["executed_gates"] += 1
        _, final_mask, _, history, converged = result
        if ordinary and stage == "exclude_refit" and converged and not final_mask.all() and history:
            stable = scan, budget, pickle.dumps(node, protocol=5), final_mask.copy(), result
        return result

    return gate


@contextmanager
def stable_recovery():
    from leo.analysis.localization_v3 import conservative_recovery as kernel

    recover = kernel.conservative_recovery
    counts = {"executed_gates": 0, "reused_pairs": 0}

    @wraps(recover)
    def wrapped(*args, **kwargs):
        with patch.object(kernel, "fit_and_gate", scope(kernel.fit_and_gate, counts)):
            return recover(*args, **kwargs)

    with patch.object(kernel, "conservative_recovery", wrapped):
        yield counts
