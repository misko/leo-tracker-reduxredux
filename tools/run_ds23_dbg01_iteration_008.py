"""Next worst-two batch after the non-promoted full prediction experiment."""

import csv
from pathlib import Path

import run_ds23_dbg01_iteration_007 as previous
from run_algo01_ds23_sample import ROOT,read,sha,write

engine=previous.engine
RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_008_raw'
CLOSED=previous.CLOSED+('DS23-0227','DS23-0400')


def batch_cases(rows):
    return engine.next_cases(rows,closed=CLOSED)


def configure():
    engine.RAW=RAW;engine.configure()


def protocol():
    RAW.mkdir(parents=True,exist_ok=True)
    record=dict(iteration=8,cases=batch_cases(list(csv.DictReader(engine.baseline.BENCHMARK.open()))),
        previously_closed=list(CLOSED),debug_queue_skip_only=['DS23-0405'],
        benchmark_sha256=sha(engine.baseline.BENCHMARK),source_sha256=sha(Path(__file__)),engine_sha256=sha(Path(engine.__file__)),
        parent_report='reports/2026_10_22_ds23_dbg01_iteration_007/README.md',
        parent_published_commit='b934ed298f262f0f28199c4f3829983ab3ba4bfa',
        continue_original_ALGO02_ALGO03_engines=True,
        iteration007_new_family_prediction_not_adopted_as_default=True,
        iteration007_endpoint_core_not_adopted_as_default=True,
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
        if read(path)!=record:raise ValueError('preserve frozen iteration008 protocol')
    else:write(path,record)
    return record


def main():
    configure();engine.protocol=protocol;engine.main()


if __name__=='__main__':main()
