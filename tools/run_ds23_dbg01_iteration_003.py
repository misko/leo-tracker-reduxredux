"""Next worst-two DBG01 batch, with the verified current-label context."""

import csv
from pathlib import Path

import run_ds23_dbg01_iteration_002 as engine
from run_algo01_ds23_sample import ROOT, read, sha, write

RAW = ROOT/'reports/2026_10_22_ds23_dbg01_iteration_003_raw'
CLOSED = ('DS23-0081','DS23-0326','DS23-0035','DS23-0041','DS23-0405')


def batch_cases(rows):
    return engine.next_cases(rows, closed=CLOSED)


def configure():
    engine.RAW = RAW
    engine.configure()


def protocol():
    RAW.mkdir(parents=True,exist_ok=True)
    record = dict(iteration=3,cases=batch_cases(list(csv.DictReader(engine.baseline.BENCHMARK.open()))),
        previously_closed=list(CLOSED),
        queue_skip_only={'DS23-0405':'prior DBG01 and bounded controls completed; remains in evaluation'},
        benchmark_sha256=sha(engine.baseline.BENCHMARK),
        parent_report='reports/2026_10_22_ds23_dbg01_iteration_002/README.md',
        parent_published_commit='81c5d65f39fe5d6701141a72b34a98c4d8a1f443',
        source_sha256=sha(Path(__file__)),
        current_context_bound_before_any_inventory_or_ablation=True,
        context_helper_sha256=sha(ROOT/'tools/ds23_current_assignment_context.py'),
        engine_sha256=sha(Path(engine.__file__)),
        regional_center=[37.906,-122.545],regional_width_km=25.,
        original_points_candidates_other_priors_gates_and_budgets_matched_between_c_arms=True,
        inference_no_GPS_or_following_TLE_or_manual_satellite_choice=True,
        debug_priority_only_uses_reported_position_error=True,
        no_new_RF_or_IQ_reprocessing_or_stationary_pooling=True,
        workers_DBG01=24,workers_case_stages=2,
        publish_all_bounded_iteration_results=True,no_ALGO_release_without_full_DS23_confirmation=True)
    path=RAW/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen iteration003 protocol')
    else:write(path,record)
    return record


def main():
    configure()
    engine.protocol=protocol
    engine.main()


if __name__=='__main__':main()
