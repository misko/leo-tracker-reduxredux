"""Next bounded worst-two batch after iteration005; existing ALGO02/03 engines."""

import csv
from pathlib import Path

import run_ds23_dbg01_iteration_005 as previous
from run_algo01_ds23_sample import ROOT,read,sha,write

engine=previous.engine
RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_006_raw'
CLOSED=previous.CLOSED+('DS23-0272','DS23-0068')


def batch_cases(rows):
    return engine.next_cases(rows,closed=CLOSED)


def configure():
    engine.RAW=RAW;engine.configure()


def protocol():
    RAW.mkdir(parents=True,exist_ok=True)
    record=dict(iteration=6,cases=batch_cases(list(csv.DictReader(engine.baseline.BENCHMARK.open()))),
        previously_closed=list(CLOSED),debug_queue_skip_only=['DS23-0405'],
        benchmark_sha256=sha(engine.baseline.BENCHMARK),source_sha256=sha(Path(__file__)),
        engine_sha256=sha(Path(engine.__file__)),
        parent_report='reports/2026_10_22_ds23_dbg01_iteration_005/README.md',
        parent_published_commit='d1cab78789f8a82d6b9749c26eb8dd6b7c29e7d4',
        current_labels_bound_before_inventory_and_ablations=True,
        regional_center=[37.906,-122.545],regional_width_km=25.,
        all_active_families_and_retained_curved_tracks_ablated=True,
        both_c_arms_same_observations_candidates_other_priors_gates_and_budgets=True,
        inference_no_GPS_following_TLE_manual_identities_or_stationary_pooling=True,
        inherited_baseline_phase_qualification_must_be_reported_separately_from_fallback=True,
        no_new_RF_or_IQ_reprocessing=True,publish_all_bounded_iteration_results=True,
        no_ALGO_release_without_matched_full_DS23_confirmation=True)
    path=RAW/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen iteration006 protocol')
    else:write(path,record)
    return record


def main():
    configure();engine.protocol=protocol;engine.main()


if __name__=='__main__':main()
