"""Project owned accepted policy decisions into the existing recorded path."""

import numpy as np

from leo.contracts.fast_graph_position import MODEL_VERSION as BASE
from leo.contracts.fast_graph_position_v2 import MODEL_VERSION as PREDICTIVE
from leo.contracts.fast_graph_position_v3 import MODEL_VERSION as NUMERICAL
from leo.contracts.fast_graph_position_v4 import MODEL_VERSION as GAP
from leo.contracts.fast_graph_position_v5 import MODEL_VERSION as ADDITIONAL
from leo.contracts.fast_graph_position_v6 import MODEL_VERSION as REASSOCIATION
from leo.presentation.position_path import recorded_fit_path


def _values(value):
    """Match public JSON numeric representation, without rounding."""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {k: _values(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_values(v) for v in value]
    return value


def recorded_decision_path(
    cavity,
    region,
    *,
    predictive=None,
    numerical=None,
    gap=None,
    additional=None,
    reassociation=None,
):
    """Include adopted fits only, preserving each published policy's detail.

    Policy labels describe the unchanged scientific behavior. No earlier worker,
    terminal, result path or evaluation coordinate is consumed.
    """
    if cavity["status"] != "complete":
        raise ValueError("Complete baseline policy required for a recorded path")
    accepted = []

    def add(model, rows):
        # The predictor/numerical and gap decisions already contain the original
        # compact published rows. Do not substitute richer private checkpoints.
        accepted.append(
            dict(
                model_version=model,
                arms={
                    arm: _values(
                        {
                            k: v
                            for k, v in rows[arm].items()
                            if k in ("history", "endpoint_east_north_km", "endpoint_latlon", "x")
                        }
                    )
                    for arm in ("c0", "fitted_c")
                },
            )
        )

    add(BASE, cavity["policy_arms"])
    if predictive and predictive.get("selected"):
        if predictive["decision"] not in ("ALGO03_single", "ALGO03_joint"):
            raise ValueError("Selected predictive fit has no adoption decision")
        add(PREDICTIVE, predictive["selected"]["arms"])
    if numerical and numerical["decision"] == "ALGO04_additive":
        add(NUMERICAL, numerical["candidate"]["selected"]["arms"])
    if gap and gap.get("candidate"):
        add(GAP, gap["candidate"]["trial"]["arms"])
    if additional:
        decision = additional["decisions"]["72h_30s"]
        if decision["status"] == "qualified":
            add(ADDITIONAL, additional["trials"][decision["trial"]]["arms"])
    if reassociation and reassociation.get("selected"):
        if reassociation["execution_status"] != "complete":
            raise ValueError("Incomplete reassociation cannot supply a path")
        rows = [r for r in reassociation["records"] if r["name"] == reassociation["selected"]]
        if len(rows) != 1 or not rows[0]["accepted"]:
            raise ValueError("Selected reassociation has no unique accepted fit")
        add(REASSOCIATION, rows[0]["pair"])
    return recorded_fit_path(
        accepted,
        accepted[-1]["model_version"],
        region_center=region.center,
        box_width_km=region.width_km,
    )
