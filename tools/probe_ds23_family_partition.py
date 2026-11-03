"""Bounded all-family partition proposals; geography is not an inference input."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time

import numpy as np

import ds23_family_partition as split
import probe_ds23_family_cavity_nominations as nom
from ds23_family_cavity import coarse_phase_scores,predictive_density_reference,directional_orbit_frequency_reference
from ds23_conditioned_relative_nomination import gaussian_prediction
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_22_ds23_family_partition'
SOURCE=ROOT/'reports/2026_10_22_ds23_family_cavity/phase_refreshed/full_DS23'
CASES=['DS23-0268','DS23-0405','DS23-0080','DS23-0240']


def coarse_subset(d,data,mask,frequency,derivative,elevation):
    indices=np.flatnonzero(mask);groups,local=np.unique(data['groups'][mask],return_inverse=True)
    coarse=coarse_phase_scores(data['values'][mask],(data['radio']@data['coefficient'][:data['radio_width']])[mask],
        frequency[:,mask]*data['q'][mask],derivative[:,mask]*data['q'][mask],d['widths'],
        data['base_covariance'][np.ix_(indices,indices)],local)
    coarse['score']=np.where(elevation[:,mask].min(axis=1)>=0,coarse['score'],np.inf)
    return coarse,groups


def nominate(case):
    path=OUT/(case+'_nominations.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600s partition nomination cap')));signal.alarm(600)
    try:
        d=nom.setup(case);base=d['base'];families=sorted({r['candidate_index'] for r,s in zip(base.rows,base.slices,strict=True) if d['keep'][s].any()});rows=[];skipped=[]
        for target in families:
            try:data=nom.family_data(d,target)
            except ValueError as exc:
                if 'phase did not converge' not in str(exc):raise
                skipped.append(dict(original_index=target,reason=str(exc)));continue
            data['target']=target;partitions=split.partitions(d['scan'],data['members'])
            if not partitions:continue
            f,e=nom.phase_frequency_grid(d['scan'].sky,data['times'],*latlon(d['x']),phase_seconds=d['all_means'])
            plus,_=nom.phase_frequency_grid(d['scan'].sky,data['times'],*latlon(d['x']),phase_seconds=d['all_means']+.01)
            minus,_=nom.phase_frequency_grid(d['scan'].sky,data['times'],*latlon(d['x']),phase_seconds=d['all_means']-.01)
            derivative=(plus-minus)/.02
            whole=coarse_phase_scores(data['values'],data['radio']@data['coefficient'][:data['radio_width']],f*data['q'],derivative*data['q'],d['widths'],data['base_covariance'],data['groups'])
            original=nom.candidate_prediction(d,data,target,whole['aliases'][target])
            control=split.prediction(d,data,[target]*len(data['members']),whole['aliases'][target])
            for key in ['score','coefficient','residual_hz','prior_covariance']:np.testing.assert_allclose(control[key],original[key],rtol=1e-10,atol=2e-5)
            candidates=[]
            penalty=float(2*np.log(len(families)*len(partitions)*max(1,len(d['scan'].norads)-1)))
            for part in partitions:
                side=np.asarray(part['member_sides']);coarse=[];pools=[];members=[]
                for k in [0,1]:
                    c,g=coarse_subset(d,data,side[data['groups']]==k,f,derivative,e)
                    coarse.append(c);members.append(g)
                    pools.append([target]+[int(j) for j in np.argsort(c['score']) if np.isfinite(c['score'][j]) and j!=target][:2])
                pairs=sorted([(float(coarse[0]['score'][a]+coarse[1]['score'][b]),a,b) for a in pools[0] for b in pools[1] if a!=b])
                chosen=pairs[:3]
                for k in [1,2]:
                    anchored=next((r for r in pairs if r[k]==target),None)
                    if anchored is not None and anchored not in chosen:chosen.append(anchored)
                for proposal,a,b in chosen:
                    aliases=np.zeros(len(side),int)
                    for k,j in enumerate([a,b]):aliases[members[k]]=coarse[k]['aliases'][j]
                    labels=np.where(side==0,a,b);r=split.prediction(d,data,labels,aliases)
                    for key in ['prior_mean','prior_covariance']:r.pop(key)
                    r.update(pair=[a,b],partition=part['partition'],coarse_proposal_score=proposal,
                        predictive_gain=float(original['score']-r['score']),complexity_penalty=penalty,
                        penalized_predictive_gain=float(original['score']-r['score']-penalty))
                    candidates.append(r)
            rows.append(dict(original_index=target,original_norad=int(d['scan'].norads[target]),members=data['members'],
                held_observation_ids=data['held_ids'],original=original,candidates=candidates,partitions=len(partitions),
                cavity_phase_change_s=data['cavity_phase_change_s'],one_satellite_control_maximum_coefficient_difference=float(np.max(abs(control['coefficient']-original['coefficient'])))))
            print(case,'family',int(d['scan'].norads[target]),'partitions',len(partitions),'refined',len(candidates),flush=True)
        result=dict(case=case,status='complete',families=rows,skipped_proposals=skipped,all_active_families_considered=True,
            old_positive_whole_family_eligibility_not_required=True,reference_position_used=False)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result);return result


def select_offers(families):
    eligible=[(f,c) for f in families for c in f['candidates'] if c['qualified']]
    chosen=[]
    for field in ['predictive_gain','penalized_predictive_gain']:
        for item in sorted(eligible,key=lambda item:item[1][field],reverse=True)[:2]:
            if not any(item[0] is f and item[1] is c for f,c in chosen):chosen.append(item)
    return chosen


def fit(case):
    from probe_ds23_family_cavity_position import fit_configuration
    path=OUT/'position'/(case+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('600s partition position cap')));signal.alarm(600)
    try:
        saved=read(OUT/(case+'_nominations.json'));assert saved['status']=='complete';d=nom.setup(case);trials=[]
        for family,offer in select_offers(saved['families']):
            node,entries,means=split.configuration(d,[(family,offer)]);r=fit_configuration(d,node,entries,means)
            r.update(complexity_penalty=offer['complexity_penalty'],replacements=[dict(original_index=family['original_index'],
                original_norad=family['original_norad'],pair=offer['pair'],partition=offer['partition'],
                norads=[int(d['scan'].norads[j]) for j in offer['pair']],predictive_gain=offer['predictive_gain'])])
            trials.append(r);print(case,'split fit',r['replacements'],'paired valid',r['paired_valid'],flush=True)
        result=dict(case=case,status='complete',trials=trials,original_mask=d['keep'],powers=d['powers'],model=d['model'],
            all_original_curved_and_predictive_rows_preserved=True,reference_position_used=False,
            nomination_sha256=sha(OUT/(case+'_nominations.json')),previous_position_sha256=sha(SOURCE/'position'/(case+'.json')))
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result);return result


def audit(case):
    from audit_ds23_family_cavity import position as audit_position,density
    from build_dsx01_orbit_modes import build_modes
    from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
    d=nom.setup(case);saved=read(OUT/(case+'_nominations.json'));assert saved['status']=='complete';checks=[]
    for element in d['scan'].elements.values():
        p=element['provenance'];assert max(p['element_epoch_utc_ns'],p['collected_utc_ns'])<=d['scan'].receipt['cutoff_utc_ns']
    for family in saved['families']:
        data=nom.family_data(d,family['original_index']);data['target']=family['original_index'];assert data['held_ids']==family['held_observation_ids']
        density(d,data['p'],d['x'],d['means'],[])
        for row in family['candidates']:
            captures=[]
            def capture(raw,design,covariance,sigma):
                captures.append((raw.copy(),design.copy(),covariance.copy(),sigma.copy()))
                return gaussian_prediction(raw,design,covariance,sigma)
            split.gaussian_prediction=capture
            try:replay=split.prediction(d,data,row['labels_by_member'],row['aliases'])
            finally:split.gaussian_prediction=gaussian_prediction
            assert abs(replay['score']-row['score'])<2e-5
            direct,method=predictive_density_reference(*captures[-1]);delta=abs(direct-row['score']);assert delta<2e-3
            exact_delta=None
            if np.max(np.abs(row['phase_s']))<=15:
                coef=np.asarray(row['coefficient']);nb=data['radio_width'];prediction=data['radio']@coef[:nb]
                labels=np.asarray(row['labels_by_member'])[data['groups']]
                for model,phase in zip(row['satellite_parameters'],row['phase_s'],strict=True):
                    j=model['candidate_index'];bank=dict(time_s=d['scan'].sky['time_s'],**{k:d['scan'].sky[k][[j]] for k in ['position_km','velocity_km_s']})
                    f,_=paired_phase_frequency(bank,data['times'],np.zeros(len(labels),int),np.array([phase]),*latlon(d['x']))
                    use=labels==j;prediction[use]+=data['q'][use]*f[use]
                    if model['orbital_coordinates']:
                        p=data['p']
                        if j in p.supported:
                            local=p.labels.index(j);modes=dict(time_s=p.mode_bank['time_s'],**{k:p.mode_bank[k][3*local:3*local+3] for k in ['position_km','velocity_km_s']})
                        else:modes=build_modes(d['scan'],[j],[j],'physical')[0]
                        direction,convergence=directional_orbit_frequency_reference(bank,modes,coef[model['orbital_coordinates']],data['times'],phase,*latlon(d['x']))
                        assert convergence<2e-5;prediction[use]+=data['q'][use]*direction[use]
                prediction+=coef[row['constant_start']:][data['groups']]
                residual=data['values']+np.asarray(row['aliases'])[data['groups']]/4.4e-6-prediction
                exact_delta=float(np.max(abs(residual-row['residual_hz'])));assert exact_delta<2e-4
            checks.append(dict(original_norad=family['original_norad'],density_difference=delta,density_method=method,exact_residual_difference_hz=exact_delta))
    positions=audit_position(case,position_dir=OUT/'position')
    return dict(case=case,all_passed=True,nomination_checks=checks,position_checks=positions,
        nomination_sha256=sha(OUT/(case+'_nominations.json')),position_sha256=sha(OUT/'position'/(case+'.json')),
        entire_catalogue_causal_epoch_and_collection_checked=True,reference_position_used=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['nominations','positions','audit'],required=True)
    parser.add_argument('--workers',type=int,default=4);args=parser.parse_args()
    if not 1<=args.workers<=30:raise ValueError('1to30workers required')
    OUT.mkdir(exist_ok=True);(OUT/'position').mkdir(exist_ok=True)
    protocol=dict(cases=CASES,scope='engineering diagnostic, not generalization',all_active_families=True,
        partitions='receiver, band, owner, component, chronological whole-fragment boundaries; both sides curved',
        candidates='full causal catalogue separately per group; original plus top2 alternatives; top3pairs and anchored controls',
        shared_calibration_posterior_once=True,all_held_family_points_disjoint_from_calibration=True,
        shortlist='union top2 raw and top2 split-prior predictive gain; positive gain not required',
        split_prior='equal split/no-split class mass, uniform target family and partition; relative identity penalty2log(F*K*(M-1))',
        primary='corrected normalized c0 final loss plus split prior; original paired gates and phase convergence required',
        control='same candidates and fits, no discrete split penalty',compare_against='previous selected whole-family conditional cavity method',
        all_original_points_and_physical_priors_restored_for_final_fit=True,one_split_per_trial=True,
        cold_start=[0,0],regional_width_km=25,phase_rounds=5,position_steps=48,matched_c0_fitted_c=True,
        no_GPS_RF_future_TLE_or_point_deletion=True,nomination_cap_s=600,position_cap_s=600,
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_family_partition.py',ROOT/'tools/probe_ds23_family_cavity_position.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('frozen partition protocol changed')
    if not path.exists():write(path,protocol)
    function={'nominations':nominate,'positions':fit,'audit':audit}[args.stage];rows=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(function,c) for c in CASES]):
            rows.append(f.result());write(OUT/(args.stage+'_progress.json'),dict(rows=rows,completed=len(rows),total=len(CASES)))
    write(OUT/(args.stage+'_execution.json'),dict(rows=rows,all_terminal=True,all_passed=all(r.get('all_passed',r.get('status')=='complete') for r in rows),
        no_geographic_evaluation_yet=True))


if __name__=='__main__':main()
