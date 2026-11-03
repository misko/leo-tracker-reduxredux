"""Scan-wise, GPS/TLE-free interpolation-bias checks on saved GLRT contracts."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

from ds23_fft_bias_diagnostic import polynomial_press,interpolation_bias,native_correction,active_curvature
from run_algo01_ds23_sample import ROOT,read,write,sha

SOURCE=ROOT/'reports/2026_10_19_algo02_ds23_full'
OUT=ROOT/'reports/2026_10_20_ds23_fft_bias_diagnostic'
RESPONSE=ROOT/'reports/2026_10_19_native_fft_bias/result.json'
PHASES=np.arange(16)*500/16


def hashes():
    return {str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),ROOT/'tools/ds23_fft_bias_diagnostic.py')}


def prepare():
    OUT.mkdir(exist_ok=True);path=OUT/'protocol.json'
    if path.exists():
        d=read(path)
        if d['source_sha256']!=hashes():raise ValueError('frozen RF-bias diagnostic changed')
        return d
    manifest=read(ROOT/'reports/2026_10_18_ds23_post_ds22/manifest.json')
    cases=[];unavailable=[]
    for member in manifest['members']:
        case=member['dataset_label'];directory=SOURCE/case
        if all((directory/name).exists() for name in ('observations.json','tracks.json','tracking.json')):
            cases.append(case)
        else:unavailable.append(case)
    cases=sorted(cases);cut=int(.7*len(cases))
    d=dict(cases=cases,unavailable=sorted(unavailable),population=len(manifest['members']),workers=12,
        training_cases=cases[:cut],confirmation_cases=cases[cut:],
        partition='chronological dataset order 70/30; fixed before RF diagnostics',
        source_sha256=hashes(),response_sha256=sha(RESPONSE),
        hypothesis='fixed noiseless fine-acquisition magnitude-parabola response leaves a 500Hz periodic CFO bias',
        curvature='original piece degree>=2, span>=20s and affine residual RMS>=250Hz',
        minimum_piece_points=16,maximum_crossfit_prediction_sigma_hz=31.25,
        native_CFO_domain_hz=[1000,399000],minimum_noise_weight_sigma_hz=40,
        phase_controls_hz=PHASES,zero_phase_is_hypothesis_not_a_fitted_grid_origin=True,
        coefficient_is_descriptive_never_used_to_fit_a_correction=True,
        polynomial_degrees_and_membership_conditioned_on_original_full_RF_graph=True,
        no_GPS_TLE_or_satellite_fit_used=True,no_new_RF_or_raw_IQ_reads=True,
        actual_capture_binary_and_search_grid_identity_not_certified=True,
        no_measurement_correction_or_position_update_applied=True)
    write(path,d);return d


def run(case):
    protocol=prepare();path=OUT/(case+'.json')
    if path.exists():return dict(case=case,cached=True)
    document=read(SOURCE/case/'tracking.json');source=document.get('source',document)
    fs=source['sample_rate_hz'];observations={r['observation_id']:r for r in read(SOURCE/case/'observations.json')}
    edges={}
    for probe in source['probes']:
        edges.setdefault((probe['receiver_id']+1,probe['channel']),set()).add(probe['edge'])
    if any(len(v)!=1 for v in edges.values()):raise ValueError('multiple edge references in one RF lane')
    curves=read(RESPONSE)['response_curves'];pieces=[];seen=set();counts=dict(total_pieces=0,curved_pieces=0,eligible_points=0)
    for track in read(SOURCE/case/'tracks.json'):
        lookup={idx:k for k,idx in enumerate(track['indices'])}
        edge=next(iter(edges[track['receiver'],track['channel']]))
        key=f'{fs}/{edge}'
        if key not in curves:raise ValueError('no fixed template response for sample rate/edge')
        response=curves[key]
        for number,piece in enumerate(track['pieces']):
            counts['total_pieces']+=1;degree=piece['degree']
            indices=[lookup[i] for i in piece['indices']]
            ids=[track['observation_ids'][k] for k in indices]
            if any(oid in seen for oid in ids):raise ValueError('original graph pieces overlap canonical observations')
            seen.update(ids)
            t=np.asarray(track['times'])[indices];y=np.asarray(track['values'])[indices]
            if degree<2 or len(t)<max(16,3*(degree+1)) or not active_curvature(t,y):continue
            counts['curved_pieces']+=1
            native=np.array([observations[oid]['measured_cfo_hz'] for oid in ids])
            period=1/4.4e-6
            if np.max(abs((native-y+period/2)%period-period/2))>1e-6:raise ValueError('graph/native CFO alias differs')
            press=polynomial_press(t,y,degree)
            native_prediction=press['prediction']+(native-y)
            use=(press['prediction_sigma_hz']<=31.25)&(abs(native)>1000)&(abs(native)<399000)
            if not use.any():continue
            corrected=y+np.where((abs(native)>1000)&(abs(native)<399000),native_correction(native,response),0.)
            after=polynomial_press(t,corrected,degree)
            residual=press['press_residual'][use]
            sigma=np.maximum(40.,press['training_sigma_hz'][use]);weight=(1-press['leverage'][use])/sigma**2
            biases=np.array([interpolation_bias(native_prediction[use],response,phase) for phase in PHASES])
            information=np.sum(weight*biases*biases,axis=1);cross=np.sum(weight*biases*residual,axis=1)
            counts['eligible_points']+=int(use.sum())
            pieces.append(dict(component=track['key'],piece=number,receiver=track['receiver'],channel=track['channel'],
                edge=edge,observations=int(use.sum()),
                bias_information=information,bias_residual_cross=cross,
                fixed_forward_bias_gain=2*cross-information,
                original_PRESS_energy=float(np.sum(weight*residual**2)),
                corrected_PRESS_energy=float(np.sum(weight*after['press_residual'][use]**2)),
                original_PRESS_sum_squares=float(np.sum(residual**2)),
                corrected_PRESS_sum_squares=float(np.sum(after['press_residual'][use]**2)),
                held_native_prediction_hz=native_prediction[use],held_residual_hz=residual,
                held_prediction_sigma_hz=press['prediction_sigma_hz'][use]))
    write(path,dict(case=case,format='fast' if 'source' in document else 'adaptive',sample_rate_hz=fs,
        pieces=pieces,counts=counts,no_GPS_TLE_or_new_measurements=True,
        input_sha256={name:sha(SOURCE/case/name) for name in ('observations.json','tracks.json','tracking.json')}))
    return dict(case=case,**counts)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case');args=parser.parse_args();protocol=prepare()
    if args.case:print(run(args.case),flush=True)
    else:
        receipts=[]
        with ProcessPoolExecutor(max_workers=protocol['workers']) as pool:
            futures={pool.submit(run,c):c for c in protocol['cases']}
            for f in as_completed(futures):
                try:receipts.append(f.result())
                except Exception as exc:receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/'progress.json',dict(completed=len(receipts),total=len(futures),receipts=receipts))
        write(OUT/'execution.json',dict(all_terminal=True,receipts=receipts))
