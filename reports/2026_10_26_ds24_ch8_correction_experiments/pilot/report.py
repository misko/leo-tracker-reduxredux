"""Summarize frozen pilot results without additional IQ reads or model fits."""
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, data):
    (HERE/name).write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')


def binomial_interval(success, total):
    def cdf(k, p):
        return sum(math.comb(total,j)*p**j*(1-p)**(total-j) for j in range(k+1))
    def solve(k, target):
        lower, upper = 0., 1.
        for _ in range(64):
            middle = (lower+upper)/2
            if cdf(k,middle) > target:
                lower = middle
            else:
                upper = middle
        return (lower+upper)/2
    return [0. if success == 0 else solve(success-1,.975),
            1. if success == total else solve(success,.025)]


def sole_cell(panel, metadata):
    slot = next(s for s in panel['slots'] if s['request_id']=='DS24-0011-RX2-CH7-passed')
    doc = read(slot['tracking']['path'])
    selected = [p for p in doc['source']['probes'] if p['receiver_id']==1 and p['channel']==7]
    passed = [p for p in selected if any(c['passed_fractional_margin_gate'] for c in p['candidates'])]
    if len(passed) != 1 or passed[0] != {k:v for k,v in slot['probe'].items() if k not in ('duration_samples','window_start_counter')}:
        raise ValueError('sole passing cell mismatch')
    counter = slot['probe']['valid_start_counter']
    raw = next(r['raw_authority'] for r in metadata['rows'] if r['request_id']==slot['request_id'])
    nearby = sorted(selected, key=lambda p:abs(p['valid_start_counter']-counter))[:7]
    return dict(case=slot['case'], native_receiver_id=1, receiver=2, channel=7,
        processed_receiver_windows=len(selected), passing_windows=len(passed),
        near_gate_failed=sum(bool(p['candidates']) and not any(c['passed_fractional_margin_gate'] for c in p['candidates'])
                            and .0125<=max(c['fractional_margin'] for c in p['candidates'])<.025 for p in selected),
        no_exported_candidate=sum(not p['candidates'] for p in selected),
        sole_passing_slot=slot, sole_window_acquisition=raw['index']['acquisition'],
        physical_IQ_sha256=raw['index']['iq_sha256'], segment_manifest_sha256=raw['segment_manifest_sha256'],
        paired_receiver_probes=[p for p in doc['source']['probes'] if p['visit_index']==slot['probe']['visit_index']],
        nearby_same_cell_probes=sorted(nearby,key=lambda p:p['valid_start_counter']),
        raw_IQ_additional_reads=0, no_location_or_orbit_input=True,
        caveat='One passing window is measured; no continuous CH7 emitter/track is inferred from it.')


