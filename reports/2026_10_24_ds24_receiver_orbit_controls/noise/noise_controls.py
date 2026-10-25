"""GPS-blind grouped validation of receiver-specific graph CFO noise.

The graph is a frozen input, not validated by this experiment. Whole nominated
families (all owners) are grouped across folds; unmatched tracks each form one
group. Test scores use full polynomial residual contrasts, not independent
leverage-adjusted point residuals. The latter are training samples only, as in
the existing radio-noise estimator. This validates a conditional noise proxy,
not externally known measurement error or satellite identities.
"""
from pathlib import Path
import csv, hashlib, json
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from scipy.linalg import solve_triangular
from localize_merged_track_catalogue import raw_curvature
from prototype_dsx01_glrt_weighting import fit_variance

HERE=Path(__file__).resolve().parent
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
OLD=Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
SEED=20261025

def encode(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    raise TypeError(type(x).__name__)

def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,default=encode,indent=2)+'\n')

def learn(pieces):
    m=np.concatenate([p['margin'] for p in pieces]);s=np.concatenate([p['squares'] for p in pieces])
    constant=float(np.clip(s.mean(),40**2,600**2))
    floor,strength=map(float,fit_variance(m,s))
    proposed=np.clip(floor+strength/m,40**2,600**2)
    gain=float(np.sum(np.log(constant)+s/constant-np.log(proposed)-s/proposed)-np.log(len(s)))
    return dict(constant_variance=constant,floor=floor,strength=strength,
                margin_selected=bool(gain>0),training_BIC_gain=gain,training_points=len(s),training_pieces=len(pieces))

def variance(law,margins):
    m=np.asarray(margins)
    if law['margin_selected']:return np.clip(law['floor']+law['strength']/m,40**2,600**2)
    return np.full(m.shape,law['constant_variance'])

def contrast_loss(piece,law):
    q=piece['contrast'];v=variance(law,piece['margin']);z=piece['contrast_values']
    covariance=q.T@(v[:,None]*q)
    root=np.linalg.cholesky(covariance)
    white=solve_triangular(root,z,lower=True)
    return float(white@white+2*np.log(np.diag(root)).sum())

def grouping(case):
    saved=json.loads((SOURCE/'family_cavity/position'/f'{case}.json').read_text())
    selected=saved['selected'] if saved['accepted'] else None
    node=selected['node'] if selected else saved['baseline_node']
    entries=selected['entries'] if selected else saved['baseline_entries']
    groups={r['component']:'family_'+str(r['candidate_norad']) for r in node['seed']['rows']}
    for e in entries:groups[e['component']]='family_'+str(e['norad'])
    return groups

def collect(case):
    tracks=json.loads((SOURCE/case/'tracks.json').read_text())
    observations=json.loads((SOURCE/case/'observations.json').read_text())
    scores={o['observation_id']:o['fractional_margin'] for o in observations};groups=grouping(case)
    pieces=[];seen=set()
    for track in tracks:
        t,y=np.array(track['times']),np.array(track['values'])
        if not raw_curvature(dict(times=t,values=y)):continue
        for k,piece in enumerate(track['pieces']):
            # Match the existing learner's frozen time-span membership exactly.
            use=(t>=piece['start_s'])&(t<=piece['end_s']);degree=piece['degree']
            if use.sum()<2*(degree+1)+3:continue
            ids=[oid for oid,yes in zip(track['observation_ids'],use,strict=True) if yes]
            if seen.intersection(ids):raise ValueError('overlapping graph pieces require grouped covariance')
            seen.update(ids)
            times,values=t[use],y[use];z=(times-times.mean())/max(1.,float(np.ptp(times)))
            design=np.vander(z,degree+1,increasing=True);q=np.linalg.qr(design,mode='complete')[0]
            fitted=q[:,:degree+1];contrast=q[:,degree+1:]
            residual=values-fitted@(fitted.T@values);lev=np.sum(fitted**2,axis=1)
            pieces.append(dict(key=track['key']+f'/piece{k}',group=groups.get(track['key'],'track_'+track['key']),
                receiver=track['receiver'],channel=track['channel'],ids=ids,margin=np.array([scores[o] for o in ids]),
                squares=residual**2/(1-lev),contrast=contrast,contrast_values=contrast.T@values,
                degree=degree))
    return pieces,observations

