"""Matched-budget development tests; validation labels rejected by iter01 loader."""

import sys
from pathlib import Path

from receiver_rf import VARIANTS, fit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026_10_08_position_error_iter01"))
sys.path.insert(0, str(HERE.parent / "2026_10_08_hard60_bounded_recovery"))
from inputs import json_value, write_json  # noqa: E402
from probe import error_km, load  # noqa: E402

from leo.analysis.hard60_bounded_fit import fit_bounded_position  # noqa: E402


def run(label):
    output = HERE / "probes" / f"{label}.json"
    if output.exists():
        raise FileExistsError(output)
    case, document, objective, seed = load(label)
    rows = []
    for variant in ("matched-control", *VARIANTS):
        for arm in ("fitted-c", "zero-c"):
            if variant == "matched-control":
                result, _ = fit_bounded_position(
                    objective,
                    seed,
                    rf_arm=arm,
                    maximum_seconds=20,
                    maximum_iterations=600,
                    local_center=seed[:2],
                    local_radius_km=25,
                )
                result = json_value(result)
            else:
                result = json_value(fit(objective, seed, sigma=VARIANTS[variant], arm=arm))
            result.update(
                variant=variant, arm=arm, error_km=error_km(case.prior, result["vector"], document)
            )
            rows.append(result)
            print(
                label, variant, arm, result["converged"], round(result["error_km"], 4), flush=True
            )
    write_json(
        output,
        dict(
            label=label,
            session_id=document["session_id"],
            seed=seed,
            satellites=objective.bank.numbers.tolist(),
            candidates=rows,
            observation_count=len(objective.observations.window_ids),
        ),
    )


if __name__ == "__main__":
    for label in sys.argv[1:]:
        run(label)
