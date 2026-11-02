"""Frozen ALGO07 science; source provenance is recorded in origin_manifest.json."""
import time
import numpy as np
from scipy.special import logsumexp
from . import engine as e
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon
SEED=20261111


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
