"""Diagnostic only: does original raw curvature survive robust radio fitting?"""

import json

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import Scan
from dsx01_radio_curvature import fit_polynomial
from prototype_dsx01_remeasured_position import apply_measurements
from run_dsx01_clock_transfer import MEASUREMENTS, OUTPUT, measurement_path


def run():
    result = {}
    for case in [f"DSX01-S0{k}" for k in range(1, 6)]:
        points = json.loads(measurement_path(case).read_text())["points"]
        for variant in MEASUREMENTS:
            scan = Scan(case)
            apply_measurements(scan, points, variant)
            rows = []
            for i in scan.curved:
                t = scan.tracks[i]
                if len(t["times"]) < 12:
                    rows.append(
                        dict(
                            component=t["key"],
                            points=len(t["times"]),
                            active_curvature=False,
                            selected_degree=None,
                            selected_curvature_rms_hz=None,
                            signal_points=None,
                            reason="fewer than twelve points",
                            fits=[],
                        )
                    )
                    continue
                fit = fit_polynomial(t["times"], t["values"])
                rows.append(
                    dict(
                        component=t["key"],
                        points=len(t["times"]),
                        active_curvature=fit["active_curvature"],
                        selected_degree=fit["selected"]["degree"],
                        selected_curvature_rms_hz=fit["selected"]["curvature_rms_hz"],
                        signal_points=fit["selected"]["signal_points"],
                        fits=[
                            {
                                k: v
                                for k, v in f.items()
                                if k not in ["prediction", "signal_responsibility"]
                            }
                            for f in fit["fits"]
                        ],
                    )
                )
            result[case + "/" + variant] = rows
            write(OUTPUT / "radio_curvature_diagnostic.json", result)
            print(case, variant, len(rows), sum(r["active_curvature"] for r in rows), flush=True)
    write(
        OUTPUT / "radio_curvature_protocol.json",
        dict(
            original_partitions_and_eligibility_unchanged_in_main_experiments=True,
            radio_only_no_TLE_satellite_or_GPS_used_to_score_curvature=True,
            maximum_polynomial_degree=4,
            noise_sigma_hz=150,
            contamination_sigma_hz=5000,
            signal_prior=0.98,
            complexity_penalty="(degree+1)*log(original_points)",
            active_threshold="degree>=2,250Hz curvature,12signal points,20s span",
            no_random_or_time_holdout=True,
            diagnostic_does_not_drop_points_from_existing_fits=True,
        ),
    )


if __name__ == "__main__":
    run()
