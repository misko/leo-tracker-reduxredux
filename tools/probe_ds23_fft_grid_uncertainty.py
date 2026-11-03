"""Matched follow-up: fixed CFO correction with its derived noise Jacobian.

The correction/noise law has no adjustable coefficient. The 20+20 cohorts,
observations, satellite labels, priors and optimization schedule are reused.
This is a declared follow-up after the value-only policy failed confirmation.
"""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

import probe_ds23_fft_grid_position as engine
from ds23_fft_grid_origin import search_origin
from ds23_fft_noise_propagation import inverse_noise_scale
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_fft_grid_uncertainty'
PREVIOUS=engine.OUT
original_hashes=engine.hashes
original_prepare=engine.prepare
original_correct=engine.corrected_scan


def hashes():
    return dict(original_hashes(),**{str(p.relative_to(ROOT)):sha(p) for p in
        (Path(__file__),ROOT/'tools/ds23_fft_noise_propagation.py')})


def prepare():
    p=original_prepare()
    if 'inverse_noise_Jacobian' not in p:
        previous=read(PREVIOUS/'protocol.json')
        if any(p[k]!=previous[k] for k in ('development_cases','confirmation_cases','qualified_groups')):
            raise ValueError('follow-up cohorts or RF qualification changed')
        p.update(inverse_noise_Jacobian='sigma_corrected = sigma_original * d inverse_CFO / d native_CFO',
            approximation='first order delta method; not an exact non-Gaussian forward likelihood',
            uncertainty_law_has_no_fitted_parameter=True,
            labels_aliases_masks_weights_noise_priors_and_search_budgets_unchanged=False,
            labels_aliases_masks_family_powers_priors_and_search_budgets_unchanged=True,
            original_noise_law_not_refit_only_deterministic_coordinate_transform=True,
            follows_value_only_confirmation_failure=True,
            new_confirmation_is_reused_experiment_cohort_not_a_third_untouched_sample=True,
            previous_protocol_sha256=sha(PREVIOUS/'protocol.json'))
        write(OUT/'protocol.json',p)
    return p


def corrected_scan(scan,case,protocol):
    changed,receipt=original_correct(scan,case,protocol)
    tracking=read(engine.SOURCE/case/'tracking.json');source=tracking.get('source',tracking)
    edges={(r['receiver_id']+1,r['channel']):r['edge'] for r in source['probes']}
    observations={r['observation_id']:r for r in read(engine.SOURCE/case/'observations.json')}
    responses=read(engine.RESPONSE)['response_curves'];fs=source['sample_rate_hz']
    kind='fast' if 'source' in tracking else 'adaptive'
    changed.fixed_window_noise=copy.deepcopy(scan.fixed_window_noise)
    meta=changed.fixed_window_noise;by_id=meta['per_observation_noise_sigma_hz']
    if meta['extra_parameter_BIC_gain']<=0:
        for oid in by_id:
            by_id[oid]=scan.radio_sigma_hz
    scales=[];seen=set()
    for track in scan.tracks:
        edge=edges[track['receiver'],track['channel']]
        if f'{kind}/{fs}/{edge}' not in protocol['qualified_groups']:
            continue
        for oid in track['observation_ids']:
            if oid in seen:
                raise ValueError('duplicate original observation in noise propagation')
            seen.add(oid);f=observations[oid]['measured_cfo_hz']
            if not 1000<abs(f)<399000:
                continue
            scale=float(inverse_noise_scale(f,responses[f'{fs}/{edge}'],search_origin(fs)))
            by_id[oid]*=scale;scales.append(scale)
    # This existing explicit per-ID override activates the propagated law;
    # no heteroscedastic feature is learned from satellite residuals.
    meta['extra_parameter_BIC_gain']=1.
    meta['research_override']='fixed inverse-measurement Jacobian, not a BIC-selected new noise feature'
    receipt.update(noise_scale_min=float(min(scales)),noise_scale_max=float(max(scales)),
                   noise_transformation_is_first_order=True)
    return changed,receipt


def bind():
    engine.OUT=OUT;engine.hashes=hashes;engine.prepare=prepare;engine.corrected_scan=corrected_scan


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('prepare','development','confirmation','evaluate'),required=True)
    args=parser.parse_args();bind();protocol=prepare()
    if args.stage=='evaluate':
        import evaluate_ds23_fft_grid_position as report
        report.OUT=OUT;report.prepare=prepare;report.main()
    elif args.stage!='prepare':
        receipts=[];cases=protocol[args.stage+'_cases']
        with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
            futures={pool.submit(engine.run,c):c for c in cases}
            for f in as_completed(futures):
                try:
                    receipts.append(f.result())
                except Exception as exc:
                    receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(args.stage+'_progress.json'),dict(receipts=receipts,completed=len(receipts),total=len(cases)))
        write(OUT/(args.stage+'_execution.json'),dict(all_terminal=True,receipts=receipts))
        print('Terminal',len(receipts),'errors',sum('error' in r for r in receipts),flush=True)
