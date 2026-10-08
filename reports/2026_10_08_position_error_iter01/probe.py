"""Development-only same-seed, same-candidate clock-bias model probes."""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from satellite_bias import VARIANTS, fit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026_10_08_hard60_bounded_recovery"))
from baseline import load_case as load_ds17  # noqa: E402
from baseline import protocol  # noqa: E402
from inputs import json_value, write_json  # noqa: E402
from inputs import load_case as load_ds16  # noqa: E402

from leo.analysis.hard60_bounded_fit import fit_bounded_position  # noqa: E402
from leo.analysis.hard60_score import Hard60Objective  # noqa: E402
from leo.analysis.regional_position_score import coordinates  # noqa: E402
from leo.application.hard60_runner import HARD60_SCORE  # noqa: E402


def error_km(prior, vector, document):
    latitude, longitude = coordinates(prior, np.asarray(vector)[:2])
    lat, lon, ref_lat, ref_lon = map(
        math.radians,
        (
            latitude,
            longitude,
            document["reference_latitude_deg"],
            document["reference_longitude_deg"],
        ),
    )
    h = (
        math.sin((lat - ref_lat) / 2) ** 2
        + math.cos(lat) * math.cos(ref_lat) * math.sin((lon - ref_lon) / 2) ** 2
    )
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1, max(0, h))))


def load(label):
    if label.startswith("DS17-"):
        row = next(r for r in protocol()["membership"] if r["label"] == label)
        assert row["group"] == "development", "validation outcome lock"
        case = load_ds17(label)
        document = json.loads((HERE / "baseline" / f"{label}.json").read_text())
    else:
        case = load_ds16(label)
        document = case.document
        if label in ("S14", "S27"):
            document = json.loads(
                (
                    HERE.parent / "2026_10_08_hard60_bounded_recovery" / f"{label}-document.json"
                ).read_text()
            )
    selected = next(
        a["selected"] for a in document["methods"][0]["arms"] if a["name"] == "fitted-c"
    )
    row = next(
        r
        for r in document["diagnostics"]["final_starts"]
        if r["arm"] == "fitted-c"
        and r["basin"] == selected["source_basin"]
        and r["fit"]
        and r["fit"]["converged"]
        and abs(r["fit"]["objective"] - selected["objective"]) < 1e-9
    )
    lookup = {int(n): i for i, n in enumerate(case.bank.numbers)}
    bank = case.bank.select([lookup[n] for n in selected["satellites"]])
    calibration = document["diagnostics"]["calibrations"][selected["source_basin"]]
    objective = Hard60Objective(
        case.prepared.observations,
        bank,
        case.prior,
        HARD60_SCORE,
        receiver_baseline_hz=np.asarray(calibration["receiver_baseline_hz"]),
    )
    return case, document, objective, np.asarray(row["fit"]["vector"])


def run(label):
    output = HERE / "probes" / f"{label}.json"
    if output.exists():
        raise FileExistsError(output)
    case, document, objective, seed = load(label)
    candidates = []
    # Equal budget, start, observations and satellite bank in both c arms.
    for variant in ("matched-control", *VARIANTS):
        for arm in ("fitted-c", "zero-c"):
            if variant == "matched-control":
                result, diagnostics = fit_bounded_position(
                    objective,
                    seed,
                    rf_arm=arm,
                    maximum_seconds=20,
                    maximum_iterations=600,
                    local_center=seed[:2],
                    local_radius_km=25,
                )
                result = json_value(result)
                result.update(variant=variant, arm=arm, bias_hz=[0.0] * len(objective.bank.numbers))
            else:
                result = json_value(fit(objective, seed, variant=variant, arm=arm))
            result["error_km"] = error_km(case.prior, result["vector"], document)
            candidates.append(result)
            print(
                label, variant, arm, result["converged"], round(result["error_km"], 4), flush=True
            )
    write_json(
        output,
        {
            "label": label,
            "session_id": document["session_id"],
            "original_arms": document["methods"][0]["arms"],
            "satellites": objective.bank.numbers.tolist(),
            "seed": seed,
            "observation_count": len(objective.observations.window_ids),
            "variants": VARIANTS,
            "candidates": candidates,
            "reference_use": "evaluated only after optimizer returned each candidate",
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("labels", nargs="+")
    for label in parser.parse_args().labels:
        run(label)
