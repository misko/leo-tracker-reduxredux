"""Refit radio/satellite nuisance terms at a frozen blind consensus position."""

import argparse
import hashlib
import json

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, Scan
from prototype_dsx01_continuous_position import OUTPUT, numpy_state

from leo.analysis.research.phase_linear_geometry import phase_linear_frequency


def run(method="receiver_smooth", variant="continuous", rule="mean"):
    source = OUTPUT / "consensus_endpoints.json"
    consensus = json.loads(source.read_text())
    directory = OUTPUT / "consensus_calibration" / f"{rule}_{variant}_{method}"
    directory.mkdir(parents=True, exist_ok=True)
    results = {}
    for number in range(1, 6):
        case = f"DSX01-S0{number}"
        source_fit = json.loads((OUTPUT / case / "endpoints.json").read_text())
        scan = Scan(case)
        for arm in ("c0", "fitted_c"):
            position = consensus[f"{rule}/{variant}/{arm}/{method}"]
            lat, lon = position["latitude_deg"], position["longitude_deg"]
            point = np.array([(lon - scan.center[1]) * scan.scale, (lat - scan.center[0]) * 111])
            state = numpy_state(source_fit[f"{variant}/{arm}/{method}"]["state"])
            base = phase_linear_frequency(scan.geometry, lat, lon)
            history, best = [], None
            for i in range(9):
                score, rows, nominations, predicted = scan.association(state, base, point, method)
                history.append(dict(iteration=i, score=score))
                if best is None or score < best[0]:
                    best = score, state
                if i < 8:
                    state, _ = scan.update(state, nominations, predicted, point, method)
            state = best[1]
            score, rows, _, _ = scan.association(state, base, point, method, all_tracks=True)
            results[f"{case}/{arm}"] = dict(
                latitude_deg=lat,
                longitude_deg=lon,
                position_frozen=True,
                state=state,
                score=score,
                rows=rows,
                history=history,
            )
            write(directory / "endpoints.json", results)
            print(case, arm, sum(r["points"] for r in rows if r["compatible"]), flush=True)
    write(
        directory / "protocol.json",
        dict(
            no_reference_position_read=True,
            consensus_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            position_fixed_for_every_nuisance_round=True,
            curved_only_calibration=True,
            linear_tracks_receive_postfit_transfer_only=True,
            c0_fitted_c_same_points_candidates_priors_and_eight_nuisance_rounds=True,
            source_sha256=hashlib.sha256(
                __import__("pathlib").Path(__file__).read_bytes()
            ).hexdigest(),
            method=method,
            variant=variant,
            rule=rule,
            no_calibration_covariance_claim=True,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS, default="receiver_smooth")
    parser.add_argument("--variant", default="continuous")
    parser.add_argument("--rule", choices=("mean", "coordinate_median"), default="mean")
    args = parser.parse_args()
    run(args.method, args.variant, args.rule)
