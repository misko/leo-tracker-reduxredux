"""Extend the same causal orbit bank at the first eligible corner lookup."""

from contextlib import contextmanager
from functools import wraps
from unittest.mock import patch


@contextmanager
def bind(position, scanner, support, audit):
    """Keep the installed solve and its fallback policy, including genuine errors."""
    original = position.solve
    if scanner.solve is not original:
        raise ValueError("The installed solver aliases must refer to the same original solve")

    @wraps(original)
    def solve(*args, **kwargs):
        with support() as entry:
            audit.append(entry)
            result, packet, policy = original(*args, **kwargs)
        if policy == "stock" and entry["corner_projections_extended"]:
            policy = "orbit_support"
        return result, packet, policy

    with patch.object(position, "solve", solve), patch.object(scanner, "solve", solve):
        yield
