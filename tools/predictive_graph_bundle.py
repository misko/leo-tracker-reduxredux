"""Reconstruct immutable, alias-aligned graph fragments as one predictive view."""
import copy
import hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read
from leo.analysis.research.retained_track_likelihood import PERIOD,whitening


def polynomial_pair(first,second):
    """Frozen-graph nomination only; this score cannot authorize association."""
    times=np.r_[first['times'],second['times']];values=np.r_[first['values'],second['values']]
    group=np.r_[np.zeros(len(first['times'])),np.ones(len(second['times']))]
    if not np.isfinite(np.r_[times,values]).all() or np.ptp(times)<=0:return None
    z=2*(times-times.min())/np.ptp(times)-1;offers=[]
    for degree in range(1,5):
        u=np.polynomial.legendre.legvander(z,degree);design=np.c_[u,group]
        if np.linalg.matrix_rank(design)!=design.shape[1]:continue
        offset=np.linalg.lstsq(design,values,rcond=None)[0][-1]
        lift=-int(round(offset/PERIOD));aligned=values+group*lift*PERIOD
        coef=np.linalg.lstsq(u,aligned,rcond=None)[0];residual=aligned-u@coef
        offers.append(dict(degree=degree,alias_lift=lift,RMS_hz=float(np.sqrt(np.mean(residual**2))),
            BIC=float(len(times)*np.log(max(150.**2,np.mean(residual**2)))+(degree+1)*np.log(len(times))),
            coefficients=coef,residual_hz=residual,times_s=times,aligned_values_hz=aligned))
    return min(offers,key=lambda r:r['BIC']) if offers else None


def append_bundle(scan,members,occupied,bundle_id):
    if len(members)<2:raise ValueError('a bundle requires multiple source fragments')
    indices=[m['track_index'] for m in members]
    if len(set(indices))!=len(indices):raise ValueError('repeated source fragment')
    source=[scan.tracks[i] for i in indices];lane=lambda t:(t['receiver'],t['channel'],t['rf_hz'])
    if len({lane(t) for t in source})!=1:raise ValueError('bundle mixes receiver, channel or RF lanes')
    ids=[o for t in source for o in t['observation_ids']]
    if len(set(ids))!=len(ids) or set(ids)&set(occupied):raise ValueError('bundle duplicates or owns existing observations')
    if any(type(m['alias_lift']) is not int for m in members):raise ValueError('integer alias lifts required')
    times=np.concatenate([t['times'] for t in source]);values=np.concatenate([np.asarray(t['values'])+m['alias_lift']*PERIOD for t,m in zip(source,members,strict=True)])
    order=np.argsort(times);times=times[order];values=values[order]
    if not np.isfinite(np.r_[times,values]).all() or np.any(np.diff(times)<=0):raise ValueError('bundle requires distinct finite increasing timestamps')
    basis=np.concatenate([scan.rx_basis[i] for i in indices])[order]
    labels=np.concatenate([np.full(len(t['times']),k) for k,t in enumerate(source)])[order]
    track=dict(source[0],key=source[0]['key']+'-BUNDLE-'+bundle_id,observation_ids=[ids[i] for i in order],
        times=times.copy(),values=values.copy(),start_s=float(times[0]),end_s=float(times[-1]),
        quality_status='provisional_frozen_graph_union_not_calibration',bundle_members=members,bundle_member_indices=labels)
    # Original fragment fits/pieces cannot describe the union and must not be reused.
    track.pop('pieces',None)
    changed=copy.copy(scan);changed.tracks=[*scan.tracks,track];changed.white=[*scan.white,whitening(times)]
    changed.rx_basis=[*scan.rx_basis,basis.copy()]
    return changed,len(scan.tracks)


def bundle_context(d,inventory,path,bundle_id):
    source=read(path);bundle=next(b for b in source['bundles'] if b['bundle_id']==bundle_id)
    if bundle['job']['job_id']!=inventory['job']['job_id']:raise ValueError('bundle belongs to another scan')
    for name,digest in bundle['source_hashes'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=digest:raise ValueError('bundle source changed')
    occupied=set(o for r in inventory['policy'].values() for o in r['proposed_associated_ids'])
    for p,_ in d['problems'].values():
        occupied.update(o for i,sl in zip(p.members,p.slices,strict=True)
            for o,k in zip(d['scan'].tracks[i]['observation_ids'],p.keep[sl],strict=True) if k)
    occupied.update(o for e in d['entries'] for o in e['observation_ids'])
    for m in bundle['members']:
        t=next(t for t in inventory['tracks'] if t['track_id']==m['track_id'])
        if t['track_index']!=m['track_index']:raise ValueError('bundle parent index changed')
    scan,index=append_bundle(d['scan'],bundle['members'],occupied,bundle_id);t=scan.tracks[index]
    target=dict(track_id=bundle_id,track_index=index,component=t['key'],observation_ids=t['observation_ids'],
        graph_bundle=True,bundle_source=str(path),bundle_source_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        members=bundle['members'],member_indices=t['bundle_member_indices'].tolist(),original_graph_unchanged=True,
        conditional_on_frozen_graph_and_bundle_selection=True)
    return dict(d,scan=scan),target


def validated_bundle_context(d,inventory,validation):
    pr=read(Path(validation)/'protocol.json');r=read(Path(validation)/'result.json');t=pr['target']
    if not r.get('graph_bundle') or pr['job']['job_id']!=inventory['job']['job_id']:raise ValueError('annotation is not this scan bundle')
    if r['annotation']['status']!='conditionally_supported_identity' or not r.get('bundle_member_checks',{}).get('passed'):
        raise ValueError('bundle lacks member-specific predictive support')
    path=Path(t['bundle_source'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=t['bundle_source_sha256']:raise ValueError('bundle discovery changed since annotation')
    changed,target=bundle_context(d,inventory,path,r['track_id'])
    for key in ('track_id','track_index','component','observation_ids','members','member_indices'):
        if target[key]!=t[key]:raise ValueError('bundle observations or alignment changed since annotation')
    return changed,target


def member_evidence(folds,target,norad,minimum_margin=10.):
    """Prevent a strong parent from hiding a poorly predicted bundle member.

    These comparisons still condition on the shared-bundle hypothesis. They
    are not an exhaustive comparison against independently labelled fragments.
    """
    votes=[];covered=set()
    for fold in folds:
        for member in target['members']:
            tid=member['track_id']
            for arm in ('c0','fitted_c'):
                rows=[(q['norad'],q['arms'][arm].get('bundle_member_scores',{}).get(tid)) for q in fold['proposals']]
                rows=[r for r in rows if r[1] is not None and r[1]['held_points']>=4]
                if not rows:continue
                rows.sort(key=lambda r:r[1]['negative_twice_log_density']);winner,score=rows[0]
                margin=rows[1][1]['negative_twice_log_density']-score['negative_twice_log_density'] if len(rows)>=2 else float('-inf')
                passed=bool(winner==norad and np.isfinite([margin,score['rms_hz']]).all() and margin>=minimum_margin and score['rms_hz']<=450)
                votes.append(dict(seed=fold['seed'],arm=arm,member=tid,norad=winner,margin=margin,rms_hz=score['rms_hz'],passed=passed))
                if passed:covered.add((tid,arm))
    expected={(m['track_id'],a) for m in target['members'] for a in ('c0','fitted_c')}
    return dict(passed=covered==expected and bool(votes) and all(v['passed'] for v in votes),votes=votes,
                missing_member_arms=sorted(expected-covered),conditional_on_shared_bundle_hypothesis=True,
                independent_fragment_identity_alternatives_tested=False)
