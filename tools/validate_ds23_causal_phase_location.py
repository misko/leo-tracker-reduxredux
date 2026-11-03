"""Prospective recording selection for the frozen causal phase-location rule."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import re
import numpy as np

from probe_ds23_causal_phase_location import run_case, SOURCE, OUT as DEVELOPMENT
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_causal_phase_location_validation'


def initialize():
    destination = OUT/'protocol.json'
    if destination.exists():
        return read(destination)
    OUT.mkdir(parents=True, exist_ok=True)
    excluded = set(read(DEVELOPMENT/'protocol.json')['cases'])
    # FAI residual inventory covered almost all recordings but did not fit a
    # position variant. Original ALGO02 results also already cover this corpus.
    skipped = {'2026_10_19_algo03_fai_residuals', SOURCE.name}
    exposure_sources = {}
    directories = set(ROOT.glob('reports/*ds23*')) | set(ROOT.glob('reports/*algo03*'))
    for directory in sorted(directories):
        if directory.name in skipped or directory == OUT:
            continue
        cases = {m.group() for p in directory.glob('*DS23*')
                 if (m := re.search(r'DS23-\d{4}', p.name))}
        if cases:
            exposure_sources[directory.name] = sorted(cases)
            excluded.update(cases)
    candidates = []
    original_statuses = {}
    for path in sorted(SOURCE.glob('DS23-*/algo02_result.json')):
        status = read(path)['status']
        original_statuses[status] = original_statuses.get(status, 0)+1
        if status == 'accepted' and path.parent.name not in excluded:
            candidates.append(path.parent.name)
    if len(candidates) < 20:
        raise ValueError('insufficient additional recording support')
    cases = sorted(np.random.default_rng(15485863).choice(candidates, 20, replace=False).tolist())
    source_paths = [Path(__file__), ROOT/'tools/probe_ds23_causal_phase_location.py',
                    ROOT/'tools/ds23_causal_phase_location.py']
    document = dict(cases=cases, seed=15485863, available_pool=candidates, original_status_counts=original_statuses,
        excluded_cases=sorted(excluded), prior_position_artifact_sources=exposure_sources,
        original_baseline_and_global_FAI_inventory_previously_available=True,
        not_a_new_location_or_external_dataset=True, no_claim_completely_untouched_corpus=True,
        random_selection_never_reads_GPS_errors=True,
        rule_frozen_before_these_recordings_are_run_or_geographically_evaluated=True,
        mean_estimation_uses_only_each_scans_own_causal_TLE_history=True,
        no_hyperparameter_transfer_from_evaluated_scan_RF_or_GPS=True,
        inherited_development_protocol_sha256=sha(DEVELOPMENT/'protocol.json'),
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in source_paths},
        workers=20, source_GPS_blind=True,
        positive_publication_requires_both_mean_and_median_improve_in_both_c_arms=True,
        every_failed_trial_falls_back_to_original_baseline_and_stays_in_denominator=True)
    write(destination, document)
    return document


def main():
    protocol = initialize()
    results = []
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(run_case, case, str(OUT)):case for case in protocol['cases']}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(dict(case=futures[future], error=repr(exc)))
            write(OUT/'progress.json', dict(completed=len(results), total=len(futures), results=results))
    write(OUT/'execution.json', dict(results=results, all_terminal=True))


if __name__ == '__main__':
    main()
