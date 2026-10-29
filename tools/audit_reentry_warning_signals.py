"""RF-only retrospective warning signals; no GPS input and no acceptance changes."""
import argparse
from pathlib import Path
import numpy as np

from benchmark_graph_covariance import load_case, baseline_pair, support_recovery
from combined_family_reentry import build, ARMS
from debug_fast_graph_unassociated import read, write
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import geodetic_to_ecef_km, ecef_to_enu_matrix, look_angles


def angular_summary(target, peers):
    """Equal-family empirical angular ranks, not an antenna beam probability."""
    peers=np.asarray(peers,float);target=np.asarray(target,float)
    centre=peers.mean(axis=0);centre/=np.linalg.norm(centre)
    distances=np.rad2deg(np.arccos(np.clip(peers@centre,-1,1)))
    distance=float(np.rad2deg(np.arccos(np.clip(target@centre,-1,1))))
    nearest=float(np.rad2deg(np.arccos(np.clip(np.max(peers@target),-1,1))))
    return dict(centroid_distance_deg=distance,centroid_rank_percent=100*float(np.mean(distances<=distance)),
                nearest_peer_deg=nearest,peer_count=len(peers),peer_radii_deg=distances)


def direction(p,x,i,j):
    t=p.scan.tracks[i];times=np.array([t['times'][0],np.median(t['times']),t['times'][-1]])
    phase=np.asarray(p.state(x)['phases']);states=paired_phase_states(p.scan.sky,times,np.full(3,j),phase)
    ll=latlon(x);origin=geodetic_to_ecef_km(*ll,0.);matrix=ecef_to_enu_matrix(*ll)
    az,el,_,_=look_angles(*states,origin,matrix)
    delta=states[0]-np.asarray(origin);enu=delta@matrix.T;unit=enu/np.linalg.norm(enu,axis=1)[:,None]
    return dict(times_s=times,azimuth_deg=az,elevation_deg=el,unit_enu=unit)


def fixed_position(d,target,x):
    reference=np.zeros(len(d['means']))
    for _ in range(5):
        q=build(d,d['keep'],d['arm'],reference,target,300)
        c=q.calculate(x);phase=np.clip(q.state(x)['phases'][q.labels],-15,15)
        change=float(np.max(abs(phase-reference)));reference=phase
    return q,c,change


