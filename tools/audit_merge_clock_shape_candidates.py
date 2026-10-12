"""Probe orbital-shape candidate sensitivity to common receiver drift."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import LOCAL, REPORT
from continuous_merge_positions import load_prepared
from continuous_merge_study import plain, sha, write
from global_band_merge_study import verify

from leo.analysis.hard60_score import predict_orbits
from leo.analysis.lnb_band_calibration import calibrated_band_observations
from leo.analysis.regional_position_bootstrap import bootstrap_position
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior


def main():
    output = REPORT / "local/predictive-curves/clock-shape-probe.json"
    if output.exists():
        raise ValueError("clock-shape sensitivity receipt already exists")
    sid = "fast-43ce59233fe914e1d273ee584efcd405"
    case = LOCAL / "DS20" / sid / "global-transfer"
    protocol_path = case / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol)
    prepared = load_prepared(Path(protocol["original_case"]) / "baseline.json")
    obs, _ = calibrated_band_observations(prepared.observations, protocol["fixed_band_offsets_hz"])
    parent_path = REPORT / "refinement/complete-parent-audit.json"
    parent = json.loads(parent_path.read_bytes())
    target = next(r for r in parent["rows"] if r["calibrated"] and r["lane"][:3] == [2, "lower", 1])
    track_rows = [tuple(p["rows"]) for p in target["parents"]]
    joined = tuple(target["joined_matches_at_cached_calibrated_point"][0]["rows"])
    pool = tuple(dict.fromkeys([*prepared.bootstrap_tracks, *track_rows, joined]))
    seed_path = REPORT / "refinement/seed-sampling-and-weight-audit.json"
    seed = json.loads(seed_path.read_bytes())
    settings = [("zero-drift", [0.0, 0.0])]
    for source in seed["rows"]:
        for key in ("seed_vector", "coarse_vector"):
            vector = source[key]
            settings.append((source["mode"] + "-" + key, [vector[3], vector[5]]))
    with np.load(protocol["bank_path"]) as z:
        bank = PositionOrbitBank(**{key: z[key] for key in z.files})
    point = tuple(float(v) for v in parent["point"].split(":")[1:])
    records = []
    for name, slopes in settings:
        derived = replace(
            obs,
            measured_hz=(
                obs.measured_hz - np.array(slopes)[obs.receiver] * (obs.times_s - obs.time_center_s)
            ),
        )
        fit = bootstrap_position(
            derived,
            bank,
            RegionalPrior(),
            point,
            pool,
            maximum_seconds=120,
            orbit_predictor=predict_orbits,
        )
        lookup = {tuple(m.rows): m for m in fit.matches}
        record = {
            "source": name,
            "subtracted_slopes_hz_per_s": slopes,
            "preferred_catalogue_by_original_track": [
                int(bank.numbers[lookup[t].satellite_index]) if t in lookup else None
                for t in prepared.bootstrap_tracks
            ],
            "target": [],
        }
        for label, rows in zip(
            ("selected-parent", "added-parent", "joined"), [*track_rows, joined], strict=True
        ):
            match = lookup.get(rows)
            record["target"].append(
                {
                    "label": label,
                    "match": plain(match),
                    "catalogue_number": int(bank.numbers[match.satellite_index]) if match else None,
                }
            )
        records.append(record)
        print(
            json.dumps(
                {
                    "source": name,
                    "target": [
                        {
                            "label": r["label"],
                            "catalogue_number": r["catalogue_number"],
                            "shape_rms_hz": (r["match"] or {}).get("shape_rms_hz"),
                        }
                        for r in record["target"]
                    ],
                }
            ),
            flush=True,
        )
    baseline = records[0]["preferred_catalogue_by_original_track"]
    for record in records:
        record["changed_original_preferences"] = sum(
            a != b
            for a, b in zip(baseline, record["preferred_catalogue_by_original_track"], strict=True)
        )
    write(
        output,
        {
            "session_id": sid,
            "point": point,
            "rows": records,
            "bindings": {
                str(p): sha(p) for p in (Path(__file__), protocol_path, parent_path, seed_path)
            },
            "reference_usage": "none",
            "scope": (
                "Fixed initial bank, point, pool and shape/timing budgets. Subtract each existing "
                "common receiver slope before constant-centered shape profiling. Existing clocks "
                "are in-sample conditioning states, not new fits or physical truths. No learned "
                "RF-dependent c is fitted in these profiles; coarse slope sources condition on "
                "shared fitted-c discovery. This is candidate sensitivity, not position accuracy."
            ),
        },
    )


if __name__ == "__main__":
    main()
