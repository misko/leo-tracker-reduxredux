"""Channel, receiver, and stored-GLRT metadata controls for the residual audit."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from residual_trend_audit import (
    ROOT, OUTPUT, CARRIER, SESSIONS, ExactOrbit, channel_design, cross_validate,
    file_digest, final_tracks, load_archived_session, polynomial, profile_minimum,
    read_membership_rows, regress, rms, serializable, stats, time_folds,
)


def fit_timing_channels(orbit, values, design, train=None):
    train = np.ones(len(values), bool) if train is None else train
    if np.linalg.matrix_rank(design[train]) < design.shape[1]:
        return None, None

    def evaluate(delta, details=False):
        coef, bias, _ = regress(design, values - orbit.change(delta), train)
        predicted = orbit.change(delta) + bias
        return (coef, predicted) if details else float(np.mean((values[train] - predicted[train]) ** 2))

    delta = profile_minimum(evaluate)
    coef, prediction = evaluate(delta, True)
    return {"extra_timing_s": delta, "channel_biases_hz": coef,
            "rms_hz": rms(values[train] - prediction[train]), "boundary_hit": abs(delta) >= .9999}, prediction


def matched_receiver_rows(times, channels, left, right, tolerance=.75):
    """Greedy nearest-time, same-channel, one-to-one pairs across receivers."""
    candidates = []
    for a in left:
        for b in right[channels[right] == channels[a]]:
            dt = abs(times[a] - times[b])
            if dt <= tolerance:
                candidates.append((float(dt), int(a), int(b)))
    used_left, used_right, pairs = set(), set(), []
    for dt, a, b in sorted(candidates):
        if a not in used_left and b not in used_right:
            pairs.append((a, b, dt)); used_left.add(a); used_right.add(b)
    return sorted(pairs, key=lambda pair: times[pair[0]])


def partial_correlation(values, feature, design):
    values = np.asarray(values, float)
    feature = np.asarray(feature, float)
    if np.any(~np.isfinite(feature)):
        return None
    _, yhat, _ = regress(design, values)
    _, fhat, _ = regress(design, feature)
    y, f = values - yhat, feature - fhat
    denom = np.linalg.norm(y) * np.linalg.norm(f)
    return float(y @ f / denom) if denom > 1e-10 else None


def run():
    destination=OUTPUT/"followup.json"
    if destination.exists(): raise FileExistsError(destination)
    source=OUTPUT/"receipt.json";main=json.loads(source.read_text())
    hashes={str(source):file_digest(source),str(Path(__file__)):file_digest(__file__)}
    membership_path=ROOT/"orbit-backfill-prototype/group-summed-orbit-backfill-memberships.csv"
    mem=read_membership_rows(membership_path)
    results,cross_rx=[],[]
    for session,label in zip(SESSIONS,"AB",strict=True):
        arch,_,_,_=load_archived_session(session);arrays={k:arch[k] for k in arch.files};arch.close()
        bank_path=ROOT/"all-visible-bank"/session/"expanded.npz"
        if file_digest(bank_path)!=main['source_hashes'][str(bank_path)]:raise ValueError('bank changed')
        with np.load(bank_path) as b:bank={k:b[k] for k in ('nodes','numbers','position','velocity')}
        manifest_path=ROOT/"scans"/session/"bundle.json"
        if file_digest(manifest_path)!=main['source_hashes'][str(manifest_path)]:raise ValueError('manifest changed')
        manifest=json.loads(manifest_path.read_text());families=manifest['alias_grouping']['families']
        tracks=final_tracks(mem,arrays,label)
        for tr in tracks:
            rr=tr['rows'];x=arrays['times_s'][rr];ch=arrays['channel'][rr];col=tr['column'];y=arrays['residual_hz'][rr,col]
            m=next(r for r in main['tracks'] if r['scan']==label and r['catalog_number']==tr['catalog_number'] and r['receiver']==tr['receiver'])
            orbit=ExactOrbit(arrays,bank,col,rr);design=channel_design(x,ch)
            fit,pred=fit_timing_channels(orbit,y,design)
            errors=[];folds=[]
            for train,test in time_folds(x):
                f,yp=fit_timing_channels(orbit,y,design,train)
                if f is None:break
                errors.extend(y[test]-yp[test]);folds.append({**f,'test_rms_hz':rms(y[test]-yp[test])})
            fit['cv']={'available':len(errors)==len(y),'rms_hz':rms(errors) if len(errors)==len(y) else None,'folds':folds}
            # Repeat channel controls on channels with at least 15 groups and 40% time coverage.
            levels=[c for c in np.unique(ch) if sum(ch==c)>=15 and np.ptp(x[ch==c])>=.4*np.ptp(x)]
            keep=np.isin(ch,levels);kx,ky,kc=x[keep],y[keep],ch[keep]
            stable={'channels':levels,'count':int(keep.sum()),'models':{}}
            if len(ky)>=20:
                for order in (0,1,2):
                    dd=channel_design(kx,kc,order);coef,yp,_=regress(dd,ky)
                    stable['models'][str(order)]={'coefficients':coef,'rms_hz':rms(ky-yp),'cv':cross_validate(dd,ky,time_folds(kx))}
            feature_records=[families[r]['representative_row'] for r in rr]
            features={key:np.array([float(f[key]) for f in feature_records]) for key in
                      ('fractional_margin','native_residual_cfo_hz','acquired_cfo_hz','fractional_epoch_offset_samples')}
            features['candidate_rank']=np.array([float(f['candidate_rank']) for f in feature_records])
            margin=features['fractional_margin'];strong=margin>=np.median(margin)
            strength={'high_margin':stats(x[strong],y[strong]),'low_margin':stats(x[~strong],y[~strong]),
                'partial_correlations_after_channel_quadratic':{k:partial_correlation(y,v,channel_design(x,ch,2)) for k,v in features.items()},
                'native_residual_zero_count':int(np.sum(features['native_residual_cfo_hz']==0)),
                'native_residual_value_counts':{str(k):int(n) for k,n in zip(*np.unique(features['native_residual_cfo_hz'],return_counts=True))}}
            results.append({'scan':label,'catalog_number':tr['catalog_number'],'receiver':tr['receiver'],
                            'timing_channel_bias':fit,'well_covered_channel_subset':stable,'stored_estimator_metadata':strength})
            print(label,tr['catalog_number'],tr['receiver'],'timing+channels RMS',fit['rms_hz'],'CV',fit['cv']['rms_hz'],flush=True)
        for number in sorted({t['catalog_number'] for t in tracks}):
            both=[t for t in tracks if t['catalog_number']==number]
            if len(both)!=2:continue
            left=next(t for t in both if t['receiver']==0);right=next(t for t in both if t['receiver']==1)
            pairs=matched_receiver_rows(arrays['times_s'],arrays['channel'],left['rows'],right['rows'])
            if len(pairs)<10:continue
            lr=np.array([p[0] for p in pairs]);rr=np.array([p[1] for p in pairs]);col=left['column']
            x=(arrays['times_s'][lr]+arrays['times_s'][rr])/2;ch=arrays['channel'][lr]
            # These are normalized residuals of the same satellite/RF; native conversion is identical within each pair.
            factor=arrays['rf_hz'][lr]/CARRIER
            a=arrays['residual_hz'][lr,col]*factor;b=arrays['residual_hz'][rr,col]*factor
            dd=channel_design(x,ch,2);co,_,_=regress(dd,a-b)
            cross_rx.append({'scan':label,'catalog_number':number,'pair_count':len(pairs),
                'max_time_mismatch_s':max(p[2] for p in pairs),'rx0_native':stats(x,a),'rx1_native':stats(x,b),
                'difference_native':stats(x,a-b),'difference_channel_quadratic_coefficients':co,
                'channels':np.unique(ch)})
    for p,h in main['source_hashes'].items():
        if file_digest(p)!=h:raise ValueError(f'source changed: {p}')
    result={'source_hashes':hashes,'tracks':results,'same_satellite_cross_receiver':cross_rx,
        'scope':'Extra diagnostic fits only. Channel-bias timing uses the same ±1 s bound and purged temporal folds. Sparse-channel exclusion changes cohort and is reported explicitly. Receiver pairing is nearest in same channel, <=0.75 s, no row reused.'}
    destination.write_text(json.dumps(serializable(result),indent=2,allow_nan=False)+'\n')


if __name__=='__main__':run()
