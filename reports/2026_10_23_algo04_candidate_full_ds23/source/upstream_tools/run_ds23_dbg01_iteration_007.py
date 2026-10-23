"""Next bounded DBG01 batch; the rejected constrained extension is not adopted."""

import csv
from pathlib import Path

import run_ds23_dbg01_iteration_006 as previous
from run_algo01_ds23_sample import ROOT,read,sha,write

engine=previous.engine
RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_007_raw'
CLOSED=previous.CLOSED+('DS23-0069','DS23-0291')


def batch_cases(rows):
    return engine.next_cases(rows,closed=CLOSED)


def configure():
    engine.RAW=RAW;engine.configure()


def protocol():
    RAW.mkdir(parents=True,exist_ok=True)
    record=dict(iteration=7,cases=batch_cases(list(csv.DictReader(engine.baseline.BENCHMARK.open()))),
        previously_closed=list(CLOSED),debug_queue_skip_only=['DS23-0405'],
        benchmark_sha256=sha(engine.baseline.BENCHMARK),source_sha256=sha(Path(__file__)),engine_sha256=sha(Path(engine.__file__)),
        parent_report='reports/2026_10_22_ds23_dbg01_iteration_006/README.md',
        parent_published_commit='e6b0544652751ded12dbf57d61bdb51443566f6e',
        continue_original_ALGO02_ALGO03_engines=True,iteration006_supported_constrained_extension_not_adopted=True,
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
        if read(path)!=record:raise ValueError('preserve frozen iteration007 protocol')
    else:write(path,record)
    return record


def main():
    configure();engine.protocol=protocol;engine.main()


if __name__=='__main__':main()
