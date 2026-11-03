"""Local position/phase gauge audit on qualified curved diagnostic matches."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import load_tracks, write

from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.phase_position_identifiability import conditional_position_information


def run(diagnosis, recordings, banks, output):
    output.mkdir(parents=True, exist_ok=False)
    result = []
    for path in sorted(diagnosis.glob("*/*/diagnosis.json")):
        case = path.parent.parent.name
        rows = json.loads(path.read_text())
        if len(rows) != 2:
            raise ValueError("diagnostic process has not finished both fixed sites")
        recording = recordings / ("cohort" if case.startswith("DS22") else "dsx01_adapter") / case
        mapping = {t["key"]: t for t in load_tracks(recording)}
        with np.load(banks / f"ds22-shared-phase-bank-{case}" / "bank.npz") as archive:
            original = {k: archive[k] for k in archive.files}
        number_index = {int(n): i for i, n in enumerate(original["norad"])}
        for row in rows:
            fit = row["fit"]
            qualified = [
                r for r in row["association"]["rows"] if r["compatible"] and r["active_curvature"]
            ]
            features = []
            if qualified:
                ids = sorted({r["candidate_norad"] for r in qualified})
                indexes = [number_index[n] for n in ids]
                sky = dict(
                    time_s=original["time_s"],
                    position_km=original["position_km"][indexes],
                    velocity_km_s=original["velocity_km_s"][indexes],
                )
                phases = np.asarray(fit["phases_s"])[indexes]
                times = np.unique(
                    np.concatenate([mapping[r["component"]]["times"] for r in qualified])
                )
                geometry = prepare_phase_geometry(sky, times, phases)
                latitude, longitude = fit["latitude_deg"], fit["longitude_deg"]
                _, _, phase_derivative = phase_linear_frequency(geometry, latitude, longitude)
                step = 0.25
                derivatives = []
                for latitude_step, longitude_step in (
                    (step / 111.32, 0),
                    (0, step / (111.32 * np.cos(np.deg2rad(latitude)))),
                ):
                    plus, _ = phase_frequency_grid(
                        sky,
                        times,
                        latitude + latitude_step,
                        longitude + longitude_step,
                        phase_seconds=phases,
                    )
                    minus, _ = phase_frequency_grid(
                        sky,
                        times,
                        latitude - latitude_step,
                        longitude - longitude_step,
                        phase_seconds=phases,
                    )
                    derivatives.append((plus - minus) / (2 * step))
                for match in qualified:
                    track = mapping[match["component"]]
                    j = ids.index(match["candidate_norad"])
                    ix = np.searchsorted(times, track["times"])
                    q = track["rf_hz"] / 11.5e9
                    features.append(
                        dict(
                            component=track["key"],
                            satellite=match["candidate_norad"],
                            times=track["times"],
                            group=2 * (track["receiver"] - 1) + int(track["channel"] > 4),
                            rf_ratio=q,
                            active_curvature=True,
                            phase_sensitivity_hz_s=q * phase_derivative[j, ix],
                            position_sensitivity_hz_km=q
                            * np.column_stack([d[j, ix] for d in derivatives]),
                        )
                    )
            sigma = (
                {
                    n: float(original["phase_sigma_s"][number_index[n]])
                    for n in {f["satellite"] for f in features}
                }
                if fit["phase_enabled"]
                else {}
            )
            information = conditional_position_information(
                features, fitted_c=fit["fitted_c"], phase_sigma_s=sigma
            )
            result.append(
                dict(
                    case=case,
                    variant=path.parent.name,
                    site=row["site"],
                    information=information,
                    input_diagnosis_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    scope=(
                        "conditional on qualified curved candidate assignments; "
                        "not empirical confidence"
                    ),
                )
            )
    write(output / "results.json", result)
    write(
        output / "protocol.json",
        dict(
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            information_source_sha256=hashlib.sha256(
                Path(__file__)
                .resolve()
                .parents[1]
                .joinpath("src/leo/analysis/research/phase_position_identifiability.py")
                .read_bytes()
            ).hexdigest(),
            position_step_km=0.25,
            satellite_identities_conditioned_on=True,
            no_geographic_fit=True,
        ),
    )
    print(json.dumps(dict(cases=len(result))), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--diagnosis", type=Path, required=True)
    p.add_argument("--recordings", type=Path, required=True)
    p.add_argument("--banks", type=Path, default=Path("/tmp"))
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    q = Path("/mnt/qnap01")
    if a.output.resolve() == q or q in a.output.resolve().parents:
        p.error("QNAP is read-only")
    run(a.diagnosis, a.recordings, a.banks, a.output)
