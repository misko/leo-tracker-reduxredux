"""Apply frozen joint-site/radio fits to every original graph fragment.

No position or nuisance update occurs. Linear fragments receive calibration
only after location and all calibration parameters have been frozen.
"""

import argparse
import csv
import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from localize_merged_track_catalogue import distance_km
from prototype_dsx01_continuous_position import numpy_state
from prototype_dsx01_receiver_geometry import OUTPUT
from refine_dsx01_exact_receiver_orbits import exact_corrected_bank
from report_dsx01_model_iterations import REFERENCE

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)


def run(case, methods=METHODS, *, exact=False):
    directory = OUTPUT / ("pooled_exact_transfer" if exact else "pooled_transfer") / case
    directory.mkdir(parents=True, exist_ok=True)
    raw_path = ROOT / "reports/2026_10_18_dsx01_retention_localization/per_scan.csv"
    with raw_path.open() as f:
        raw_counts = {r["case"]: int(r["raw_points"]) for r in csv.DictReader(f)}
    scan = None
    for method in methods:
        source = OUTPUT / (
            "pooled_exact_refinement/endpoints.json"
            if exact
            else f"pooled/{method}/mean_10_endpoints.json"
        )
        endpoints = json.loads(source.read_text())
        path = directory / f"{method}.json"
        result = json.loads(path.read_text()) if path.exists() else {}
        for arm, fit in endpoints.items():
            if arm in result:
                continue
            scan = Scan(case) if scan is None else scan
            lat, lon = fit["latitude_deg"], fit["longitude_deg"]
            point = np.array([(lon - scan.center[1]) * scan.scale, (lat - scan.center[0]) * 111])
            state = numpy_state(fit["states"][case])
            base = phase_linear_frequency(scan.geometry, lat, lon)
            if exact:
                labels = sorted(state["extra"])
                bank = exact_corrected_bank(scan, labels, state["extra"])
                geometry = prepare_phase_geometry(bank, scan.times, state["phases"][labels])
                nominal_predictions = Scan.predictions

                def exact_predictions(
                    state,
                    base,
                    point,
                    method,
                    geom=geometry,
                    active=labels,
                    source_scan=scan,
                    nominal=nominal_predictions,
                ):
                    f, e, h = nominal(source_scan, dict(state, extra={}), base, point, method)
                    f[active], e[active], h[active] = phase_linear_frequency(
                        geom, *source_scan.latlon(point)
                    )
                    return f, e, h

                scan.predictions = exact_predictions
            _, rows, _, _ = scan.association(state, base, point, method, all_tracks=True)
            accepted = [r for r in rows if r["compatible"]]
            count = sum(r["points"] for r in accepted)
            segments = sum(r["parts"] for r in accepted)
            result[arm] = dict(
                case=case,
                method=method,
                arm=arm,
                latitude_deg=lat,
                longitude_deg=lon,
                position_error_km=distance_km((lat, lon), REFERENCE),
                position_and_nuisance_frozen=True,
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                raw_point_denominator_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                associated_points=count,
                raw_points=raw_counts[case],
                percent_associated=100 * count / raw_counts[case],
                associated_fragments=len(accepted),
                association_segments=segments,
                points_per_segment=count / max(1, segments),
                accepted_rms_hz=float(
                    np.sqrt(
                        sum(np.sum(np.asarray(r["residual_hz"]) ** 2) for r in accepted)
                        / max(1, count)
                    )
                ),
                legacy_gated_objective_not_used_to_select_or_update=True,
                no_evaluation_GPS_in_frozen_fit=True,
                orbital_prediction_exact_SGP4=exact,
                rows=rows,
            )
            write(path, result)
            print(case, method, arm, count, flush=True)
    return directory


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", required=True)
    p.add_argument("--methods", nargs="+", choices=METHODS, default=METHODS)
    p.add_argument("--exact", action="store_true")
    a = p.parse_args()
    run(a.case, ("orbit_em",) if a.exact else tuple(a.methods), exact=a.exact)
