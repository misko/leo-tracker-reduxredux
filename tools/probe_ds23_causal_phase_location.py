"""Matched single-scan position test of causally qualified signed prior centers."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time
import numpy as np

from algo02_scan import pair_passes
from ds23_causal_phase_location import qualify, adjust_means, KINDS
from investigate_ds23_adaptive_failures import phase_widths
from probe_algo03_frame_peak_recovery import context, SOURCE
from probe_ds23_frequency_events import parameters, refit
from probe_ds23_gate_retention_cohort import OUT as COHORT, ARMS
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_causal_phase_location'


def initialize():
    destination = OUT/'protocol.json'
    if destination.exists():
        return read(destination)
    OUT.mkdir(parents=True, exist_ok=True)
    cohort = read(COHORT/'protocol.json')
    protocol = dict(cases=cohort['cases'], development=cohort['development'], additional=cohort['additional'],
        cohort_is_reused_development_not_untouched_validation=True, candidate_mean_features=KINDS,
        unchanged_phase_scales_tails_forecast_shrinkage_and_clip=True,
        prior_selection='earliest70percentTLEupdates, excluding NORADmod5=0; future and held-satellite density gains > logN+2log4',
        all_causal_catalogue_histories_used_not_RF_selected_families=True,
        prior_choice_before_current_RF_fit_and_without_GPS=True,
        no_new_or_removed_points_no_labels_aliases_noise_or_hardware_changes=True,
        paired_c_masks_priors_and_budgets=True, cold_start_km=[0,0], box_width_km=25,
        phase_rounds=5, position_iterations=48, original_paired_gates_unchanged=True,
        workers=20, source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/'tools/ds23_causal_phase_location.py'))
    write(destination, protocol)
    return protocol


def run_case(case, output_directory=None):
    directory = OUT if output_directory is None else Path(output_directory)
    destination = directory/(case+'.json')
    if destination.exists():
        return dict(case=case, cached=True)
    start = time.monotonic()
    scan, node, mask, base, old = context(case)
    powers, ordinary, hyper = parameters(scan, base, old)
    history_path = SOURCE/'causal_phase_history'/(case+'.json')
    forecast_path = history_path.with_name(case+'_forecast.json')
    history, forecast = read(history_path), read(forecast_path)
    if sha(history_path) != forecast['history_sha256']:
        raise ValueError('causal history digest mismatch')
    if history['cutoff_utc_ns'] != scan.receipt['cutoff_utc_ns']:
        raise ValueError('scan/history cutoff mismatch')
    cutoff = history['cutoff_utc_ns']
    if any(v['epoch'] > cutoff or v['collected_utc_ns'] > cutoff
           for versions in history['past_versions'].values() for v in versions):
        raise ValueError('post-scan TLE in history')
    rows = forecast['transitions']
    if any(r['validation_time_ns'] > cutoff for r in rows):
        raise ValueError('post-scan target in mean qualification')
    selected = qualify(rows, forecast['temporal_split_boundary_ns'], forecast['prefix_distribution'], hyper)
    _, receipts = phase_widths(scan, base.labels)
    means = adjust_means(ordinary, receipts, hyper, selected)
    entries = old['linear_entries'] if old['linear_paired_valid'] else []
    pair = ({a:refit(scan, node, mask, a, powers, means, hyper, [], entries) for a in ARMS}
            if selected['qualified'] else old['policy_arms'])
    # A null correction reuses an already accepted published policy. Some
    # curved-only historical records predate the predictive phase-change key.
    valid = pair_passes(pair, include_linear=True) if selected['qualified'] else True
    write(destination, dict(case=case, selection=selected, means_s=means, original_means_s=ordinary,
        arms=pair, baseline_arms=old['policy_arms'], policy_arms=pair if valid else old['policy_arms'],
        paired_valid=valid, accepted=bool(selected['qualified'] and valid),
        GPS_used=False, future_TLE_used=False, original_mask=mask,
        history_sha256=sha(history_path), forecast_sha256=sha(forecast_path), seconds=time.monotonic()-start))
    result = dict(case=case, qualified=selected['qualified'], kind=selected.get('kind'),
        coefficient=selected.get('coefficient'), paired_valid=valid, seconds=time.monotonic()-start)
    print(result, flush=True)
    return result


def main():
    protocol = initialize()
    if (OUT/'execution.json').exists() and not (OUT/'execution_initial.json').exists():
        write(OUT/'execution_initial.json', read(OUT/'execution.json'))
        write(OUT/'execution_bugfix.json', dict(
            reason='unqualified exact-null policies need no new predictive gate replay',
            historical_curved_only_results_lack_final_phase_change_key=True,
            no_inference_objective_observations_or_selection_change=True,
            original_source_sha256=protocol['source_sha256'], corrected_source_sha256=sha(Path(__file__))))
    results = []
    with ProcessPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(run_case, c):c for c in protocol['cases']}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append(dict(case=futures[future], error=repr(exc)))
            write(OUT/'progress.json', dict(completed=len(results), total=len(futures), results=results))
    write(OUT/'execution.json', dict(results=results, all_terminal=True))


if __name__ == '__main__':
    main()
