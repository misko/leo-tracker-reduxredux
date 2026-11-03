"""Bound whole-satellite leverage while keeping the wider RX drift prior."""

import argparse
import hashlib
import json
from pathlib import Path

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import fit_once
from prototype_dsx01_family_consensus import ConsensusFamilies
from prototype_dsx01_receiver_geometry import SOURCE
from prototype_s01_receiver_drift import ReceiverDriftProblem

OUTPUT = ROOT / "reports/2026_10_18_dsx01_receiver_consensus"


def run(case, method, *, mean=10.0):
    directory = OUTPUT / case / method
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "endpoints.json"
    if path.exists():
        return json.loads(path.read_text())
    scan = Scan(case)
    source = SOURCE / case / f"{method}_center.json"
    seed = json.loads(source.read_text())

    def factory(*args):
        return ReceiverDriftProblem(
            ConsensusFamilies(*args, mode="consensus_floor"), mean_sigma=mean
        )

    write(
        directory / "protocol.json",
        dict(
            no_reference_GPS_or_oracle_states=True,
            all_original_curved_points_retained=True,
            same_c_arms_nominations_aliases_grid_3_starts_24_iterations=True,
            whole_family_data_and_phase_priors_normalized_and_bounded=True,
            receiver_priors_outside_family_energy_cap=True,
            common_RX_mean_sigma_hz_s=mean,
            family_support_normalized_to_50_points=True,
            normalized_family_energy_cap=200,
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    fits = fit_once(scan, seed, method, (0, 0), problem_class=factory)
    write(path, fits)
    print(json.dumps({a: f["east_north_km"].tolist() for a, f in fits.items()}), flush=True)
    return fits


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S01")
    p.add_argument("--method", choices=METHODS, default="shared_phase")
    a = p.parse_args()
    run(a.case, a.method)
