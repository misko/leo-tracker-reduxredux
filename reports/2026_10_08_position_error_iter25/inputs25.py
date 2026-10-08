"""Load the fixed operational seed and candidate bank for all consumed cohorts."""

import json
import sys
from pathlib import Path

import numpy as np

REPORTS = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPORTS / f"2026_10_08_position_error_iter{n}") for n in ("20", "24", "13")]
# isort: off
from newer import load_member  # noqa: E402
from post_prune import load_basis  # noqa: E402
from inputs import json_value  # noqa: E402
# isort: on

from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402
from leo.contracts.digests import canonical_digest  # noqa: E402


def load(label, protocol):
    binding = protocol["members"][label]
    if binding["cohort"] in ("FRESH", "LATER"):
        previous = json.loads((REPORTS / binding["result"]).read_text())["result"]
        document = json.loads((REPORTS / binding["baseline"]).read_text())
        case = load_member(binding["member"])
        assert canonical_digest(case.document) == canonical_digest(document)
        assert previous["regional_sources"]["fitted-c"] == "baseline"
        chosen = previous["stages"]["drift-50"]["fitted-c"]
        numbers = previous["satellites"]
        old_operational = previous["operational"]
        lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
        bank = case.bank.select([lookup[n] for n in numbers])
        selected = next(
            a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
        )
        calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
        base = Hard60Objective(
            case.prepared.observations,
            bank,
            case.prior,
            HARD60_SCORE,
            receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
        )
        seed, clock = np.asarray(chosen["vector"]), np.asarray(chosen["clock_coefficients"])
        source_stage = "drift-50"
    else:
        previous = json.loads((REPORTS / binding["result"]).read_text())
        post = json.loads((REPORTS / binding["post200"]).read_text())
        case, document, original_base = load_basis(label, protocol["consumed_ds17_labels"])
        lookup = {int(n): i for i, n in enumerate(original_base.bank.numbers)}
        bank = original_base.bank.select([lookup[n] for n in previous["satellites"]])
        base = Hard60Objective(
            original_base.observations,
            bank,
            case.prior,
            original_base.score,
            receiver_baseline_hz=original_base.baseline,
        )
        selected = next(
            a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
        )
        calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
        chosen = next(
            r
            for r in previous["candidates"]
            if r["variant"] == "drift-50" and r["arm"] == "fitted-c"
        )
        source_stage = "drift-50"
        if not chosen["converged"]:
            chosen = next(
                r
                for r in post["candidates"]
                if r["variant"] == "post-200" and r["arm"] == "fitted-c"
            )
            source_stage = "post-200"
            if not chosen["converged"]:
                chosen = next(r for r in post["previous_candidates"] if r["arm"] == "fitted-c")
                source_stage = "remove-5"
        seed = np.asarray(chosen["vector"])
        clock = np.asarray(chosen["clock_coefficients"])
        if source_stage != "drift-50":
            clock = np.r_[clock, 0.0, 0.0]
        summary = json.loads(
            (REPORTS / "2026_10_08_position_error_iter19/summary.json").read_text()
        )
        record = next(row for row in summary["cases"] if row["label"] == label)
        old_operational = {
            arm: dict(
                error_km=row["drift-50"]["error_km"],
                posterior_rms_hz=row["drift-50"]["rms_hz"],
                archived_fallback=row["drift-50"]["fallback"],
            )
            for arm, row in record["arms"].items()
        }
    assert chosen["converged"]
    return (
        case,
        document,
        base,
        calibration["correction"],
        seed,
        clock,
        dict(
            previous_operational=json_value(old_operational),
            source_stage=source_stage,
            source_objective=chosen["objective"],
        ),
    )
