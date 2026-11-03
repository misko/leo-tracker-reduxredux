"""Full-corpus confirmation of one frozen, TLE-only mean correction."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from probe_ds23_causal_phase_location import run_case, OUT as DEVELOPMENT, SOURCE
from validate_ds23_causal_phase_location import OUT as VALIDATION
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_causal_phase_location_full'


def initialize():
    destination = OUT/'protocol.json'
    if destination.exists():
        return read(destination)
    OUT.mkdir(parents=True, exist_ok=True)
    population = read(SOURCE/'sample.json')['selected']
    cases, unavailable = [], []
    for row in population:
        case = row['dataset_label']
        path = SOURCE/case/'algo02_result.json'
        if not path.exists():
            unavailable.append(dict(case=case, reason='no accepted original ALGO02 result'))
        elif read(path)['status'] != 'accepted':
            unavailable.append(dict(case=case, reason='original ALGO02 input failure'))
        else:
            cases.append(case)
    development = read(DEVELOPMENT/'protocol.json')['cases']
    validation = read(VALIDATION/'protocol.json')['cases']
    extra = sorted(set(cases)-set(development)-set(validation))
    cache = {}
    for directory in (DEVELOPMENT, VALIDATION):
        for case in cases:
            path = directory/(case+'.json')
            if path.exists():
                cache[case] = dict(path=str(path.relative_to(ROOT)), sha256=sha(path))
    sources = [Path(__file__), ROOT/'tools/probe_ds23_causal_phase_location.py', ROOT/'tools/ds23_causal_phase_location.py']
    protocol = dict(cases=cases, unavailable=unavailable, population=population,
        development=development, prior_validation=validation, additional_confirmation=extra, cache=cache,
        rule_and_hyperparameters_unchanged_after_first20_validation=True,
        first20_validation_means_improved_but_medians_unchanged_and_strict_criterion_failed=True,
        no_recording_selected_or_dropped_using_GPS_error=True,
        remaining_confirmatory_subset_and_entire_cohort_must_both_improve_mean_and_median_in_both_c_arms=True,
        failed_new_trials_retain_original_positions_and_stay_in_denominator=True,
        nine_original_unavailable_recordings_remain_explicit_not_assigned_invented_errors=True,
        all_records_one_site_not_external_location_validation=True, workers=20,
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources})
    write(destination, protocol)
    return protocol


def job(case, cache):
    if case in cache:
        record = cache[case]
        if sha(ROOT/record['path']) != record['sha256']:
            raise ValueError('cached trial changed after full-corpus freeze')
        return dict(case=case, path=record['path'], cached=True)
    result = run_case(case, str(OUT))
    result['path'] = str((OUT/(case+'.json')).relative_to(ROOT))
    return result


def main():
    protocol = initialize()
    results = []
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(job, case, protocol['cache']):case for case in protocol['cases']}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(dict(case=futures[future], error=repr(exc)))
            write(OUT/'progress.json', dict(completed=len(results), total=len(futures), results=results))
    write(OUT/'execution.json', dict(results=results, all_terminal=True))


if __name__ == '__main__':
    main()
