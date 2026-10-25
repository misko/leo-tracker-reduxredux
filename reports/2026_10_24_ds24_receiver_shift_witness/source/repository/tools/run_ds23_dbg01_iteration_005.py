"""Next bounded worst-two DBG01 batch, retaining ALGO02/03 causal controls."""

import csv
from pathlib import Path

import run_ds23_dbg01_iteration_002 as engine
from run_algo01_ds23_sample import ROOT,read,sha,write

RAW=ROOT/'reports/2026_10_22_ds23_dbg01_iteration_005_raw'
CLOSED=('DS23-0081','DS23-0326','DS23-0035','DS23-0041','DS23-0111','DS23-0390','DS23-0405','DS23-0221','DS23-0322')


def batch_cases(rows):
    return engine.next_cases(rows,closed=CLOSED)


def configure():
    engine.RAW=RAW;engine.configure()


def protocol():
    RAW.mkdir(parents=True,exist_ok=True)
    record=dict(iteration=5,cases=batch_cases(list(csv.DictReader(engine.baseline.BENCHMARK.open()))),
        previously_closed=list(CLOSED),debug_queue_skip_only=['DS23-0405'],
        benchmark_sha256=sha(engine.baseline.BENCHMARK),source_sha256=sha(Path(__file__)),
        engine_sha256=sha(Path(engine.__file__)),
        parent_report='reports/2026_10_22_ds23_dbg01_iteration_004/README.md',
        parent_published_commit='cc028c05a8f669e312dbc1546aafdfe407269672',
        current_labels_bound_before_inventory_and_ablations=True,
        regional_center=[37.906,-122.545],regional_width_km=25.,
        all_active_families_and_retained_curved_tracks_ablated=True,
        both_c_arms_same_observations_candidates_other_priors_gates_and_budgets=True,
        inference_no_GPS_following_TLE_manual_identities_or_stationary_pooling=True,
        no_new_RF_or_IQ_reprocessing=True,publish_all_bounded_iteration_results=True,
        no_ALGO_release_without_matched_full_DS23_confirmation=True)
    path=RAW/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen iteration005 protocol')
    else:write(path,record)
    return record


def main():
    configure();engine.protocol=protocol;engine.main()


if __name__=='__main__':main()
