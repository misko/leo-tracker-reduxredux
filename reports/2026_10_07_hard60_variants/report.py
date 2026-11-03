"""Produce the final explanatory report from completed, independently checked results."""
import csv
import json
from pathlib import Path
import numpy as np
import run_variants as run
import analyze
from summarize import distance_km
from leo.analysis.regional_position_score import coordinates
from leo.contracts.regional_position import RegionalPrior


def holdout_summary():
    doc=run.read(run.HERE/'holdout_results.json')
    pairs=[]
    for case in doc['results']:
        for arm in analyze.ARMS:
            control=next(r for r in case['rows'] if r['arm']==arm and not r['rf_enabled'])
            variant=next(r for r in case['rows'] if r['arm']==arm and r['rf_enabled'])
            pair=dict(label=case['label'],kind=case['kind'],block=case['block'],arm=arm,
                control_accepted=control['accepted'],rf_accepted=variant['accepted'],
                paired_accepted=control['accepted'] and variant['accepted'],windows=control['heldout_windows'],
                delta_nll=variant['heldout_data_nll']-control['heldout_data_nll'])
            pair['delta_nll_per_window']=pair['delta_nll']/pair['windows']
            pairs.append(pair)
    summary={}
    for arm in analyze.ARMS:
        summary[arm]={}
        for kind in ('time','rf'):
            rows=[r for r in pairs if r['arm']==arm and r['kind']==kind]
            accepted=[r for r in rows if r['paired_accepted']]
            summary[arm][kind]=dict(total=len(rows),control_accepted=sum(r['control_accepted'] for r in rows),
                rf_accepted=sum(r['rf_accepted'] for r in rows),paired_accepted=len(accepted),
                improved=sum(r['delta_nll']<0 for r in accepted),
                worsened=sum(r['delta_nll']>0 for r in accepted),
                mean_delta_nll_per_window=sum(r['delta_nll'] for r in accepted)/sum(r['windows'] for r in accepted) if accepted else None)
    out=dict(scope=doc['protocol']['scope'],summary=summary,pairs=pairs)
    run.engine.write(run.HERE/'holdout_summary.json',out)
    with (run.HERE/'holdout_pairs.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)
    return out


def write_report(result,holdout):
    lines=['N01--N64: three isolated Hard60 variants','',
        'Every configuration uses relative timing sigma 2 s, common timing sigma 3 s, hard +/-60 Hz/s additional affine slopes, corrected 40/20/10/5 km search, 400 grid locations and three retained regions.',
        'Hard60 is the original immutable control. Each variant adds exactly one mechanism; these are not combined variants.',
        'Two starts: geometry bootstrap plus independent zero timing/slopes at each coarse location; 5 s/200 iterations per start. The best objective is used for coarse ranking as in the control. New downstream regions are refit.',
        'Calibration recovery: retain original successful regions; failed prefit/postfit gets one continuation, then one zero-timing restart if still rejected. Strict stationarity 0.001 and all bounds remain unchanged.',
        'RF offsets: retain control grid, calibration and association. Fit receiver-by-RF residual offsets only at final stage, Gaussian SD 50 Hz and hard group bounds +/-150 Hz. The design excludes receiver mean and shared linear RF coefficient c directions. Same three final starts and 20 s/600-iteration budget per arm as control.',
        'Both final c arms use matched observations, candidate banks, calibration, priors and search/fit budgets within each variant. Discovery and calibration use fitted c. This is a final-stage c ablation, not end-to-end c=0.',
        'Reference coordinates are used only by evaluation. Selection uses score and unchanged numerical certification. The known difficult cases are retained in the full 64; no tuning after looking at their results.',
        'Previous study artifacts were hash-verified and left unchanged. No new RF collection or production code changes.', '']
    for arm in analyze.ARMS:
        lines.append(arm)
        for phase in analyze.PHASES:
            s=result['summary'][arm][phase];p=s['position_error_km']
            lines.append(f"  {analyze.NAMES[phase]}: accepted {s['accepted']}/64; median {p['median']:.3f} km; p90 {p['p90']:.3f}; max {p['maximum']:.3f} ({s['worst_scan']}); mean {p['mean']:.3f}; <5 km {p['under5']}; >10 km {p['over10']}; median frequency RMS {s['median_frequency_rms_hz']:.3f} Hz.")
            lines.append(f"    Paired with Hard60: improved {s['paired_improved']}, worsened {s['paired_worsened']}, unchanged within 1 m {s['paired_unchanged']}; median paired change {s['median_paired_change_km']:.3f} km.")
            lines.append(f"    Median paired frequency RMS change: {s['median_paired_frequency_rms_change_hz']:.3f} Hz; fit metric only, over accepted paired scans.")
        lines.append('')
    lines.append('Stage and work diagnostics:')
    for phase in analyze.PHASES:
        group=[r for r in result['stages'] if r['phase']==phase]
        lines.append(f"  {analyze.NAMES[phase]}: reference covered {sum(r['reference_covered'] for r in group)}/64; failed region pipelines {sum(r['failed_regions'] for r in group)}; recovered regions {sum(r['recovered_regions'] for r in group)}; regions without accepted zero-c/fitted-c result {sum(r['no_accepted_zero_c_regions'] for r in group)}/{sum(r['no_accepted_fitted_c_regions'] for r in group)}; recorded coarse fits {sum(r['coarse_fit_attempts'] for r in group)}; coarse timeouts {sum(r['coarse_timeouts'] for r in group)}; final timeouts {sum(r['final_timeouts'] for r in group)}; summed coarse-fit seconds {sum(r['coarse_fit_seconds'] for r in group):.1f}; summed final-fit seconds {sum(r['final_fit_seconds'] for r in group):.1f}.")
        if phase=='two_starts':
            lines.append(f"    Second initialization wins {sum(r['second_start_wins'] for r in group)} of {sum(r['coarse_paired_starts'] for r in group)} recorded two-fit comparisons; {sum(r['new_retained_regions'] for r in group)} retained regions differ from the control.")
    lines += ['', 'Timing caveat: these fit-seconds are diagnostic work totals, not elapsed full-pipeline latency. Immutable control stages were reused; concurrency and machine load differ. Two starts doubles the allowed coarse fits, not necessarily total pipeline runtime.', '', 'Difficult scans:']
    for label in run.WATCH:
        for arm in analyze.ARMS:
            rows=[next(r for r in result['rows'] if (r['label'],r['arm'],r['phase'])==(label,arm,p)) for p in analyze.PHASES]
            lines.append(f"  {label} {arm}: "+' | '.join(f"{analyze.NAMES[r['phase']]} {r['error_km']} km" for r in rows))
    lines += ['', 'Calibration-recovery regression on N21:',
        'The recovered region (-77.5,-87.5) beats the previous selected region (-90,-90) by model score. Zero-c error increases from 2.314 to 3.681 km and fitted-c from 5.119 to 5.999 km. Two coarse starts leaves N21 unchanged. This is a downstream model-ranking effect, not rejection or lack of grid coverage.']
    lines += ['', 'Conditional held-out final-stage frequency checks:',
        'Six difficult captures, two contiguous time-half folds and four leave-one-RF-group-out folds per capture. Final parameters refit on training windows. Search region, bank and frozen calibration still came from the full capture, so this is not independent end-to-end validation. It diagnoses whether additional final RF freedom transfers beyond the fitted windows.',
        'Negative held-out NLL change favors RF offsets. Only paired converged fits enter means; rejection counts are reported rather than hidden.']
    for arm,groups in holdout['summary'].items():
        for kind,s in groups.items():lines.append(f"  {arm} {kind}: {s}")
    lines += ['', 'N64 RF-offset numerical failure:',
        'The zero-c nearby region has a feasible candidate at 0.588 km error with score about 26,832, better than the selected remote score about 34,016, but its best fits fail the unchanged 0.001 stationarity criterion (roughly 0.0034--0.0048). This yields approximately 299 km error. It is numerical acceptance failure, not evidence that the likelihood prefers that remote solution over the nearby feasible state.',
        'Additional final-state continuation probes are separate diagnostics and never enter the benchmark.']
    diagnostic=run.read(run.HERE/'rf_n64_diagnostic.json')
    prior=RegionalPrior(**run.read(run.OLD/'inputs'/'N64'/'inputs.json')['prior'])
    ref=run.read(run.OLD/'evaluation.json');reference=[ref['reference_latitude_deg'],ref['reference_longitude_deg']]
    for arm in analyze.ARMS:
        pool=[r for r in diagnostic['rows'] if r['arm']==arm and r['converged']]
        if pool:
            best=min(pool,key=lambda r:r['selection_score'])
            err=distance_km(*coordinates(prior,best['vector'][:2]),reference)
            lines.append(f"  Extra diagnostic {arm}: best accepted error {err:.3f} km, score {best['selection_score']:.3f}, start {best['name']}.")
        else:lines.append(f'  Extra diagnostic {arm}: no accepted result.')
    stationarity=run.read(run.HERE/'rf_stationarity.json')
    step=1e-6
    positive=next(p['value_change'] for p in stationarity['profile'] if p['step_scaled']==step)
    negative=next(p['value_change'] for p in stationarity['profile'] if p['step_scaled']==-step)
    curvature=(positive+negative)/step**2
    derivative=stationarity['analytic_directional_derivative']
    estimated_gain=derivative**2/(2*curvature)
    numerical=dict(directional_curvature=curvature,analytic_directional_derivative=derivative,
        quadratic_estimated_gain=estimated_gain,quadratic_estimated_scaled_step=-derivative/curvature,
        terminal=stationarity['terminal'],scope='One local projected-gradient direction; not a global or complete second-order certificate.')
    run.engine.write(run.HERE/'rf_precision_diagnostic.json',numerical)
    lines.append(f"  Along one tested projected-gradient direction, local quadratic curvature implies only {estimated_gain:.3g} score units of remaining improvement. The terminal optimizer state still fails strict stationarity. This supports a numerical conditioning/precision issue, without certifying a global optimum or changing acceptance.")
    lines += ['', 'Validation: analytic/finite-difference RF gradients, original/native objective agreement, known constrained optimum including active RF bounds and exact zero-c, recovery acceptance behavior, full search replays, score-only winner reconstruction, and original-likelihood selected-state audits.',
        'All results describe this development cohort. Better in-sample frequency fit alone does not establish better position accuracy or performance on new captures.']
    (run.HERE/'findings.txt').write_text('\n'.join(lines)+'\n')


def main():
    result=run.read(run.HERE/'summary.json')
    assert result['complete'] and run.read(run.HERE/'validation_full.json')['all_checks_passed']
    holdout=holdout_summary();write_report(result,holdout)
    # Pin result/search/region content as well as source and presentation files.
    files=[p for p in run.HERE.iterdir() if p.is_file() and p.suffix in ('.py','.json','.csv','.txt','.png','.svg') and p.name!='artifact_manifest.json']
    files += list((run.HERE/'results').glob('*/*/result.json'))
    files += list((run.HERE/'results').glob('*/*/search.json'))
    files += list((run.HERE/'results').glob('*/*/regions/*.json'))
    files += list((run.HERE/'results').glob('*/two_starts/points/*.json'))
    files += list((run.HERE/'results').glob('*/bootstrap/*.json'))
    files += list((run.HERE/'holdout').glob('*.json'))
    files.append(run.HERE/'tests.log')
    run.engine.write(run.HERE/'artifact_manifest.json',dict(files={str(p.relative_to(run.HERE)):run.data.digest(p) for p in sorted(files)}))
    print('REPORT COMPLETE:',len(files),'artifacts hashed')


if __name__=='__main__':main()
