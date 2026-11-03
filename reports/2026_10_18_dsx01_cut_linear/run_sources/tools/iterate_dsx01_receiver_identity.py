"""Refresh candidate phases without restoring the legacy tight drift bounds."""

import argparse
import hashlib
import json
from pathlib import Path

from associate_merged_track_catalogue import write
from compare_dsx01_retention_localization import METHODS, ROOT, Scan
from iterate_dsx01_position_nominations import fit_once
from iterate_dsx01_profiled_identity import explore
from prototype_dsx01_continuous_position import numpy_state
from prototype_dsx01_receiver_geometry import OUTPUT as SOURCE
from prototype_dsx01_receiver_geometry import geometry_problem

OUTPUT = ROOT / "reports/2026_10_18_dsx01_receiver_identity"


def run(case, method, *, mean=10.0, rounds=3):
    directory = OUTPUT / case / method
    directory.mkdir(parents=True, exist_ok=True)
    source = SOURCE / case / method / "endpoints.json"
    variant = f"mean_{mean:g}_height_0"
    inherited = json.loads(source.read_text())
    incumbent = {arm: inherited[f"{variant}/{arm}"] for arm in ("c0", "fitted_c")}
    path = directory / f"mean_{mean:g}_iterations.json"
    records = json.loads(path.read_text()) if path.exists() else []
    start = records[-1]["fits"]["c0"] if records else incumbent["c0"]
    state, anchor = numpy_state(start["state"]), start["east_north_km"]
    scan = Scan(case)
    write(
        directory / f"mean_{mean:g}_protocol.json",
        dict(
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            no_reference_GPS_or_oracle_states=True,
            radio_prior_mean_sigma_hz_s=mean,
            band_contrast_sigma_hz_s=0.5,
            legacy_tight_drift_update_disabled=True,
            proposals_already_one_shared_phase_per_candidate=True,
            candidate_phase_topk_per_curve=4,
            maximum_proposals=64,
            common_c0_rows_aliases_and_geographic_starts=True,
            incumbent_remains_in_final_score_selection=True,
            rounds=rounds,
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        ),
    )
    for iteration in range(len(records), rounds):
        seed, diagnostics = explore(scan, state, anchor, method, compact_update=False)

        def factory(*args):
            return geometry_problem(*args, mean_sigma=mean, height_sigma=0.0)

        fits = fit_once(scan, seed, method, anchor, problem_class=factory)
        records.append(dict(iteration=iteration, proposal=diagnostics, fits=fits))
        write(path, records)
        start = fits["c0"]
        anchor, state = start["east_north_km"], numpy_state(start["state"])
        print(
            json.dumps(
                dict(
                    case=case,
                    method=method,
                    iteration=iteration,
                    positions={a: f["east_north_km"].tolist() for a, f in fits.items()},
                )
            ),
            flush=True,
        )
    selected = {}
    for arm in ("c0", "fitted_c"):
        choices = [dict(incumbent[arm], selected_from="incumbent")]
        choices.extend(dict(r["fits"][arm], selected_from=r["iteration"]) for r in records)
        selected[arm] = min(choices, key=lambda f: f["score"])
    write(directory / f"mean_{mean:g}_endpoints.json", selected)
    return selected


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", default="DSX01-S01")
    p.add_argument("--method", choices=METHODS, default="shared_phase")
    p.add_argument("--mean", type=float, default=10.0)
    p.add_argument("--rounds", type=int, default=3)
    a = p.parse_args()
    run(a.case, a.method, mean=a.mean, rounds=a.rounds)
