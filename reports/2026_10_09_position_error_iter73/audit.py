"""Fixed-state score decomposition; evaluation diagnostics cannot seed inference."""

import hashlib
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter68"))
from audit import make_model, residuals  # noqa: E402

sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter52"))
from common_sigma1 import load_member, read, write_json  # noqa: E402


def main():
    plan = read(HERE / "protocol.json")
    for name, digest in plan["source_sha256"].items():
        assert hashlib.sha256((REPORTS / name).read_bytes()).hexdigest() == digest, name
    if (HERE / "results.json").exists():
        raise FileExistsError("Preserve first fixed-state audit")
    members = read(REPORTS / "2026_10_08_position_error_iter29/protocol.json")["members"]
    case = load_member(next(m for m in members if m["label"] == "RESERVED-001"))
    census = read(REPORTS / "2026_10_09_position_error_iter53/results.json")
    doc = read(REPORTS / "2026_10_08_position_error_iter29/baselines/RESERVED-001.json")
    model = make_model(case, doc, 1, census["candidate_union"])
    completed = read(REPORTS / "2026_10_09_position_error_iter72/summary.json")
    sources = []
    for arm, metrics in completed["metrics"].items():
        for label, key in (
            ("operational-winner", "hard_all_winner"),
            ("closest-evaluation-only", "closest_qualified_evaluation_only"),
        ):
            row = metrics[key]
            sources.append(
                dict(
                    label=label,
                    arm=arm,
                    source_index=row["index"],
                    fit=row["fit"],
                    error_km=row["error_km"],
                )
            )
    diagnostic = read(REPORTS / "2026_10_09_position_error_iter52/results.json")
    for i, row in enumerate(diagnostic["rows"]):
        sources.append(
            dict(
                label="historical-" + row["hypothesis"],
                arm=row["arm"],
                source_index=i,
                source_arm=row["source_arm"],
                fit=row["fit"],
                error_km=row["fit"]["error_km"],
            )
        )
    rows = []
    for source in sources:
        fit = source["fit"]
        vector, clock = np.asarray(fit["vector"]), np.asarray(fit["clock_coefficients"])
        score, _, _, terms = model.evaluate_joint(vector, clock)
        relative = model.basis @ vector[8:]
        components = dict(
            frequency_nll=float(terms.nll),
            common_timing=float(0.5 * (vector[7] / model.score.common_sigma_s) ** 2),
            relative_timing=float(0.5 * np.sum((relative / model.score.relative_sigma_s) ** 2)),
            clock=float(0.5 * clock @ model.precision @ clock),
        )
        np.testing.assert_allclose(score, fit["objective"], atol=1e-6, rtol=0)
        np.testing.assert_allclose(sum(components.values()), score, atol=1e-7, rtol=0)
        np.testing.assert_allclose(
            components["clock"], fit["calibration_penalty"], atol=1e-7, rtol=0
        )
        pairs, _, pair_residual = residuals(model, vector, clock)
        row = {k: v for k, v in source.items() if k != "fit"}
        row.update(
            converged=fit["converged"],
            objective=float(score),
            components=components,
            frequency_rms_hz=fit["posterior_rms_hz"],
            signal_windows=fit["signal_windows"],
            relative_timing_rms_s=float(np.sqrt(np.mean(relative**2))),
            pair_count=len(pairs),
            pair_median_absolute_hz=float(np.median(abs(pair_residual))),
            pair_fraction_within250hz=float(np.mean(abs(pair_residual) <= 250)),
        )
        rows.append(row)
    write_json(HERE / "results.json", dict(rows=rows, scope=plan["scope"]))
    print(
        "Audited", len(rows), "fixed states; no optimization or operational selection", flush=True
    )


if __name__ == "__main__":
    main()
