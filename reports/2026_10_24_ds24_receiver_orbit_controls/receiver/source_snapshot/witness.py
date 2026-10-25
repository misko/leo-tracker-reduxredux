"""GPS-blind whole-family contrasts for a shared RX1 discrepancy witness.

This is conditional on previously selected masks/labels, not a new blind
identification study. No incumbent residual or fitted position enters a fit.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import time
import numpy as np
from scipy.linalg import qr

import algo02_scan as algo
from ds23_height_problem import geometry_features
from probe_ds23_graph_seeded_paths import build as original_build
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis

HERE=Path(__file__).resolve().parent
ROOT=Path('/srv/bulk/leo/research/ds25-20261024')
COHORT=Path('/srv/bulk/leo/research/ds24-channel-halves-20261024/summary.json')
SEED=20261025
SIGMA_HZ=75.
FAST_SIGMA_HZ=50.
METHODS=('fast_rx1_hz50','fast_rx1_rf50')

def read(p):return json.loads(p.read_text())
def encode(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    raise TypeError(type(x).__name__)
def write(p,x):p.write_text(json.dumps(x,indent=2,default=encode)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def replay(case):
    saved=read(ROOT/'family_cavity/position'/(case+'.json'))
    assert saved['status']=='complete'
    selected=saved['selected'] if saved['accepted'] else None
    algo.bind_run_directory(ROOT)
    return dict(scan=algo.load_scan(ROOT,case),
        node=selected['node'] if selected else saved['baseline_node'],
        keep=np.asarray(saved['original_mask'],bool),powers=np.asarray(saved['powers']),
        model=saved['model'],means=np.asarray(selected['means'] if selected else saved['baseline_means']),
        entries=selected['entries'] if selected else saved['baseline_entries'])

def fast_basis(times,receivers,q,method,*,training_control='native'):
    if method not in METHODS:raise ValueError('unknown frozen covariance design')
    times=np.asarray(times,float);receivers=np.asarray(receivers);q=np.asarray(q,float)
    if training_control not in ('native','wrong_RX','shift75'):raise ValueError('unknown negative control')
    if training_control=='shift75':times=(times+75.)%300.
    basis=projected_receiver_basis(times,spacing_s=10.,width_s=5.)*FAST_SIGMA_HZ
    basis*=((receivers==2) if training_control=='wrong_RX' else (receivers==1))[:,None]
    if method=='fast_rx1_rf50':basis*=q[:,None]
    return basis

def nuisance_projector(design):
    """Design-only orthonormal nuisance span, with invariant unit scaling."""
    a=np.asarray(design,float);norm=np.linalg.norm(a,axis=0);use=norm>1e-12
    if not use.any():return np.zeros((len(a),0)),0
    q,r,_=qr(a[:,use]/norm[use],mode='economic',pivoting=True)
    diagonal=abs(np.diag(r));rank=int(np.count_nonzero(diagonal>1e-8*max(diagonal[0],1.)))
    return q[:,:rank],rank

def project(values,orthogonal):return values-orthogonal@(orthogonal.T@values)

def statistics(y,b,dimension):
    return dict(dimension=dimension,square=float(y@y),cross=b.T@y,gram=b.T@b)

def add_statistics(rows):
    if not rows:raise ValueError('nonempty family statistics required')
    return {k:sum((r[k] for r in rows)) for k in rows[0]}

def predictive(train,test,sigma_hz=SIGMA_HZ):
    """Exact diagonal-plus-low-rank density of all held contrasts jointly."""
    variance=sigma_hz**2;k=len(train['cross'])
    a=np.eye(k)+train['gram']/variance
    mean=np.linalg.solve(a,train['cross']/variance)
    all_a=a+test['gram']/variance
    residual_square=float(test['square']-2*mean@test['cross']+mean@test['gram']@mean)
    cross=test['cross']-test['gram']@mean
    quadratic=residual_square/variance-cross@np.linalg.solve(all_a,cross)/variance**2
    volume=np.linalg.slogdet(all_a)[1]-np.linalg.slogdet(a)[1]
    normal=test['dimension']*np.log(2*np.pi*variance)
    assert quadratic>-1e-6
    return dict(negative_twice_log_density=float(normal+quadratic+volume),
        quadratic=float(quadratic),logvolume=float(volume),dimension=test['dimension'],
        predictive_mean_contrast_RMS_hz=float(np.sqrt(max(residual_square,0)/test['dimension'])),
        posterior_coefficient=mean,posterior_precision=a)

def data(case):
    d=replay(case);p=original_build(d,'default','c0',np.zeros(len(d['means'])))
    center=np.zeros(2);g=geometry_features(p,center,0.)
    raw=p.values-p.q*g['intercept']
    rows=[];flat_rx=np.zeros(len(raw),int);fragment=np.zeros(len(raw),int)
    for k,(member,sl) in enumerate(zip(p.members,p.slices,strict=True)):
        flat_rx[sl]=p.scan.tracks[member]['receiver'];fragment[sl]=k
    position=[]
    for delta in np.eye(2)*.01:
        plus=geometry_features(p,center+delta,0.)
        minus=geometry_features(p,center-delta,0.)
        position.append(p.q*(plus['intercept']-minus['intercept'])/.02)
    position=np.column_stack(position)
    begin=p.hardware.shape[1]+p.smooth.shape[1]
    end=begin+len(p.labels)+3*len(p.supported)
    physical=g['features'][:,begin:end]
    absolute_family=np.asarray(p.labels)[p.flat_labels]
    source_families=sorted(set(absolute_family[p.keep]))
    projected_c_max=0.
    for family in source_families:
        ix=np.flatnonzero(p.keep&(absolute_family==family));times=p.flat_times[ix]
        fragments=fragment[ix];parts=[]
        for member in sorted(set(fragments)):
            use=(fragments==member).astype(float)
            local_times=times[fragments==member]
            parts.extend((use,use*(times-local_times.mean())/max(np.ptp(local_times),1.)))
        nuisance=np.column_stack((*parts,physical[ix],position[ix]))
        orthogonal,rank=nuisance_projector(nuisance)
        dimension=len(ix)-rank
        if dimension<6:
            rows.append(dict(family=int(family),norad=int(p.scan.norads[family]),points=len(ix),rank=rank,dimension=dimension,eligible=False))
            continue
        y=project(raw[ix],orthogonal);slow=project(p.smooth[ix]*200.,orthogonal)
        c=(p.q[ix]*11.5-11.5)*200000.
        c_remainder=np.linalg.norm(project(c,orthogonal))/max(np.linalg.norm(c),1.)
        projected_c_max=max(projected_c_max,c_remainder)
        assert c_remainder<1e-9
        # This checks that no held nuisance coefficient was inferred from data.
        norm=np.maximum(np.linalg.norm(nuisance,axis=0),1.)
        trial=(nuisance/norm)@np.arange(1,nuisance.shape[1]+1)
        assert np.max(abs(project(raw[ix]+trial,orthogonal)-y))<1e-5
        model_stats={};designs={}
        model_stats['baseline/native']=statistics(y,slow,dimension)
        for method in METHODS:
            for control in ('native','wrong_RX','shift75'):
                fast=project(fast_basis(times,flat_rx[ix],p.q[ix],method,training_control=control),orthogonal)
                matrix=np.column_stack((slow,fast))
                model_stats[method+'/'+control]=statistics(y,matrix,dimension)
        rows.append(dict(family=int(family),norad=int(p.scan.norads[family]),points=len(ix),rank=rank,dimension=dimension,
            eligible=True,statistics=model_stats,receivers=sorted(set(flat_rx[ix].tolist()))))
    return rows,dict(projected_c_relative_norm_max=projected_c_max,
        family_count=len(source_families),active_points=int(p.keep.sum()),
        source_mask_node_digest=sha(ROOT/'family_cavity/position'/(case+'.json')),
        no_incumbent_position_or_residual_read=True)

def one(case):
    started=time.monotonic();rows,audit=data(case)
    eligible=[r for r in rows if r['eligible']]
    # Stable stream keyed by case; all owners/channels of a family share a fold.
    seed=SEED+int(case.rsplit('-',1)[1]);order=np.random.default_rng(seed).permutation(len(eligible))
    assignments={eligible[index]['family']:k%3 for k,index in enumerate(order)}
    results=[]
    for fold in range(3):
        train=[r for r in eligible if assignments[r['family']]!=fold]
        test=[r for r in eligible if assignments[r['family']]==fold]
        assert not ({r['family'] for r in train}&{r['family'] for r in test})
        if not train or not test:raise ValueError('whole-family fold lacks contrast support')
        by={}
        configurations=['baseline/native']+[m+'/'+c for m in METHODS for c in ('native','wrong_RX','shift75')]
        for configuration in configurations:
            method,control=configuration.split('/')
            target='baseline/native' if method=='baseline' else method+'/native'
            training=add_statistics([r['statistics'][configuration] for r in train])
            testing=add_statistics([r['statistics'][target] for r in test])
            prediction=predictive(training,testing)
            family_predictions=[]
            for row in test:
                pred=predictive(training,row['statistics'][target])
                family_predictions.append(dict(norad=row['norad'],points=row['points'],dimension=row['dimension'],
                    negative_twice_log_density=pred['negative_twice_log_density'],predictive_mean_contrast_RMS_hz=pred['predictive_mean_contrast_RMS_hz']))
            by[configuration]=dict(**{k:v for k,v in prediction.items() if k not in ('posterior_coefficient','posterior_precision')},family_predictions=family_predictions)
        for configuration,saved in by.items():
            saved['gain_vs_baseline']=by['baseline/native']['negative_twice_log_density']-saved['negative_twice_log_density']
        results.append(dict(fold=fold,train_norads=[r['norad'] for r in train],test_norads=[r['norad'] for r in test],
            train_points=sum(r['points'] for r in train),test_points=sum(r['points'] for r in test),results=by))
    output=dict(case=case,status='complete',seed=seed,audit=audit,folds=results,
        families=[{k:v for k,v in r.items() if k!='statistics'} for r in rows],seconds=time.monotonic()-started,
        c0_fitted_c_witness_identical_after_affine_projection=True)
    write(HERE/(case+'.json'),output)
    print(case,'seconds',round(output['seconds'],2),'gains',{m:round(sum(f['results'][m+'/native']['gain_vs_baseline'] for f in results),2) for m in METHODS},flush=True)
    return output

def protocol(cases):
    return dict(cases=cases,seed=SEED,folds=3,family_split='Random whole families, all RX/channels and fragments together; case-specific seed=20261025+numeric case suffix',
        raw_observations='Original lifted curved CFO minus nominal causal TLE Doppler at fixed regional center; zero fitted phase reference',
        target='Design-only orthogonal contrasts removing each fragment affine plus shared family phase/three physical orbit modes and two local position derivatives',
        target_nuisance='No target nuisance coefficient or noise learned; projection design uses only timestamps/RF/nominal geometry',
        baseline='Original slow receiver covariance (200 Hz coefficient scale), posterior learned from training families only',
        candidates={m:dict(receiver=1,loading='constant Hz' if m.endswith('hz50') else 'RF/11.5GHz',
            coefficient_sigma_hz=FAST_SIGMA_HZ,centers_s=list(np.arange(0,301,10)),width_s=5.,affine_removed_on_fixed_0_300_grid=True) for m in METHODS},
        independent_noise_sigma_hz=SIGMA_HZ,noise_is_fixed_engineering_reference_not_calibrated=True,
        controls=['Train extra component on RX2 instead, predict RX1','Shift extra training time by+75s modulo300, predict native target times'],
        primary_score='Complete held-family contrast vector correlated Gaussian predictive density; shared posterior covariance retained across held families',
        qualification='Native total gain>2log2, median case gain>0, positive gain on at least13/24cases, native beats each negative control by>2log3; choose minimum native total loss among qualifying candidates',
        full_RF_selected_labels_masks_are_conditioning_inputs=True,no_GPS_in_fit_or_selection=True,no_IQ_or_new_RF=True,
        no_incumbent_fitted_positions_residuals_or_Gamma_precisions_used=True,
        paired_c='Witness c columns are exactly fragment constants and vanish under contrasts; ensuing position propagation must refit both arms',
        source_sha256=sha(Path(__file__)))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case');parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    if args.case:one(args.case);return
    cases=read(COHORT)['baseline']['c0']['common_cases']
    if (HERE/'protocol.json').exists():
        if not args.resume:raise FileExistsError('preserve frozen receiver witness protocol')
        old=read(HERE/'protocol.json');current=protocol(cases)
        assert {k:v for k,v in old.items() if k!='source_sha256'}=={k:v for k,v in current.items() if k!='source_sha256'}
        write(HERE/'implementation_amendment.json',dict(original_protocol_sha256=sha(HERE/'protocol.json'),original_source_sha256=old['source_sha256'],current_source_sha256=current['source_sha256'],reason='Normalize columns in validation-only nuisance-invariance assertion; data, projection, model designs, split, scores and selection unchanged'))
    else:write(HERE/'protocol.json',protocol(cases))
    outputs=[one(case) for case in cases]
    summary={}
    for method in METHODS:
        percase=[]
        for output in outputs:
            gains={c:sum(f['results'][method+'/'+c]['gain_vs_baseline'] for f in output['folds']) for c in ('native','wrong_RX','shift75')}
            percase.append(dict(case=output['case'],**gains))
        total={c:sum(r[c] for r in percase) for c in ('native','wrong_RX','shift75')}
        median=float(np.median([r['native'] for r in percase]));positive=sum(r['native']>0 for r in percase)
        qualified=bool(total['native']>2*np.log(2) and median>0 and positive>=13 and all(total['native']-total[c]>2*np.log(3) for c in ('wrong_RX','shift75')))
        summary[method]=dict(per_case=percase,total_gain=total,median_case_native_gain=median,positive_cases=positive,qualified=qualified)
    eligible=[m for m in METHODS if summary[m]['qualified']]
    selected=max(eligible,key=lambda m:summary[m]['total_gain']['native']) if eligible else 'baseline'
    write(HERE/'selection.json',dict(status='complete',selected_method=selected,methods=summary,
        selection_uses_no_GPS=True,qualifies_only_conditional_held_family_contrast_prediction=True,
        all_24_cases_retained=True,protocol_sha256=sha(HERE/'protocol.json')))
    print(json.dumps(dict(selected_method=selected,summary=summary),indent=2))

if __name__=='__main__':main()
