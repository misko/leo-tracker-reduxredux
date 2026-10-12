"""Data-selected B7 residual profiles for a constant receiver/band correction."""

import json
from pathlib import Path

import numpy as np
from continuous_merge_consistency_study import LOCAL, REPORT
from continuous_merge_positions import load_prepared
from continuous_merge_study import sha, write
from shared_track_refinement_study import restore

from leo.analysis.hard60_score import likelihood, predict_orbits
from leo.contracts.regional_position import PositionOrbitBank


def main():
    rows, authorities = [], {}
    for dataset, sid in (
        ("DS20", "fast-014c72ff95ab599c51ba3b3ec9b92cb8"),
        ("DS16", "scan-fw-0e40d0535caa0b16"),
    ):
        case = LOCAL / dataset / sid
        p = json.loads((case / "shared-refinement/protocol.json").read_bytes())
        prepared = load_prepared(Path(p["original_case"]) / "baseline.json")
        terminal_path = case / "positions/baseline/terminal.json"
        terminal = json.loads(terminal_path.read_bytes())
        authorities[str(terminal_path)] = sha(terminal_path)
        with np.load(case / "positions/bank.npz") as z:
            bank = PositionOrbitBank(**{k: z[k] for k in z.files})
        for arm in ("fitted-c", "zero-c"):
            final = next(f for f in terminal["result"]["finals"] if f["arm"] == arm)
            model, vector, clock = restore(prepared, bank, final, p["groups"]["joined"], 0.0)
            _, _, _, terms = model.evaluate_joint(vector, clock)
            visible = predict_orbits(
                model.bank,
                model.observations,
                model.prior,
                vector[:2],
                vector[7] + model.basis @ vector[8:],
                derivatives=False,
            )[1]
            for receiver in (0, 1):
                for high in (False, True):
                    mask = (model.observations.receiver == receiver) & (
                        (model.observations.channel >= 5) == high
                    )
                    row = {
                        "dataset": dataset,
                        "session_id": sid,
                        "arm": arm,
                        "receiver": receiver,
                        "band": "CH5-8" if high else "CH1-4",
                        "windows": int(mask.sum()),
                        "reference_usage": "none",
                    }
                    if not mask.any():
                        rows.append({**row, "status": "no-observations"})
                        continue
                    residual, seen = terms.residual_hz[mask], visible[mask]

                    def score(offset, residual=residual, seen=seen, position_score=model.score):
                        return likelihood(
                            np.zeros(len(residual)), -residual + offset, seen, position_score
                        ).nll

                    def search(grid, scorer=score):
                        return min(
                            (
                                scorer(float(g)) + 0.5 * (float(g) / 25000) ** 2,
                                abs(float(g)),
                                float(g),
                            )
                            for g in grid
                        )

                    best = search(np.arange(-50000.0, 50000.001, 500.0))
                    best = search(
                        np.arange(
                            max(-50000.0, best[2] - 500), min(50000.0, best[2] + 500) + 0.001, 50.0
                        )
                    )
                    best = search(
                        np.arange(
                            max(-50000.0, best[2] - 50), min(50000.0, best[2] + 50) + 0.001, 5.0
                        )
                    )
                    independent_nll = score(0.0)
                    row.update(
                        status="profiled",
                        correction_hz=best[2],
                        original_nll=independent_nll,
                        profiled_nll=score(best[2]),
                        penalized_gain=independent_nll - best[0],
                        original_signal_mass=float(terms.responsibilities[mask].sum()),
                    )
                    rows.append(row)
    write(
        REPORT / "band-residual-profile.json",
        {
            "script_sha256": sha(Path(__file__)),
            "authorities": authorities,
            "rows": rows,
            "scope": (
                "Exposed residual sensitivity at each data-selected baseline solution; "
                "no reference coordinates used. Fixed observations, bank, position, epochs and "
                "existing calibration "
                "within each c arm. Four receiver/band corrections are profiled independently on "
                "identical grids with a 25 kHz Gaussian scale. This is an in-sample "
                "diagnostic, not a full joint band-calibration fit, a position "
                "improvement or a physical-cause claim."
            ),
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