def run(args):
    result=read(args.study/args.case/'result.json')
    if result['status']!='accepted':raise ValueError('accepted reentry required')
    d=load_case(args.root,args.case);d,preceding,_=support_recovery(d,baseline_pair(d))
    target=result['proposal']['row'];sigma=result['selected_sigma_hz'];out=dict(case=args.case,proposal=result['proposal'],arms={})
    for arm in ARMS:
        d['arm']=arm;p,x=d['problems'][arm];j=p.rows[target]['candidate_index'];i=p.members[target]
        keep=d['keep'].copy();keep[p.slices[target]]=True
        r=result['policy'][arm];newx=np.array(r['endpoint_east_north_km'])
        q=build(d,keep,arm,np.array(r['phase_reference']),target,sigma);c=q.calculate(newx)
        assert abs(c['negative_twice_elbo']-r['negative_twice_elbo'])<1e-5
        nb=q.hardware.shape[1];ns=q.smooth.shape[1];begin=nb+ns;local=q.labels.index(j)
        latent=c['latent_coefficient'];standardized=latent*np.sqrt(c['coefficient_prior_precision'])
        phase=q.state(newx)['phases'][j];phase_z=float(abs(phase-d['means'][local])/q.phase_sigma[local])
        offset=float(c['coefficient'][-len(q.members)+target]*1000*sigma/300)
        target_sky=direction(q,newx,i,j)
        peer_sky=[];seen=set();target_rx=d['scan'].tracks[i]['receiver']
        for row,ix,sl in zip(p.rows,p.members,p.slices):
            family=row['candidate_index'];t=d['scan'].tracks[ix]
            if not p.keep[sl].any() or family==j or t['receiver']!=target_rx or family in seen:continue
            seen.add(family);sky=direction(p,x,ix,family)
            peer_sky.append(dict(norad=row['candidate_norad'],component=t['key'],**sky))
        angular=angular_summary(target_sky['unit_enu'][1],[s['unit_enu'][1] for s in peer_sky])
        peer_phases=[];peer_offsets=[]
        for kk,(row,sl) in enumerate(zip(p.rows,p.slices)):
            if not p.keep[sl].any():continue
            jj=row['candidate_index'];ll=q.labels.index(jj)
            peer_phases.append(abs(q.state(newx)['phases'][jj]-d['means'][ll])/q.phase_sigma[ll])
            peer_offsets.append(abs(c['coefficient'][-len(q.members)+kk])/.3)
        phase_rank=100*float(np.mean(np.asarray(peer_phases)<=phase_z))
        offset_rank=100*float(np.mean(np.asarray(peer_offsets)<=abs(offset)/sigma))
        orbit=standardized[begin+len(q.labels)+3*q.supported.index(j):begin+len(q.labels)+3*q.supported.index(j)+3] if j in q.supported else np.zeros(0)
        oldq,oldc,oldchange=fixed_position(d,target,x)
        displacedq,displacedc,newchange=fixed_position(d,target,newx)
        # Same old observations and priors, at two positions, with nuisance phase
        # independently refreshed. No target observations enter these scores.
        score_penalty=float(displacedc['negative_twice_elbo']-oldc['negative_twice_elbo'])
        unconstrained=read(args.study/args.case/'unconstrained.json')[arm]
        oldbeta=np.array(preceding[arm]['state']['beta']);newbeta=np.array(r['state']['beta'])
        raw_scores=[]
        for row,sl in zip(p.rows,p.slices):
            use=p.keep[sl]
            if not use.any():continue
            a=oldc['conditional_residual_hz'][sl][use];b=displacedc['conditional_residual_hz'][sl][use]
            raw_scores.append(dict(norad=row['candidate_norad'],component=row['component'],points=len(a),
                preceding_rms_hz=float(np.sqrt(np.mean(a*a))),displaced_rms_hz=float(np.sqrt(np.mean(b*b)))))
        gates=[]
        for stage in (unconstrained,r):
            g=next(z for z in stage['gates']['tracks'] if z['component']==result['proposal']['component'])
            gates.append({k:v for k,v in g.items() if k!='observation_ids'})
        out['arms'][arm]=dict(position_shift_km=float(np.linalg.norm(newx-x)),
            constraint_position_shift_km=float(np.linalg.norm(newx-unconstrained['endpoint_east_north_km'])),
            old_evidence_score_penalty=score_penalty,old_model_phase_changes_s=[oldchange,newchange],
            target_phase_s=phase,target_phase_prior_mean_s=d['means'][local],target_phase_sigma_s=q.phase_sigma[local],
            target_phase_scale_units=phase_z,target_phase_scale_rank_percent=phase_rank,
            target_effective_phase_prior_units=float(abs(standardized[begin+local])),
            target_constant_hz=offset,target_constant_scale_units=abs(offset)/sigma,target_constant_rank_percent=offset_rank,
            target_orbit_prior_norm=float(np.linalg.norm(orbit)),target_orbit_mode_count=len(orbit),
            receiver_drift_changes_hz_s=(newbeta[4:8]-oldbeta[4:8])/150,
            target_sky=target_sky,peer_sky=peer_sky,angular=angular,old_curve_residuals=raw_scores,
            unconstrained_target_gate=gates[0],accepted_target_gate=gates[1],minimum_gate_slack=r.get('minimum_gate_slack'))
    write(args.output,out);print(args.case,'complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','study','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--case',required=True);run(p.parse_args())