def one(case):
    pieces,observations=collect(case);groups=sorted({p['group'] for p in pieces})
    rng=np.random.default_rng(np.random.SeedSequence([SEED,int(case[-4:])]))
    order=rng.permutation(len(groups));folds={groups[j]:int(i%3) for i,j in enumerate(order)}
    checks=[];valid=True
    for f in range(3):
        train=[p for p in pieces if folds[p['group']]!=f];test=[p for p in pieces if folds[p['group']]==f]
        training_ids={o for p in train for o in p['ids']};test_ids={o for p in test for o in p['ids']}
        assert not(training_ids&test_ids)
        sufficient=bool(test and all(sum(p['receiver']==rx for p in train)>=3 for rx in (1,2)))
        if not sufficient:valid=False;checks.append(dict(fold=f,sufficient=False));continue
        pooled=learn(train);rxlaws={rx:learn([p for p in train if p['receiver']==rx]) for rx in (1,2)}
        per_piece=[dict(key=p['key'],group=p['group'],receiver=p['receiver'],
                       contrast_degrees=len(p['contrast_values']),pooled_loss=contrast_loss(p,pooled),
                       receiver_loss=contrast_loss(p,rxlaws[p['receiver']])) for p in test]
        gain=sum(p['pooled_loss']-p['receiver_loss'] for p in per_piece)
        checks.append(dict(fold=f,sufficient=True,training_groups=sorted({p['group'] for p in train}),
                           test_groups=sorted({p['group'] for p in test}),training_points=len(training_ids),test_points=len(test_ids),
                           pooled_law=pooled,receiver_laws=rxlaws,test_gain=gain,test_pieces=per_piece))
    gains=[r['test_gain'] for r in checks if r['sufficient']]
    qualified=bool(valid and sum(gains)>2*np.log(2) and sum(g>0 for g in gains)>=2)
    laws={rx:learn([p for p in pieces if p['receiver']==rx]) for rx in (1,2)}
    all_law=learn(pieces)
    noise={o['observation_id']:float(np.sqrt(variance(laws[o['receiver']],np.array([o['fractional_margin']]))[0])) for o in observations}
    # The adapter must force use of the supplied per-ID values. This is a selector
    # flag in an in-memory experiment, not a newly measured BIC or contract edit.
    result=dict(case=case,qualified=qualified,qualification_rule='sum held-group contrast-density gain >2log2 and at least2of3fold gains positive',
        group_seed=SEED,folds=folds,checks=checks,heldout_gain=sum(gains),receiver_laws=laws,pooled_full_law=all_law,
        per_observation_noise_sigma_hz=noise,noise_adapter_use_per_ID=True,unchanged_observation_IDs=True,
        original_graph_and_nomination_groups_frozen_not_independently_validated=True,
        no_GPS_or_position_or_orbit_predictions_in_variance_estimation=True)
    write(HERE/'results'/f'{case}.json',result)
    return dict(case=case,qualified=qualified,heldout_gain=sum(gains),fold_gains=gains,groups=len(groups),pieces=len(pieces))

def main():
    cases=sorted({r['case'] for r in csv.DictReader((OLD/'tables/positions.csv').open()) if r['status']=='localized'})
    write(HERE/'protocol.json',dict(cases=cases,seed=SEED,folds=3,groups='whole nominated family across RX/channel; unmatched whole graph track',
        models=['original pooled constant-or-margin variance','receiver-specific constant-or-margin variance'],
        same_40_to_600_Hz_bounds=True,training_only_noise_law_fits=True,
        heldout_score='full polynomial-residual Gaussian contrast covariance; omit identical normalization',
        qualification='total heldout gain>2log2 AND at least2of3fold gains>0',
        no_GPS_selection=True,graph_degrees_and_membership_inherited=True,
        no_claim_of_raw_noise_truth_or_independent_full_pipeline_validation=True,
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    with ProcessPoolExecutor(max_workers=4) as pool:summary=list(pool.map(one,cases))
    write(HERE/'summary.json',dict(rows=summary,qualified=sum(r['qualified'] for r in summary)))
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
