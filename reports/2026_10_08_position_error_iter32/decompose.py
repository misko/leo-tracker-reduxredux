"""Post-hoc comparison of same-bank joint100 minima, without further fitting."""

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter31"))
# isort: off
from branch import Hard60Objective, HARD60_SCORE  # noqa: E402
from pipeline import InitialClockObjective  # noqa: E402
from newer import load_member  # noqa: E402
from inputs import write_json  # noqa: E402
# isort: on


def main():
    plan = json.loads((HERE / "protocol.json").read_text())
    members = json.loads((REPORTS / "2026_10_08_position_error_iter29/protocol.json").read_text())[
        "members"
    ]
    output = {}
    for label, binding in plan["cases"].items():
        current = json.loads((HERE / "results" / f"{label}.json").read_text())
        control = json.loads((REPORTS / binding["control"]).read_text())
        document = current["document"]
        selected = document["methods"][0]["arms"][0]["selected"]
        case = load_member(next(m for m in members if m["label"] == label))
        lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
        bank = case.bank.select([lookup[n] for n in selected["satellites"]])
        cal = document["diagnostics"]["calibrations"][binding["basin"]]
        base = Hard60Objective(
            case.prepared.observations,
            bank,
            case.prior,
            HARD60_SCORE,
            receiver_baseline_hz=np.asarray(cal["receiver_baseline_hz"]),
        )
        model = InitialClockObjective(
            base, cal["correction"]["nodes_s"], cal["correction"]["knots_hz"], 2
        )
        arms = {}
        for arm in ("fitted-c", "zero-c"):
            variants = {}
            for name, source in (("original-start", control), ("zero-timing-start", current)):
                row = source["upstream"]["stages"]["joint-100"][arm]
                vector, clock = np.asarray(row["vector"]), np.asarray(row["clock_coefficients"])
                value, _, _, terms = model.evaluate_joint(vector, clock)
                np.testing.assert_allclose(value, row["objective"], atol=1e-6, rtol=0)
                relative = model.basis @ vector[8:]
                timing = 0.5 * np.sum((relative / model.score.relative_sigma_s) ** 2)
                common = 0.5 * (vector[7] / model.score.common_sigma_s) ** 2
                penalty = 0.5 * clock @ model.precision @ clock
                np.testing.assert_allclose(value, terms.nll + timing + common + penalty, atol=1e-6)
                variants[name] = dict(
                    error_km=row["error_km"],
                    objective=float(value),
                    data_nll=float(terms.nll),
                    relative_timing_penalty=float(timing),
                    common_timing_penalty=float(common),
                    clock_penalty=float(penalty),
                    common_s=float(vector[7]),
                    satellites=bank.numbers.tolist(),
                    relative_seconds=relative.tolist(),
                    posterior_mass=terms.responsibilities.sum(axis=0).tolist(),
                    fixed_vector_timing_sensitivity={
                        str(s): float(value - timing + 0.5 * np.sum((relative / s) ** 2))
                        for s in (0.25, 0.5, 0.75, 1, 1.5, 2)
                    },
                )
            arms[arm] = variants
        output[label] = arms
        print(
            label,
            {
                a: {
                    v: {k: r[k] for k in ("data_nll", "relative_timing_penalty", "clock_penalty")}
                    for v, r in rows.items()
                }
                for a, rows in arms.items()
            },
            flush=True,
        )
    write_json(
        HERE / "decomposition.json",
        dict(
            scope="Same-bank saved minima; prior sensitivity without reoptimization",
            cases=output,
        ),
    )


if __name__ == "__main__":
    main()
