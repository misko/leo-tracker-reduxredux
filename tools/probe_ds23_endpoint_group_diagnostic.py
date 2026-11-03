"""Whole versus endpoint-clutter prediction from independent grouped evidence."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import run_ds23_dbg01_iteration_007 as runner
import probe_ds23_new_family_prediction as model
from ds23_new_family_prediction import orbit_terms,wrapped_curve_score,new_gates
from ds23_predictive_linear import linear_geometry
from ds23_predictive_subsets import realize_predictive_subsets
from ds23_height_problem import geometry_features
from build_dsx01_orbit_modes import build_modes
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'endpoint_group_diagnostic'


def endpoint_variants(track):
    times=np.asarray(track['times']);values=np.asarray(track['values']);pieces=track['pieces']
    if len(times)<10 or len(pieces)!=1 or pieces[0]['degree']<3:return []
    degree=pieces[0]['degree'];z=(times-times.mean())/np.ptp(times);u=np.polynomial.legendre.legvander(z,degree)
    if np.linalg.matrix_rank(u)<degree+1:return []
    q,_=np.linalg.qr(u,mode='reduced');leverage=np.sum(q*q,axis=1);gaps=np.diff(times);positive=gaps[gaps>0]
    if not len(positive):return []
    result=[]
    for index,gap in [(0,gaps[0]),(len(times)-1,gaps[-1])]:
        keep=np.array([i for i in range(len(times)) if i!=index])
        if leverage[index]<.98 or gap<5*np.median(positive) or np.ptp(times[keep])<6:continue
        scores=[]
        for order in range(1,5):
            design=np.polynomial.legendre.legvander(z[keep],order);r=values[keep]-design@np.linalg.lstsq(design,values[keep],rcond=None)[0]
            scores.append(len(keep)*np.log(max(1e-12,float(np.mean(r*r))))+(order+1)*np.log(len(keep)))
        core_degree=int(np.argmin(scores))+1
        if core_degree<degree:result.append(dict(removed_index=index,indices=keep,leverage=float(leverage[index]),
            gap_s=float(gap),median_gap_s=float(np.median(positive)),original_degree=degree,core_degree=core_degree))
    return result


def fixed_groups(d,arm,entries):
    reference=np.asarray(d['arms'][arm]['phase_reference']);x=np.asarray(d['arms'][arm]['endpoint_east_north_km'])
    phase=np.zeros(len({e['candidate_index'] for e in entries}));change=np.inf
    for _ in range(5):
        p=model.build(d,arm,reference,phase,entries,True);next_phase=np.clip(p.calculate(x)['new_family_phases_s'],-15,15)
        change=float(np.max(abs(next_phase-phase)));phase=next_phase
    return p,x,change


def expected(p,d,x,index,j):
    track=p.scan.tracks[index];times=track['times'];q=track['rf_hz']/11.5e9;c=p.calculate(x)
    dummy=dict(track_index=index,candidate_index=p.labels[0],alias=0)
    view,*_=linear_geometry(p,[dummy]);width=p.hardware.shape[1]+p.smooth.shape[1]
    radio=geometry_features(view,x,0.)['features'][:,:width]@c['coefficient'][:width]
    local=p.new_family_indices.index(j);phase=c['new_family_phases_s'][local]
    bank=dict(time_s=p.scan.sky['time_s'],position_km=p.scan.sky['position_km'][[j]],velocity_km_s=p.scan.sky['velocity_km_s'][[j]])
    f,el,_=orbit_terms(bank,times,phase,*latlon(x));modes,_=build_modes(p.scan,[j],[j],'physical')
    mode=paired_frequency_modes(bank,modes,times,np.zeros(len(times),int),np.array([phase]),*latlon(x))
    mean=radio+q*(f+mode@c['new_family_coefficient'][4*local+1:4*local+4])
    return mean,el


def one(case):
    d=runner.engine.current_setup(case);source=read(runner.RAW/'new_family_prediction_v2'/(case+'_selection.json'));entries=source['entries']
    inventory=read(runner.RAW/case/'inventory.json')['arms'];occupied=set().union(*(set(v['accepted_observation_ids']) for v in inventory.values()))
    offered=[]
    for i in d['scan'].curved:
        track=d['scan'].tracks[i]
        if set(track['observation_ids'])&occupied:continue
        for variant in endpoint_variants(track):offered.append(dict(track_index=i,component=track['key'],**variant))
    offered.sort(key=lambda r:-np.ptp(d['scan'].tracks[r['track_index']]['times']));offered=offered[:3]
    if not entries:
        write(OUT/(case+'.json'),dict(case=case,offers=offered,rows=[],no_supported_new_family=True));return dict(case=case,offers=len(offered),models=0)
    parents={a:fixed_groups(d,a,entries) for a in ['c0','fitted_c']};families=sorted({e['candidate_index'] for e in entries})
    penalty=float(2*np.log(max(1,len(offered))*len(families)*2));rows=[]
    for offer in offered:
        track=d['scan'].tracks[offer['track_index']];keep=np.asarray(offer['indices']);pair={}
        for arm,(p,x,change) in parents.items():
            base=p.calculate(x)['linear_predictive_objective'];candidates=[]
            for j in families:
                mean,el=expected(p,d,x,offer['track_index'],j);alias=int(np.rint(np.mean(mean-track['values'])/PERIOD))
                full=dict(track_index=offer['track_index'],component=track['key'],candidate_index=j,norad=int(d['scan'].norads[j]),alias=alias,
                    points=len(track['times']),observation_ids=track['observation_ids'])
                a=model.build(d,arm,p.reference,p.new_references,entries+[full],True);ca=a.calculate(x)
                subset=dict(full,points=len(keep),observation_ids=np.asarray(track['observation_ids'])[keep].tolist())
                scan,realized,_=realize_predictive_subsets(d['scan'],[subset]);dd=dict(d,scan=scan)
                b=model.build(dd,arm,p.reference,p.new_references,entries+realized,True);cb=b.calculate(x)
                whole=ca['linear_predictive_objective']-base;core=cb['linear_predictive_objective']-base+2*np.log(PERIOD)
                sigma=np.full(len(track['times']),d['scan'].radio_sigma_hz*np.sqrt(2))
                meta=d['scan'].fixed_window_noise
                if meta['extra_parameter_BIC_gain']>0:sigma=np.array([meta['per_observation_noise_sigma_hz'][o] for o in track['observation_ids']])*np.sqrt(2)
                null=wrapped_curve_score(track['times'],track['values'],sigma)
                gates=new_gates(b,x)
                candidates.append(dict(norad=int(d['scan'].norads[j]),candidate_index=j,alias=alias,
                    whole_conditional_score=whole,core_plus_clutter_score=core,unknown_curve_score=null,
                    penalized_gain=min(whole,null)-core-penalty,fixed_group_phase_change_s=change,
                    all_new_predictive_gates_pass=all(g['compatible'] for g in gates),core_gates=gates[-1],
                    expected_hz=mean,raw_residual_hz=track['values']+alias*PERIOD-mean,
                    eligible=bool(change<=.01 and min(whole,null)-core-penalty>2*np.log(100) and all(g['compatible'] for g in gates))))
            pair[arm]=candidates
        rows.append(dict(offer=offer,arms=pair,penalty=penalty))
    write(OUT/(case+'.json'),dict(case=case,offers=offered,rows=rows,diagnostic_only_no_new_position_or_ID_adopted=True,
        original_persisted_polynomial_unchanged=True,original_GLRT_denominator_unchanged=True))
    return dict(case=case,offers=len(offered),models=sum(len(v) for r in rows for v in r['arms'].values()))


def main():
    runner.configure();OUT.mkdir(exist_ok=True)
    record=dict(cases=read(runner.RAW/'protocol.json')['cases'],source_sha256=sha(Path(__file__)),
        endpoint_leverage_at_least=.98,endpoint_gap_over_median_at_least=5,original_degree_at_least=3,
        core_BIC_order_must_drop=True,maximum_targets=3,minimum_core_span_s=6,
        prediction_families_only_from_independent_linear_groups=True,RF_position_fixed_to_original_incumbent=True,
        conditional_joint_density_control='full track versus core + one uniform-alias-period clutter point and multiplicity penalty; broad wrapped polynomial null also competes',
        no_GPS_future_TLE_or_point_deletion=True,diagnostics_only=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve endpoint diagnostic')
    write(OUT/'protocol.json',record)
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,record['cases']))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True))


if __name__=='__main__':main()
