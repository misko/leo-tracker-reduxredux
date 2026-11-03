import json
from pathlib import Path

import numpy as np

directory = Path(__file__).parent
data = json.loads((directory / "evidence.json").read_text())
rows = data["candidates"]
origin = data["origin_utc_ns"]
times = np.array([(row["support_center_utc_ns"] - origin) / 1e9 for row in rows])
scale = 11_200_000_000 / rows[0]["actual_rf_hz"]
alias = scale / 4.4e-6
frequency = np.array([row["measured_cfo_hz"] * scale for row in rows])
reference = (
    np.interp(times, [180, 194, 219, 228, 275, 285], [-55e3, -75e3, -130e3, -155e3, -315e3, -350e3])
    * scale
)
unwrapped = frequency - np.round((frequency - reference) / alias) * alias
support = set(
    data["replays"]["baseline"][0]["point_ids"] + data["replays"]["baseline"][2]["point_ids"]
)
selected = np.array([row["candidate_id"] in support for row in rows])
visits = np.array([row["visit_index"] for row in rows])
groups = np.unique(visits[selected])
generator = np.random.default_rng(20261001)
generator.shuffle(groups)
training_groups = groups[: round(0.7 * len(groups))]
training = selected & np.isin(visits, training_groups)
evaluation = selected & ~training
models = []
for degree in (1, 2, 3):
    coefficients = np.polynomial.polynomial.polyfit(
        times[training] - 230, unwrapped[training], degree
    )
    predicted = np.polynomial.polynomial.polyval(times - 230, coefficients)
    residual = unwrapped - predicted
    models.append(
        {
            "degree": degree,
            "training_count": int(training.sum()),
            "evaluation_count": int(evaluation.sum()),
            "evaluation_rms_hz": float(np.sqrt(np.mean(residual[evaluation] ** 2))),
            "evaluation_max_abs_hz": float(np.max(np.abs(residual[evaluation]))),
            "evaluation_within_2500hz": int((np.abs(residual[evaluation]) <= 2500).sum()),
            "coefficients_about_230s": coefficients.tolist(),
        }
    )
    if degree == 3:
        bridge = (times >= 219.4) & (times <= 228.56) & (np.abs(residual) <= 2500)
        best = {}
        for index in np.flatnonzero(bridge):
            key = rows[index]["source_group_id"]
            if key not in best or abs(residual[index]) < abs(residual[best[key]]):
                best[key] = index
        indexes = sorted(best.values(), key=lambda index: times[index])
        bridge_result = {
            "count": len(indexes),
            "times_s": times[indexes].tolist(),
            "max_gap_s": float(np.max(np.diff(times[indexes]))),
            "residual_rms_hz": float(np.sqrt(np.mean(residual[indexes] ** 2))),
        }
result = {
    "purpose": "Geometry diagnostic only; no satellite identification or production change",
    "seed": 20261001,
    "training_visits": training_groups.tolist(),
    "evaluation_visits": groups[len(training_groups) :].tolist(),
    "models": models,
    "bridge": bridge_result,
}
(directory / "curvature.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
