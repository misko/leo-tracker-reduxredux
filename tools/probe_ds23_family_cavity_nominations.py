"""Full-causal-catalogue replacement nominations from family-excluded calibration.

All original family observations are predictive evidence during nomination.
No RF measurement, evaluation coordinate or future element is accessed.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from build_dsx01_orbit_modes import build_modes
from ds23_causal_phase_location import adjust_means
from ds23_conditioned_relative_nomination import gaussian_prediction
from ds23_family_cavity import coarse_phase_scores
from ds23_frequency_events import make_event_problem
from ds23_predictive_linear import linear_geometry
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_sign_carrier_position import context_signed
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes

OUT=ROOT/'reports/2026_10_22_ds23_family_cavity/phase_refreshed'
CASES=['DS23-0268','DS23-0405','DS23-0240']


def setup(case):
    scan,node,keep,powers,means,model,entries,signed,binding=context_signed(case)
    saved=signed['policy_arms']['c0'];reference=np.asarray(saved['phase_reference']);x=np.asarray(saved['endpoint_east_north_km'])
    base=make_event_problem(scan,node,keep,'c0',reference,powers,means,model,[])
    widths,receipts=phase_widths(scan,list(range(len(scan.norads))))
    all_means=forecast_phase_mean(receipts,model['shrinkage'])
    if signed['accepted']:all_means=adjust_means(all_means,receipts,model,signed['selection'])
    return dict(scan=scan,node=node,keep=keep,powers=np.asarray(powers),means=np.asarray(means),model=model,entries=entries,
        signed=signed,binding=binding,base=base,x=x,reference=reference,all_means=np.asarray(all_means),widths=widths*model['multiplier'])


def family_data(d,target):
    base=d['base'];keep=d['keep'].copy();curved=[]
    for k,(row,i,sl) in enumerate(zip(base.rows,base.members,base.slices,strict=True)):
        if row['candidate_index']==target:
            keep[sl]=False
            if d['keep'][sl].any():curved.append(k)
    reference=d['reference'].copy()
    for _ in range(5):
        p=make_event_problem(d['scan'],d['node'],keep,'c0',reference,d['powers'],d['means'],d['model'],[])
        phase=np.clip(p.state(d['x'])['phases'][p.labels],-15,15)
        phase_change=float(np.max(abs(phase-reference)));reference=phase
    if phase_change>.01:raise ValueError('family-excluded calibration phase did not converge')
    c=p.calculate(d['x']);present=p.noise_groups[keep];u=c['features'][keep]
    w=d['powers'][present]*c['noise_precision'][present]/p.point_noise[keep]**2
    gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None]);cov=np.linalg.inv(gram)
    radio_width=p.hardware.shape[1]+p.smooth.shape[1];times=[];values=[];q=[];radio=[];noise=[];groups=[];members=[]
    for k in curved:
        i=base.members[k];sl=base.slices[k];use=d['keep'][sl];t=p.scan.tracks[i];g=len(members)
        members.append(dict(kind='curved',row_index=k,component=t['key'],track_index=i,points=int(use.sum()),
            observation_ids=np.asarray(t['observation_ids'])[use].tolist(),receiver=t['receiver'],channel=t['channel']))
        times.extend(t['times'][use]);values.extend(t['values'][use]);q.extend(p.q[sl][use]);radio.extend(c['features'][sl,:radio_width][use])
        noise.extend(p.point_noise[sl][use]*np.sqrt(2/d['powers'][k]));groups.extend([g]*int(use.sum()))
    selected=[e for e in d['entries'] if e['candidate_index']==target]
    if selected:
        view,y,sigma,g,slices=linear_geometry(p,selected)
        from ds23_height_problem import geometry_features
        geometry=geometry_features(view,d['x'],0.)
        for entry,sl in zip(selected,slices,strict=True):
            t=p.scan.tracks[entry['track_index']]
            if t['observation_ids']!=entry['observation_ids']:raise ValueError('predictive metadata differs from held numerical rows')
            group=len(members);members.append(dict(kind='predictive',component=entry['component'],track_index=entry['track_index'],
                points=len(t['times']),observation_ids=t['observation_ids'],receiver=t['receiver'],channel=t['channel']))
            times.extend(t['times']);values.extend(t['values']);q.extend(view.q[sl]);radio.extend(geometry['features'][sl,:radio_width])
            noise.extend(sigma[sl]*np.sqrt(2));groups.extend([group]*len(t['times']))
    times,values,q,radio,noise,groups=map(np.asarray,(times,values,q,radio,noise,groups))
    calibration_ids={oid for i,sl in zip(p.members,p.slices,strict=True) for oid,use in zip(p.scan.tracks[i]['observation_ids'],keep[sl],strict=True) if use}
    held_ids={oid for m in members for oid in m['observation_ids']}
    if calibration_ids&held_ids:raise ValueError('held family was used in calibration')
    covariance=np.diag(noise**2)+radio@cov[:radio_width,:radio_width]@radio.T+300.**2*(groups[:,None]==groups[None,:])
    return dict(p=p,coefficient=c['coefficient'],covariance=cov,radio_width=radio_width,times=times,values=values,q=q,
        radio=radio,noise=noise,groups=groups,members=members,base_covariance=covariance,calibration_mask=keep,
        held_ids=sorted(held_ids),cavity_phase_change_s=phase_change,
        held_owners=len({(m['receiver'],m['channel']) for m in members if m['kind']=='curved'}))


def candidate_prediction(d,data,j,aliases):
    p=data['p'];nb=data['radio_width'];target_index=data['target'];old_active={r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if p.keep[sl].any()}
    supported=j in p.supported or data['held_owners']>=2
    if j in p.supported:
        k=p.labels.index(j);mode_bank=dict(time_s=p.mode_bank['time_s'],position_km=p.mode_bank['position_km'][3*k:3*k+3],velocity_km_s=p.mode_bank['velocity_km_s'][3*k:3*k+3])
    else:mode_bank=build_modes(d['scan'],[j],[j] if supported else [],'physical')[0]
    bank=dict(time_s=d['scan'].sky['time_s'],position_km=d['scan'].sky['position_km'][[j]],velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
    slots=list(range(nb));mean=data['coefficient'][:nb].tolist();phase_slot=nb+p.labels.index(j) if j in p.labels and j in old_active else None
    slots.append(phase_slot);mean.append(data['coefficient'][phase_slot] if phase_slot is not None else d['all_means'][j]/d['widths'][j])
    if supported:
        start=nb+len(p.labels)+3*p.supported.index(j) if j in p.supported and j in old_active else None
        slots.extend([start+k if start is not None else None for k in range(3)])
        mean.extend(data['coefficient'][start:start+3] if start is not None else np.zeros(3))
    nconstant=len(data['members']);slots.extend([None]*nconstant);mean.extend(np.zeros(nconstant));mean=np.asarray(mean)
    covariance=np.eye(len(slots));used=[k for k,s in enumerate(slots) if s is not None];old=[slots[k] for k in used]
    covariance[np.ix_(used,used)]=data['covariance'][np.ix_(old,old)];covariance[-nconstant:,-nconstant:]=np.eye(nconstant)*300**2
    constants=np.eye(nconstant)[data['groups']];reference=float(mean[nb]*d['widths'][j]);history=[];values=data['values']+np.asarray(aliases)[data['groups']]/4.4e-6
    def geometry(phase):
        f,e=phase_frequency_grid(bank,data['times'],*latlon(d['x']),phase_seconds=phase)
        plus,_=phase_frequency_grid(bank,data['times'],*latlon(d['x']),phase_seconds=phase+.01)
        minus,_=phase_frequency_grid(bank,data['times'],*latlon(d['x']),phase_seconds=phase-.01)
        derivative=(plus[0]-minus[0])/.02;intercept=data['q']*(f[0]-derivative*phase)
        features=[data['radio'],(data['q']*derivative*d['widths'][j])[:,None]]
        if supported:
            modes=paired_frequency_modes(bank,mode_bank,data['times'],np.zeros(len(data['times']),int),np.array([phase]),*latlon(d['x']))
            features.append(data['q'][:,None]*modes)
        return intercept,np.column_stack((*features,constants)),e[0]
    for _ in range(5):
        intercept,features,e=geometry(reference);result=gaussian_prediction(values-intercept-features@mean,features,covariance,data['noise'])
        coefficient=mean+result['parameter_update'];phase=float(coefficient[nb]*d['widths'][j]);change=abs(phase-reference);history.append(change);reference=float(np.clip(phase,-15,15))
    if abs(phase)<=15:
        intercept,features,e=geometry(phase);residual=values-intercept-features@coefficient
    else:e=np.full(len(values),-90.);residual=result['native_residual']
    return dict(candidate_index=j,norad=int(d['scan'].norads[j]),score=result['objective'],phase_s=phase,
        phase_change_s=change,minimum_elevation_deg=float(e.min()),aliases=aliases,conditional_RMS_hz=float(np.sqrt(np.mean(residual**2))),
        qualified=bool(abs(phase)<=15 and e.min()>=0 and change<=.01),residual_hz=residual,coefficient=coefficient,
        prior_mean=mean,prior_covariance=covariance,calibration_slots=slots,physical_modes=supported,
        all_held_observations_predictive_never_calibrate=True)


def one(case,output_dir=None):
    path=(OUT if output_dir is None else Path(output_dir))/(case+'_nominations.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('360s cavity nomination cap')));signal.alarm(360)
    try:
        d=setup(case);p=d['base'];rows=[]
        families=sorted({r['candidate_index'] for r,sl in zip(p.rows,p.slices,strict=True) if d['keep'][sl].any()})
        for target in families:
            data=family_data(d,target);data['target']=target
            if len(data['values'])<4:continue
            f,e=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(d['x']),phase_seconds=d['all_means'])
            plus,_=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(d['x']),phase_seconds=d['all_means']+.01)
            minus,_=phase_frequency_grid(d['scan'].sky,data['times'],*latlon(d['x']),phase_seconds=d['all_means']-.01)
            coarse=coarse_phase_scores(data['values'],data['radio']@data['coefficient'][:data['radio_width']],f*data['q'],
                (plus-minus)/.02*data['q'],d['widths'],data['base_covariance'],data['groups'])
            scores=np.where(e.min(axis=1)>=0,coarse['score'],np.inf)
            ordered=[int(j) for j in np.argsort(scores) if np.isfinite(scores[j]) and j!=target][:7]
            pool=[target]+ordered;candidates=[]
            for j in pool:candidates.append(candidate_prediction(d,data,j,coarse['aliases'][j]))
            eligible=sorted([r for r in candidates if r['qualified']],key=lambda r:r['score']);original=next(r for r in candidates if r['candidate_index']==target)
            best=next((r for r in eligible if r['candidate_index']!=target),None)
            gain=original['score']-best['score'] if best is not None else None
            rows.append(dict(original_index=target,original_norad=int(d['scan'].norads[target]),members=data['members'],
                held_observation_ids=data['held_ids'],held_points=len(data['values']),coarse_candidate_count=len(scores),
                candidates=candidates,original=original,best=best,predictive_gain=gain,
                search_penalty=float(2*np.log(len(scores))),all_held_points_disjoint_from_calibration=True,
                cavity_phase_change_s=data['cavity_phase_change_s'],no_predictive_noise_gate_used_to_veto_a_joint_proposal=True))
            print(case,int(d['scan'].norads[target]),'gain',gain,flush=True)
        result=dict(case=case,status='complete',families=rows,reference_position_used=False,
            no_RF_GPS_future_TLE_or_point_deletion=True,incumbent_arms=d['signed']['policy_arms'])
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result);return result


def main():
    OUT.mkdir(exist_ok=True)
    protocol=dict(cases=CASES,workers=3,per_case_seconds=360,all_active_curved_families=True,
        coarse_full_causal_catalogue_gaussian_phase_screen=True,exact_phase_refined_candidates_per_family=8,
        five_fixed_position_cavity_phase_refreshes=True,
        previous_one_reference_experiment_sha256=sha(OUT.parent/'nomination_execution.json'),
        previous_fixed_reference_max_active_phase_changes_s=[.1475291175202876,.37622056543531324,.05822871921771644],
        correction_required_before_position_trials_no_GPS_used=True,
        original_nominee_always_included=True,GLRT_calibration_covariance_from_all_other_curved_families=True,
        all_disputed_curved_and_predictive_points_enter_same_joint_prediction=True,
        unknown_phase_Gaussian_moment_approximation_proposal_only=True,
        new_candidate_physical_modes_only_with_two_held_curved_owners=True,
        covariance_includes_radio_phase_orbit_correlations=True,no_GPS_RF_future_TLE_or_point_deletion=True,
        unused_phase_prior_moment_used_instead_of_unused_variational_half_variance=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_family_cavity.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('cavity nomination protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=3) as pool:rows=[f.result() for f in as_completed([pool.submit(one,c) for c in CASES])]
    write(OUT/'nomination_execution.json',dict(rows=rows,all_terminal=True,no_position_gain_claim=True))


if __name__=='__main__':main()
