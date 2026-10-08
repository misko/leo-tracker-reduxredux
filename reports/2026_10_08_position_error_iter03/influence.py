"""Satellite-assigned observation deletion, with nuisance terms refitted.

Assignments are diagnostic groups frozen at the deployed fitted-c estimate.
No satellite is removed from the candidate bank and no reference location is
used to select groups. This is sensitivity analysis, not an inference policy.
"""

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026_10_08_position_error_iter01"))
sys.path.insert(0, str(HERE.parent / "2026_10_08_hard60_bounded_recovery"))
from inputs import json_value, write_json  # noqa: E402
from probe import error_km, load  # noqa: E402

from leo.analysis.hard60_bounded_fit import fit_bounded_position  # noqa: E402
from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.analysis.regional_position_bootstrap import observation_subset  # noqa: E402


def subset_objective(base, keep):
    model = Hard60Objective(
        observation_subset(base.observations, np.flatnonzero(keep)),
        base.bank,
        base.prior,
        base.score,
        receiver_baseline_hz=base.baseline[keep],
    )
    # Subsetting otherwise changes implicit RF/time centering. Preserve the
    # physical meaning of the seed's existing receiver nuisance parameters.
    model.design = base.design[keep].copy()
    return model


def groups(base, seed, limit=8):
    _, _, terms = base.evaluate(seed)
    assignment = terms.responsibilities.argmax(axis=1)
    confidence = terms.responsibilities.max(axis=1)
    mass = terms.responsibilities.sum(axis=0)
    ranked = sorted(range(len(mass)), key=lambda i: (-mass[i], int(base.bank.numbers[i])))
    result = []
    for i in ranked[:limit]:
        removed = (assignment == i) & (confidence >= 0.8)
        if removed.sum() >= 14:
            result.append((i, removed, float(mass[i])))
    return result


def run(label):
    output = HERE / "influence" / f"{label}.json"
    if output.exists():
        raise FileExistsError(output)
    case, document, base, seed = load(label)
    variants = [(None, np.zeros(len(base.observations.window_ids), bool), 0.0)]
    variants += groups(base, seed)
    rows = []
    for index, removed, mass in variants:
        model = base if index is None else subset_objective(base, ~removed)
        for arm in ("fitted-c", "zero-c"):
            fit, diagnostic = fit_bounded_position(
                model,
                seed,
                rf_arm=arm,
                maximum_seconds=20,
                maximum_iterations=600,
                local_center=seed[:2],
                local_radius_km=25,
            )
            row = json_value(fit)
            full_value, _, full_terms = base.evaluate(fit.vector)
            full_mass = full_terms.responsibilities.sum()
            row.update(
                arm=arm,
                removed_satellite=None if index is None else int(base.bank.numbers[index]),
                removed_rows=int(removed.sum()),
                initial_posterior_mass=mass,
                removed_rows_rx=[
                    int((removed & (base.observations.receiver == rx)).sum()) for rx in (0, 1)
                ],
                error_km=error_km(case.prior, fit.vector, document),
                displacement_km=float(np.linalg.norm(fit.vector[:2] - seed[:2])),
                full_objective=full_value,
                full_posterior_rms_hz=float(
                    np.sqrt(
                        np.sum(full_terms.responsibilities * full_terms.residual_hz**2) / full_mass
                    )
                ),
                stop_diagnostics=json_value(diagnostic),
            )
            rows.append(row)
            print(
                label,
                row["removed_satellite"],
                arm,
                fit.converged,
                round(row["error_km"], 3),
                round(row["displacement_km"], 3),
                flush=True,
            )
    write_json(
        output,
        dict(
            label=label,
            session_id=document["session_id"],
            seed=seed,
            satellites=base.bank.numbers.tolist(),
            observation_count=len(base.observations.window_ids),
            group_rule="top-eight-posterior-mass; argmax>=0.8; minimum14",
            candidates=rows,
        ),
    )


if __name__ == "__main__":
    for label in sys.argv[1:]:
        run(label)
