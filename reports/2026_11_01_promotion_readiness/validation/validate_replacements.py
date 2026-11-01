"""Bounded causal finalist diagnostics; never changes sealed acceptance.

All new data are written beneath this script. Evaluation truth is not read by
the added model. The inherited load_case replays saved ALGO06, including its
endpoint-reporting metadata, but none of that metadata selects these tests.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from scipy.special import logsumexp

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[2]
SEALED = REPO / 'reports/2026_11_01_reconsideration_population'
sys.path.insert(0, str(SEALED))
import evaluate as e
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon

CASES = {'DS26-0034': (53852, 59188), 'DS26-0044': (57414, 63186),
         'DS26-0066': (62025, 68047), 'DS26-0251': (56548, 58787)}
SEED = 20261111


def read(p):
    return json.loads(Path(p).read_text())


def clean(v):
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, np.ndarray):
        return clean(v.tolist())
    if isinstance(v, np.generic):
        return clean(v.item())
    if isinstance(v, float) and not np.isfinite(v):
        raise ValueError('Non-finite scientific output')
    return v


def write(p, v):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(clean(v), indent=2) + '\n')


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def partitions(t, groups, count=10):
    """Unique synchronized 5 s groups, one adjacent group guarded each side."""
    blocks = np.floor(t / 5).astype(int)
    available = np.unique(blocks)
    rng = np.random.default_rng(SEED)
    seen = set()
    splits = []
    for fold in range(count):
        for retry in range(10000):
            held = np.sort(rng.choice(available, max(1, round(.2 * len(available))), replace=False))
            key = tuple(held)
            if key in seen:
                continue
            test = np.isin(blocks, held)
            guard = np.unique(np.r_[held-1, held, held+1])
            train = ~np.isin(blocks, guard)
            if all(np.sum(train & (groups == g)) >= 5 and np.sum(test & (groups == g)) >= 2
                   for g in np.unique(groups)):
                break
        else:
            break
        seen.add(key)
        splits.append(dict(fold=fold, held_blocks=held, guard_blocks=guard,
                           train=train, test=test, retries=retry))
    return splits


def predict(raw, t, q, groups, rx, train, test, phase, model, phase_sd):
    """Normalized Gaussian phase-mixture predictive score with fixed priors.

    track_offset matches the sealed reduced predictive discrepancy model.
    receiver_offset instead ties the constant across a receiver's tracks.
    frozen_radio has only the common rate discrepancy, no new constant.
    """
    lift = raw.copy()
    aliases = []
    for g in np.unique(groups):
        m = (groups == g) & train
        alias = np.rint(-raw[:, m].mean(axis=1) / PERIOD).astype(int)
        lift[:, groups == g] += alias[:, None] * PERIOD
        aliases.append(alias)
    if model == 'track_offset':
        constants = [(groups == g) * 300. for g in np.unique(groups)]
    elif model == 'receiver_offset':
        constants = [(rx == r) * 300. for r in np.unique(rx)]
    elif model == 'frozen_radio':
        constants = []
    else:
        raise ValueError(model)
    design = np.column_stack(constants + [q * (t-150.) * .5]) / 150.
    u = design[train]
    precision = np.eye(u.shape[1]) + u.T @ u
    cov = np.linalg.inv(precision)
    beta = (lift[:, train] / 150.) @ u @ cov
    residual = lift / 150. - beta @ design.T
    train_cost = (np.sum(residual[:, train]**2, axis=1) + np.sum(beta**2, axis=1)
                  + np.linalg.slogdet(precision)[1] + train.sum()*np.log(2*np.pi*150**2))
    logprior = -.5 * (phase/phase_sd)**2
    logprior -= logsumexp(logprior)
    logpost = logprior - .5*train_cost
    training = -2*logsumexp(logpost)
    logpost -= logsumexp(logpost)
    v = design[test]
    a = residual[:, test]
    correction = np.linalg.inv(precision + v.T @ v)
    quad = np.sum(a*a, axis=1) - np.einsum('ij,jk,ik->i', a@v, correction, a@v)
    test_cost = (quad + np.linalg.slogdet(np.eye(v.shape[1])+cov@v.T@v)[1]
                 + test.sum()*np.log(2*np.pi*150**2))
    best = int(np.argmax(logpost))
    return dict(training_score=float(training), predictive_score=float(-2*logsumexp(logpost-.5*test_cost)),
                phase_map_s=float(phase[best]), phase_edge_mass=float(np.exp(logpost[np.abs(phase)>=29.6]).sum()),
                aliases=[int(x[best]) for x in aliases], coefficient=beta[best],
                held_rms_hz=float(np.sqrt(np.mean(residual[best,test]**2))*150.))


def receiver_shared_check(d,z,screen,old,new,ledger,*,models=('receiver_offset',),
                          phase_sds=(5.,),regional_offsets=((0.,0.),),
                          include_arrays=False):
    """Generic bounded finalist check using supplied causal context and screen.

    No case roster, storage writes, GPS, history mutation, or archive reads.
    Defaults execute only the primary receiver-shared guard. The diagnostic
    wrapper requests the extra nuisance/prior/regional cells explicitly.
    The caller owns baseline reconstruction and the full causal ledger.
    """
    began = time.monotonic()
    cutoff=z['scan_receipt']['cutoff_utc_ns']
    for n in screen['nominees']:
        element=ledger[str(n)]
        if not (0<=cutoff-element['element_epoch_utc_ns']<=int(72*3.6e12)
                and element['collected_utc_ns']<=cutoff):
            raise ValueError('finalist element must be verifiably scan-causal and within72h')
    nums, bank, failures = e.rec.bank_for({str(n): ledger[str(n)] for n in screen['nominees']}, z['scan_receipt']['origin_utc_ns'])
    base = d['problems']['fitted_c'][0]
    tracks = [(i, base.keep[sl]) for row,i,sl in zip(base.rows,base.members,base.slices)
              if row['candidate_norad']==old and base.keep[sl].any()]
    times = np.concatenate([d['scan'].tracks[i]['times'][use] for i,use in tracks])
    q = np.concatenate([np.full(use.sum(), d['scan'].tracks[i]['rf_hz']/11.5e9) for i,use in tracks])
    groups = np.concatenate([np.full(use.sum(),k) for k,(i,use) in enumerate(tracks)])
    receivers = np.concatenate([np.full(use.sum(), d['scan'].tracks[i]['receiver']) for i,use in tracks])
    native_ids = [o for i,use in tracks for o,keep in zip(d['scan'].tracks[i]['observation_ids'],use) if keep]
    assert len(native_ids)==len(set(native_ids))==len(times)
    parts = partitions(times, groups)
    phase = np.linspace(-30,30,151)
    rows = []
    regional = []
    arrays = dict(times_s=times, rf_scale=q, track_group=groups, receiver=receivers, observation_ids=np.asarray(native_ids))
    for arm in e.ARMS:
        saved = screen['cavity'][arm]
        p,_ = e.build(d,z,arm,np.asarray(saved['reference']),omit=old)
        point = np.asarray(saved['x'])
        state = p.state(point)
        values = np.concatenate([(tr['values']-p.scan.hardware(tr,state['beta'])
                                 -tr['rf_hz']/11.5e9*p.scan.rx_basis[i]@state['smooth'][tr['receiver']-1])[use]
                                for i,use in tracks for tr in [p.scan.tracks[i]]])
        arrays[arm+'_cavity_values_hz'] = values
        for offset in regional_offsets:
            at = np.clip(point + offset,-12.5,12.5)
            for j, num in enumerate(nums):
                bb = dict(time_s=bank['time_s'],
                          position_km=np.broadcast_to(bank['position_km'][j],(len(phase),*bank['position_km'][j].shape)),
                          velocity_km_s=np.broadcast_to(bank['velocity_km_s'][j],(len(phase),*bank['velocity_km_s'][j].shape)))
                ff, el = paired_phase_frequency(bb,np.tile(times,len(phase)),np.repeat(np.arange(len(phase)),len(times)),phase,*latlon(at))
                if np.min(el)<0:
                    regional.append(dict(arm=arm,offset_km=offset,norad=int(num),status='below_horizon'))
                    continue
                raw = values[None,:] - ff.reshape(len(phase),-1)*q
                if offset==(0.,0.):
                    arrays[f'{arm}_{num}_raw_hz'] = raw
                    for model in models:
                        for sd in phase_sds:
                            for split in parts:
                                fitted = predict(raw,times,q,groups,receivers,split['train'],split['test'],phase,model,sd)
                                rows.append(dict(arm=arm,norad=int(num),model=model,phase_sd_s=sd,
                                                 fold=split['fold'],held_points=int(split['test'].sum()),**fitted))
                # This is position profiling at frozen radio parameters, not
                # an independently refitted regional localization search.
                for model in models:
                    all_points = np.ones(len(times),bool)
                    regional.append(dict(arm=arm,offset_km=offset,position_km=at,norad=int(num),model=model,status='complete',
                                         **predict(raw,times,q,groups,receivers,all_points,all_points,phase,model,5.)))
    output=dict(old=old,new=new,seed=SEED,parts=parts,rows=rows,regional=regional,
          provenance={str(n):ledger[str(n)] for n in screen['nominees']},propagation_failures=failures,
          seconds=time.monotonic()-began,
          scope='Unique randomized whole-time-group finalist checks; full-data nomination and cavity fitting inherited. No GPS selection, later TLE, full catalogue exact search, or new acceptance. Regional cells freeze cavity radio calibration.')
    if include_arrays:output['arrays']=dict(phase_grid_s=phase,**arrays)
    return output


def run(case):
    old,new=CASES[case]
    folder=OUT/case
    folder.mkdir(parents=True,exist_ok=True)
    screen=read(SEALED/case/str(old)/'screen.json')
    result=read(SEALED/case/'result.json')
    selected=next(r for r in result['records']['combined'] if r['name']==f'{old}_to_{new}')
    e.rec.CATALOGUES=e.ROOTS[case[:4]]/'catalogues'
    d,z,replay=e.load_case(case)
    ledger=e.rec.causal_records(case,z)
    checks=receiver_shared_check(d,z,screen,old,new,ledger,
        models=('track_offset','receiver_offset','frozen_radio'),phase_sds=(5.,15.),
        regional_offsets=((0.,0.),(-5.,-5.),(-5.,5.),(5.,-5.),(5.,5.)),include_arrays=True)
    arrays=checks.pop('arrays')
    np.savez_compressed(folder/'native_predictive_arrays.npz',**arrays)
    base=d['problems']['fitted_c'][0]
    native_ids=arrays['observation_ids']
    owners = {}
    for arm in e.ARMS:
        fit = selected['pair'][arm]
        proposed = {o:int(tr['norad']) for tr in fit['tracks'] for o in tr['observation_ids']}
        expected = {o:int(row['candidate_norad']) for row,i,sl in zip(base.rows,base.members,base.slices)
                    for o,keep in zip(d['scan'].tracks[i]['observation_ids'],base.keep[sl]) if keep}
        target_ids = set(native_ids)
        mismatch = [o for o,owner in expected.items() if proposed.get(o)!=(new if o in target_ids else owner)]
        owners[arm] = dict(native_curved_points=len(expected),target_points=len(target_ids),unique_proposed_points=len(proposed),
                           lost_curved_ids=sorted(set(expected)-set(proposed)),unexpected_owners=mismatch,
                           destination_already_baseline_owned=new in set(z['baseline_owners'][arm].values()),
                           published_owner_count=len(z['baseline_owners'][arm]),
                           saved_lost_ids=len(fit['lost_ids']),saved_unexpected_reassigned_ids=len(fit['unexpected_reassigned_ids']),
                           saved_native_ids_sha256=fit['native_ids_sha256'])
    write(folder/'additional_checks.json',dict(case=case,ownership=owners,replay=replay,**checks))
    print(case,'complete',round(checks['seconds'],2),'s; unique partitions',len(checks['parts']),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('case',choices=CASES)
    run(parser.parse_args().case)
