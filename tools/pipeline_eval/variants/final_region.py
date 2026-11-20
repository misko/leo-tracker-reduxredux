"""Publish the selected compact result through the paired 20 m tile guard."""

from ..scoring import ARMS, validate_result
from .compact_tile_interior import guard


def publish(result, tile, *, enabled=False):
    """Keep a completed pair diagnostic-only when either fit meets a tile face."""
    if not enabled:
        return result
    validate_result(result)
    if result["status"] == "ok":
        arms = result.get("arms", {})
        if set(arms) != set(ARMS) or any(arms[arm]["latlon"] is None for arm in ARMS):
            raise ValueError("the guarded compact receiver needs both selected positions")
    return guard(result, tile)


def select(early, full, *, released, enabled=False):
    """Apply the same terminal publication policy after either release branch."""
    selected = early if released else full
    result = publish(selected["result"], selected["tile"], enabled=enabled)
    return selected if result is selected["result"] else dict(selected, result=result)
