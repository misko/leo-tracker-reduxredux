"""Next bounded worst-two DBG01 batch, preserving the current incumbent."""

import csv
from pathlib import Path

import run_ds23_dbg01_iteration_008 as previous
from run_algo01_ds23_sample import ROOT,read,sha,write

engine=previous.engine
RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_009_raw'
CLOSED=previous.CLOSED+('DS23-0157','DS23-0207')


def batch_cases(rows):
    return engine.next_cases(rows,closed=CLOSED)


def configure():
    engine.RAW=RAW;engine.configure()


def protocol():
    RAW.mkdir(parents=True,exist_ok=True)
    record=dict(iteration=9,cases=batch_cases(list(csv.DictReader(engine.baseline.BENCHMARK.open()))),
        previously_closed=list(CLOSED),debug_queue_skip_only=['DS23-0405'],
        benchmark_sha256=sha(engine.baseline.BENCHMARK),source_sha256=sha(Path(__file__)),engine_sha256=sha(Path(engine.__file__)),
        parent_report='reports/2026_10_22_ds23_dbg01_iteration_008/README.md',
        parent_published_commit='dc84a7da5f2d33e839a99d23fa2bf6870603264e',
        continue_original_ALGO02_ALGO03_engines=True,
        iteration008_temporal_and_short_curvature_prototypes_not_adopted_as_default=True,
        current_labels_bound_before_inventory_and_ablations=True,
        regional_center=[37.906,-122.545],regional_width_km=25.,
        all_active_families_and_retained_curved_tracks_ablated=True,
        both_c_arms_same_observations_candidates_other_priors_gates_and_budgets=True,
        inference_no_GPS_following_TLE_manual_identities_or_stationary_pooling=True,
        inherited_baseline_phase_qualification_reported_separately=True,
        no_new_RF_or_IQ_reprocessing=True,publish_all_bounded_iteration_results=True,
        no_ALGO_release_without_matched_full_DS23_confirmation=True)
    path=RAW/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen iteration009 protocol')
    else:write(path,record)
    return record


def main():
    configure();engine.protocol=protocol;engine.main()


if __name__=='__main__':main()
