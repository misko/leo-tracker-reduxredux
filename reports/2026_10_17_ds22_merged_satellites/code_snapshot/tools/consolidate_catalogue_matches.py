"""Identity-proposal-guided merging using frozen calibration and all native points."""

import argparse
import json
from pathlib import Path

import analyze_dsx01_fixed_site as matching
import numpy as np
from associate_merged_track_catalogue import load_tracks, write

from leo.analysis.research.identified_track_merging import consolidate
from leo.analysis.research.track_catalogue_geometry import frequency_grid


def run(cohort, catalogue, output):
    output.mkdir(parents=True, exist_ok=False)
    summaries = []
    for case in sorted(catalogue.glob("*/bias_1000")):
        sid = case.parent.name
        tracks = load_tracks(cohort / sid)
        mapping = {t["key"]: t for t in tracks}
        execution = json.loads((catalogue / sid / "execution.json").read_text())
        commands = [stage["command"] for stage in execution]
        command = next(c for c in commands if "associate" in c)
        inputs = Path(command[command.index("--inputs") + 1])
        with np.load(inputs / "bank.npz") as archive:
            original_sky = {k: archive[k] for k in archive.files}
        for fitted_c in (False, True):
            name = "fitted_c" if fitted_c else "c0"
            source = json.loads((case / f"fragments_{name}.json").read_text())
            summary = source["summary"]
            rows = [r for r in source["components"] if r["compatible"]]
            ids = sorted({r["candidate_norad"] for r in rows})
            indexes = [list(original_sky["norad"]).index(n) for n in ids]
            sky = dict(
                time_s=original_sky["time_s"],
                position_km=original_sky["position_km"][indexes],
                velocity_km_s=original_sky["velocity_km_s"][indexes],
            )
            times = (
                np.unique(np.concatenate([mapping[r["component"]]["times"] for r in rows]))
                if rows
                else np.array([])
            )
            if rows:
                frequency, _ = frequency_grid(
                    sky, times, summary["latitude_deg"], summary["longitude_deg"]
                )
            beta = np.array(summary["beta"])
            segments = []
            for row in rows:
                t = mapping[row["component"]]
                ix = np.searchsorted(times, t["times"])
                g = matching.group(t)
                prediction = t["rf_hz"] / 11.5e9 * frequency[ids.index(row["candidate_norad"]), ix]
                prediction += beta[g] + beta[g + 4] * (t["times"] - 150) / 150
                if fitted_c:
                    prediction += beta[8] * (t["rf_hz"] / 1e9 - 11.5)
                alias = np.rint(np.mean(prediction - t["values"]) / matching.PERIOD)
                residual = t["values"] + alias * matching.PERIOD - prediction
                segments.append(
                    dict(
                        key=t["key"],
                        candidate_norad=row["candidate_norad"],
                        time_s=t["times"],
                        native_residual_hz=residual,
                        observation_ids=t["observation_ids"],
                    )
                )

            def accept(residual, times):
                return (
                    np.sqrt(np.mean(residual**2)) <= 450
                    and matching.noise_screen(residual, times)["noise_screen_pass"]
                )

            result = consolidate(segments, accept)
            if result["points"] != summary["compatible_points"]:
                raise ValueError("consolidation failed its fixed population control")
            folder = output / sid
            folder.mkdir(exist_ok=True)
            write(folder / f"{name}.json", result)
            summaries.append(
                dict(
                    source_id=sid,
                    fitted_c=fitted_c,
                    input_tracks=result["input_tracks"],
                    output_tracks=result["output_tracks"],
                    points=result["points"],
                    points_dropped=result["points_dropped"],
                )
            )
    write(output / "summary.json", summaries)
    print(
        json.dumps(
            dict(cases=len(summaries), points_dropped=sum(r["points_dropped"] for r in summaries))
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cohort", type=Path, required=True)
    p.add_argument("--catalogue", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    q = Path("/mnt/qnap01")
    if a.output.resolve() == q or q in a.output.resolve().parents:
        p.error("QNAP is read-only")
    run(a.cohort, a.catalogue, a.output)
