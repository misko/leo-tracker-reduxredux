"""Clean selected-region projection and legacy-equivalent numerical construction."""

import numpy as np


def regional_document(document):
    """Whitelist only fields consumed by the ordinary87 reconstruction."""
    arms = []
    for arm in document["methods"][0]["arms"]:
        selected = arm["selected"]
        arms.append(
            {
                "name": arm["name"],
                "selected": {k: selected[k] for k in ("source_basin", "satellites")},
            }
        )
    calibrations = {}
    for arm in arms:
        key = arm["selected"]["source_basin"]
        value = document["diagnostics"]["calibrations"][key]
        calibrations[key] = {
            "receiver_baseline_hz": value["receiver_baseline_hz"],
            "correction": {k: value["correction"][k] for k in ("nodes_s", "knots_hz")},
        }
    return {
        **{
            k: document[k]
            for k in ("session_id", "input_manifest_sha256", "analysis_manifest_sha256")
        },
        "methods": [{"arms": arms}],
        "diagnostics": {"calibrations": calibrations},
    }


def reconstruct(case, document, archive, components):
    """Components are audited numerical constructors, never a legacy loader."""
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
    correction = calibration["correction"]
    lookup = {int(number): i for i, number in enumerate(case["bank"].numbers)}
    base = components["Hard60Objective"](
        case["observations"],
        case["bank"].select([lookup[n] for n in selected["satellites"]]),
        case["prior"],
        components["HARD60_SCORE"],
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    joint = archive["raw"]["B3"]["fitted-c"]
    assert joint["converged"]
    subset, _, removed = components["reduce_bank"](base, np.asarray(joint["vector"]), 5)
    assert removed == archive["reasons"]["removed_satellites"]
    chosen = archive["raw"]["B4"]["fitted-c"]
    assert chosen["converged"]
    wide = archive["raw"]["B4W"]["fitted-c"]
    if wide["converged"]:
        chosen = wide
    seed = np.asarray(chosen["vector"])
    clock = np.r_[chosen["clock_coefficients"], 0.0, 0.0]
    dynamic = archive["raw"]["B5"]["fitted-c"]
    if dynamic["converged"]:
        seed = np.asarray(dynamic["vector"])
        clock = np.asarray(dynamic["clock_coefficients"])
    nodes, knots = correction["nodes_s"], correction["knots_hz"]
    control = components["DynamicRFObjective"](subset, nodes, knots, 50)
    terms = control.evaluate_joint(seed, clock)[3]
    mass = terms.responsibilities.sum(axis=0)
    centers = np.divide(
        terms.responsibilities.T @ subset.observations.times_s,
        mass,
        out=np.full(len(mass), subset.observations.time_center_s),
        where=mass > 1e-12,
    )
    return components["SlopePrior"](subset, nodes, knots, centers, 0.5)
