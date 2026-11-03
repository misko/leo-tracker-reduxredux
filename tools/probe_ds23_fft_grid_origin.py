"""RF-only source-derived grid-origin correction, preserving the earlier null test."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from ds23_fft_bias_diagnostic import polynomial_press, interpolation_bias, active_curvature
from ds23_fft_grid_origin import search_origin, correction
from probe_ds23_fft_bias_diagnostic import SOURCE, RESPONSE, OUT as OLD, PHASES
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_20_ds23_fft_grid_origin'


def prepare():
    OUT.mkdir(exist_ok=True)
    source = {str(p.relative_to(ROOT)):sha(p) for p in
              (Path(__file__), ROOT/'tools/ds23_fft_grid_origin.py',
               ROOT/'tools/ds23_fft_bias_diagnostic.py')}
    path = OUT/'protocol.json'
    if path.exists():
        p = read(path)
        if p['source_sha256'] != source:
            raise ValueError('frozen origin experiment changed')
        return p
    p = dict(read(OLD/'protocol.json'), source_sha256=source,
        original_zero_origin_protocol_sha256=sha(OLD/'protocol.json'),
        prior_RF_phase_controls_informed_this_followup=True,
        chronological_partitions_are_RF_reuse_not_untouched_confirmation=True,
        grid_origin='(center-min(800000,center-820312.5+fs/2,fs/2-center-820312.5)) modulo 500',
        nominal_center_hz=0., origins_hz={'2500000':312.5,'10000000':0.},
        origin_not_fitted_to_GPS_or_position_or_free_RF_phase=True,
        representative_capture_metadata_matches_zero_center=True,
        every_historical_acquisition_binary_not_certified=True,
        no_measurement_correction_or_position_update_applied=True)
    write(path, p)
    rule = dict(read(OLD/'qualification_protocol.json'),
        frozen_before_new_fixed_inverse_RF_results=True,
        zero_phase_refers_to_source_derived_origin=True,
        RF_partitions_reused_from_discovery_not_independent_validation=True)
    write(OUT/'qualification_protocol.json', rule)
    return p


def run(case):
    prepare(); path = OUT/(case+'.json')
    if path.exists():
        return dict(case=case,cached=True)
    document = read(SOURCE/case/'tracking.json'); source = document.get('source', document)
    fs = source['sample_rate_hz']; origin = search_origin(fs)
    observations = {r['observation_id']:r for r in read(SOURCE/case/'observations.json')}
    edges = {}
    for probe in source['probes']:
        lane = (probe['receiver_id']+1, probe['channel'])
        if lane in edges and edges[lane] != probe['edge']:
            raise ValueError('multiple edges in RF lane')
        edges[lane] = probe['edge']
    curves = read(RESPONSE)['response_curves']; pieces = []; seen = set()
    counts = dict(total_pieces=0, curved_pieces=0, eligible_points=0)
    for track in read(SOURCE/case/'tracks.json'):
        lookup = {i:k for k,i in enumerate(track['indices'])}
        edge = edges[track['receiver'],track['channel']]; response = curves[f'{fs}/{edge}']
        for number,piece in enumerate(track['pieces']):
            counts['total_pieces'] += 1; degree = piece['degree']
            indices = [lookup[i] for i in piece['indices']]
            ids = [track['observation_ids'][k] for k in indices]
            if seen.intersection(ids):
                raise ValueError('overlapping canonical points')
            seen.update(ids)
            t = np.asarray(track['times'])[indices]; y = np.asarray(track['values'])[indices]
            if degree<2 or len(t)<max(16,3*(degree+1)) or not active_curvature(t,y):
                continue
            counts['curved_pieces'] += 1
            native = np.asarray([observations[o]['measured_cfo_hz'] for o in ids])
            period = 1/4.4e-6
            if np.max(abs((native-y+period/2)%period-period/2)) > 1e-6:
                raise ValueError('native/graph alias mismatch')
            before = polynomial_press(t,y,degree)
            use = (before['prediction_sigma_hz']<=31.25)&(abs(native)>1000)&(abs(native)<399000)
            if not use.any():
                continue
            delta = np.where((abs(native)>1000)&(abs(native)<399000),correction(native,response,origin),0.)
            after = polynomial_press(t,y+delta,degree)
            prediction = before['prediction']+(native-y)
            residual = before['press_residual'][use]
            weight = (1-before['leverage'][use])/np.maximum(40.,before['training_sigma_hz'][use])**2
            biases = np.array([interpolation_bias(prediction[use],response,origin+phase) for phase in PHASES])
            info = np.sum(weight*biases**2,axis=1); cross = np.sum(weight*biases*residual,axis=1)
            counts['eligible_points'] += int(use.sum())
            pieces.append(dict(component=track['key'],piece=number,receiver=track['receiver'],channel=track['channel'],
                edge=edge,observations=int(use.sum()),source_derived_origin_hz=origin,
                bias_information=info,bias_residual_cross=cross,fixed_forward_bias_gain=2*cross-info,
                original_PRESS_energy=float(np.sum(weight*residual**2)),
                corrected_PRESS_energy=float(np.sum(weight*after['press_residual'][use]**2)),
                original_PRESS_sum_squares=float(np.sum(residual**2)),
                corrected_PRESS_sum_squares=float(np.sum(after['press_residual'][use]**2))))
    write(path,dict(case=case,format='fast' if 'source' in document else 'adaptive',sample_rate_hz=fs,
        pieces=pieces,counts=counts,no_GPS_TLE_or_new_measurements=True,
        input_sha256={name:sha(SOURCE/case/name) for name in ('observations.json','tracks.json','tracking.json')}))
    return dict(case=case,**counts)


def evaluate():
    import evaluate_ds23_fft_bias_diagnostic as report
    report.OUT = OUT
    report.main()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--stage',choices=('run','evaluate'),required=True)
    args = parser.parse_args(); protocol = prepare()
    if args.stage == 'evaluate':
        evaluate()
    else:
        receipts = []
        with ProcessPoolExecutor(max_workers=12) as pool:
            futures = {pool.submit(run,c):c for c in protocol['cases']}
            for f in as_completed(futures):
                try:
                    receipts.append(f.result())
                except Exception as exc:
                    receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/'progress.json',dict(completed=len(receipts),total=len(futures),receipts=receipts))
        write(OUT/'execution.json',dict(all_terminal=True,receipts=receipts))
        print('Terminal',len(receipts),'errors',sum('error' in r for r in receipts),flush=True)