def main():
    panel = read(HERE/'panel.json')
    metadata = read(HERE/'raw_metadata.json')
    recorded = read(HERE/'recorded.json')
    controls = read(HERE/'controls.json')
    rate_controls = read(HERE/'clock_controls.json')
    if recorded['panel_sha256'] != sha(HERE/'panel.json'):
        raise ValueError('recorded panel changed')
    for path, digest in recorded['source_sha256'].items():
        if sha(path) != digest:
            raise ValueError('measurement source changed since recorded run')
    lookup = {s['request_id']:s for s in panel['slots']}
    rows = [r for w in recorded['rows'] for r in w.get('slots',[])]
    rows = sorted(rows,key=lambda r:list(lookup).index(r['request_id']))
    if len(rows) != 16 or any(r['status']!='complete' for r in rows):
        raise ValueError('all 16 primary slots must be represented, including failures')
    flat = []
    for r in rows:
        a = r['response']; q = r['received_symbol_rate']; s = lookup[r['request_id']]
        fits = q['models']['per_tone_received_rate']['fits']
        flat.append(dict(request_id=r['request_id'],case=r['case'],receiver=r['receiver'],channel=r['channel'],role=r['role'],
            original_candidate_rank=s['original_candidate']['candidate_rank'],visit_index=s['probe']['visit_index'],
            original_margin=s['original_candidate']['fractional_margin'],
            tone_held_SSE_improvement_percent=100*a['held_symbol_relative_SSE_improvement'],
            tone_descriptive_lower_percent=100*a['descriptive_frame_bootstrap_95_interval'][0],
            tone_descriptive_upper_percent=100*a['descriptive_frame_bootstrap_95_interval'][1],
            tone_in_sample_explained_gain_percent=100*(a['models']['per_tone']['in_sample_explained_fraction']-
                                                       a['models']['flat']['in_sample_explained_fraction']),
            correct_over_wrong_SSE_improvement_percent=100*a['correct_over_wrong_relative_SSE_improvement'],
            correct_over_wrong_lower_percent=100*a['correct_over_wrong_descriptive_frame_bootstrap_95_interval'][0],
            predictive_support=a['response_predictive_support'],
            received_rate_SSE_improvement_percent=100*q['held_symbol_relative_SSE_improvement'],
            received_rate_even_ppm=fits[0]['received_symbol_rate_ppm'],received_rate_odd_ppm=fits[1]['received_symbol_rate_ppm'],
            received_rate_boundary=any(f['boundary'] for f in fits),
            received_rate_converged=all(f['converged'] for f in fits)))
    with (HERE/'panel_results.csv').open('w') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    control_summary = {}
    for mode in ('channel','flat','wrong_sequence','noise'):
        selected = [r for r in controls['rows'] if r['mode']==mode]
        supported = sum(r['response_predictive_support'] for r in selected)
        control_summary[mode] = dict(n=len(selected), response_supported=supported,
            exact_binomial_95_interval=binomial_interval(supported,len(selected)),
            median_held_SSE_improvement_percent=float(np.median([100*r['held_symbol_relative_SSE_improvement'] for r in selected])))
    summary = dict(target_slots=16, complete_primary_slots=len(rows), complete_received_rate_slots=sum(r['received_symbol_rate']['status']=='complete' for r in rows),
        physical_windows_read=recorded['physical_window_reads'], full_paired_detector_calls=recorded['physical_detector_calls'],
        all_paired_candidate_parity_passed=all(p['all_passed'] for w in recorded['rows'] for p in w['paired_candidate_parity'].values()),
        physical_failures=recorded['full_set_failures'], primary_failures=[r['request_id'] for r in rows if r['status']!='complete'],
        received_rate_failures=[r['request_id'] for r in rows if r['received_symbol_rate']['status']!='complete'],
        recorded_job_seconds=recorded['seconds'], control_job_seconds=controls['seconds'],
        response_supported=sum(r['predictive_support'] for r in flat),
        response_held_SSE_positive=sum(r['tone_held_SSE_improvement_percent']>0 for r in flat),
        response_held_SSE_improvement_percent_range=[min(r['tone_held_SSE_improvement_percent']for r in flat),max(r['tone_held_SSE_improvement_percent']for r in flat)],
        response_median_held_SSE_improvement_percent_by_role={role:float(np.median([r['tone_held_SSE_improvement_percent']for r in flat if r['role']==role]))for role in ('passed','failed_near_gate')},
        all_in_sample_scores_increase=all(r['tone_in_sample_explained_gain_percent']>0 for r in flat),
        correct_sequence_predictive_lower_positive_by_role={role:sum(r['correct_over_wrong_lower_percent']>0 for r in flat if r['role']==role)for role in ('passed','failed_near_gate')},
        received_rate_positive_lower_interval=sum(r['received_symbol_rate']['descriptive_frame_bootstrap_95_interval'][0]>0 for r in rows),
        received_rate_boundary_slots=sum(r['received_rate_boundary']for r in flat),
        received_rate_nonconverged_slots=sum(not r['received_rate_converged']for r in flat),
        received_rate_maximum_held_SSE_improvement_percent=max(r['received_rate_SSE_improvement_percent']for r in flat),
        control_summary=control_summary, known_rate_control=rate_controls['rows'][0],
        conclusion='No predictive channel-response or received-rate correction qualifies on the frozen panel.',
        inference_and_admission_unchanged=True, raw_IQ_copied=False, new_RF_collection=False,
        original_full_window_acquisition_exposure=True, pipeline_GLRT_FPR_calibrated=False,
        absolute_CFO_or_localization_gain_established=False)
    write('summary.json',summary)
    write('sole_RX2_CH7_audit.json',sole_cell(panel,metadata))
    # Show loss improvement and parameter-estimation stability separately.
    labels=[r['request_id'].replace('DS24-00','').replace('failed_near_gate','failed')for r in flat]
    fig,axes=plt.subplots(1,2,figsize=(13,6.5),gridspec_kw={'width_ratios':[1.2,1]})
    y=np.arange(len(flat))
    for k,r in enumerate(flat):
        value=r['tone_held_SSE_improvement_percent'];lo=r['tone_descriptive_lower_percent'];hi=r['tone_descriptive_upper_percent']
        color='#268b8c' if r['role']=='passed' else '#bb7041'
        axes[0].errorbar(value,k,xerr=[[value-lo],[hi-value]],fmt='o',color=color,capsize=2)
    axes[0].axvline(0,color='black',lw=.8);axes[0].set(yticks=y,yticklabels=labels,xlabel='Held-symbol SSE improvement (%)',title='Per-tone versus flat response; fixed timing/CFO')
    axes[0].invert_yaxis()
    modes=list(control_summary)
    for k,mode in enumerate(modes):
        selected=[100*r['held_symbol_relative_SSE_improvement']for r in controls['rows']if r['mode']==mode]
        axes[1].scatter(np.full(len(selected),k)+np.linspace(-.13,.13,len(selected)),selected,s=15,color='#586e9c')
    axes[1].axhline(0,color='black',lw=.8);axes[1].set(xticks=range(4),xticklabels=['Independent\nchannels','Flat\nchannels','Wrong\nsequence','Noise'],ylabel='Held-symbol SSE improvement (%)',title='32 known-truth controls per type')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('Pilot response: no recorded slot has supported prediction improvement\nOriginal full-window acquisition saw held symbols; intervals are descriptive frame bootstraps',fontsize=12)
    fig.tight_layout();fig.savefig(HERE/'pilot_response.png',dpi=180);fig.savefig(HERE/'pilot_response.pdf');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for r in flat:
        color='#268b8c'if r['role']=='passed'else'#bb7041'
        marker='x'if r['received_rate_boundary']else'o'
        axes[0].scatter(r['received_rate_even_ppm'],r['received_rate_odd_ppm'],color=color,marker=marker)
    axes[0].plot([-100,100],[-100,100],'k--',lw=.8);axes[0].set(xlabel='Even-symbol fitted received rate (ppm)',ylabel='Odd-symbol fitted received rate (ppm)',title='Parity estimates; × = any frequency/rate boundary')
    for k,r in enumerate(rows):
        a=r['received_symbol_rate'];v=100*a['held_symbol_relative_SSE_improvement'];lo,hi=np.array(a['descriptive_frame_bootstrap_95_interval'])*100
        axes[1].errorbar(k,v,yerr=[[v-lo],[hi-v]],fmt='o',capsize=2,color='#268b8c'if r['role']=='passed'else'#bb7041')
    axes[1].axhline(0,color='black',lw=.8);axes[1].set(xlabel='Frozen slot index (panel order)',ylabel='Held-symbol SSE improvement (%)',title='Received rate versus zero rate; same guarded samples')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('Separate guarded received-symbol-rate diagnostic\nNo slot has positive lower prediction interval; received rate is not transmitter-only clock',fontsize=12)
    fig.tight_layout();fig.savefig(HERE/'received_rate.png',dpi=180);fig.savefig(HERE/'received_rate.pdf');plt.close(fig)
    source_paths=[REPO/'tools'/name for name in ('frequency_selective_pilot.py','local_pilot_refinement.py','probe_native_code_carrier.py','dsx01_pilot_clock.py')]
    source_paths += [REPO/'src/leo/analysis/starlink/templates.py',REPO/'tests/analysis/test_frequency_selective_pilot.py',REPO/'tests/analysis/test_dsx01_pilot_clock_tool.py']
    source_paths += [HERE/name for name in ('nominate.py','response.py','worker.py','clock_controls.py','test_response.py','test_clock_controls.py','report.py','PROTOCOL.md')]
    artifacts=[p for p in HERE.iterdir() if p.is_file() and p.name not in ('manifest.json','FINDINGS.md')]
    write('manifest.json',dict(source_sha256={str(p):sha(p)for p in source_paths},
        artifact_sha256={p.name:sha(p)for p in artifacts},
        tracking_source_sha256=panel['source_sha256'],historical_runtime_identity=recorded['runtime_identity'],
        historical_parity_helper_sha256=sha('/srv/bulk/leo/research/ds24-detector-response-r01/recorded/replay.py'),
        raw_IQ_artifacts_present=False))
    print(json.dumps({k:summary[k] for k in ('complete_primary_slots','physical_windows_read','all_paired_candidate_parity_passed','response_supported','received_rate_positive_lower_interval','received_rate_boundary_slots','response_held_SSE_improvement_percent_range')}))


if __name__=='__main__':
    main()
