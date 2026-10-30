"""Compare exact joint and factorized new-family evidence at a frozen RF solution."""
import argparse,hashlib,time
from pathlib import Path
import numpy as np
from scipy.linalg import block_diag,cho_solve
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from predictive_new_family import NewFamily
from leo.analysis.research.predictive_track import condition_coefficients,receiver_design,phase_mixture_evidence
from leo.analysis.research.joint_predictive_families import two_family_phase_evidence
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from ds23_predictive_linear import linear_geometry
from ds23_height_problem import geometry_features
from prototype_dsx01_continuous_position import latlon


def joint_inputs(families,p,x,powers,old_entries):
    c=p.curved_calculate(x) if old_entries else p.calculate(x);coef=c['coefficient'];u=c['features'][p.keep];groups=p.noise_groups[p.keep]
    w=np.asarray(powers)[groups]*c['noise_precision'][groups]/p.point_noise[p.keep]**2
    gram=np.diag(c['coefficient_prior_precision'])+u.T@(u*w[:,None]);cov=cho_solve((np.linalg.cholesky(gram),True),np.eye(len(gram)))
    mean=coef;posterior=cov
    if old_entries:
        view,y,sigma,g,_=linear_geometry(p,old_entries);geo=geometry_features(view,x,0.);h=geo['features']
        noise=np.diag(2*sigma*sigma)+300.**2*(g[:,None]==g[None,:])
        mean,posterior=condition_coefficients(coef,cov,h,y-view.q*geo['intercept']-h@coef,noise)
    designs=[];means=[];modes=[];visible=[]
    for family in families:
        if family.j in p.labels and any(r['candidate_index']==family.j and p.keep[sl].any() for r,sl in zip(p.rows,p.slices,strict=True)):
            raise ValueError('family already has active calibration data')
        if any(e['candidate_index']==family.j for e in old_entries):raise ValueError('family already has predictive data')
        receiver=np.concatenate([receiver_design(t['times'],t['rf_hz'],t['receiver'],t['channel'],family.scan.rx_basis[e['track_index']],fitted_c=p.fitted_c) for t,e in zip(family.tracks,family.entries,strict=True)])
        h=np.zeros((len(family.times),len(coef)));h[:,:receiver.shape[1]]=receiver;designs.append(h)
        f,e=paired_phase_frequency(family.bank,family.grid_times,family.grid_labels,family.phases,*latlon(x))
        uu=paired_frequency_modes(family.bank,family.modes,family.grid_times,family.grid_labels,family.phases,*latlon(x))
        means.append(h@mean+f.reshape(len(family.phases),-1)*family.q)
        modes.append(uu.reshape(len(family.phases),len(family.times),3)*family.q[None,:,None])
        visible.append(e.reshape(len(family.phases),-1).min(axis=1)>=0)
    h=np.concatenate(designs);base=block_diag(*(f.noise for f in families))+h@posterior@h.T
    return [f.values for f in families],means,base,modes,[f.logprior for f in families],visible


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);hashes={};targets=[];jobs=[]
    def load(path):hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();return read(path)
    for trial in args.trials:
        pr=load(trial/'protocol.json');c=load(trial/'control.json');a=load(trial/'new_family.json');audit=load(trial/'exact_owner_replay.json')
        if not(c['paired_valid'] and a['paired_valid'] and audit['all_verified']):raise ValueError('individually qualified native trials required')
        for path,digest in audit['source_hashes'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('changed source')
        if any(pr.get(k) for k in ('inactive_fragment_sources','graph_bundle_sources','measurement_refinements')):raise ValueError('native unchanged trials required')
        for folder in pr['validation']:
            r=load(Path(folder)/'result.json');load(Path(folder)/'protocol.json')
            if r['annotation']['status']!='conditionally_supported_identity':raise ValueError('supported causal identities required')
        targets.append(pr['targets']);jobs.append(pr['job'])
    if len(targets)!=2 or jobs[0]['job_id']!=jobs[1]['job_id']:raise ValueError('two families from the same scan required')
    if len({e['candidate_index'] for group in targets for e in group})!=2:raise ValueError('distinct families required')
    ids=[o for group in targets for e in group for o in e['observation_ids']]
    if len(ids)!=len(set(ids)):raise ValueError('overlapping target observations')
    inv=load(args.study/'all-large-track-recovery'/jobs[0]['job_id']/'inventory.json');d=context(inv)
    families=[NewFamily(d['scan'],group,d['model'],phase_step=args.phase_step,allow_uncalibrated_label=True) for group in targets]
    offsets=np.array([[0,0],[.1,0],[-.1,0],[0,.1],[0,-.1]])
    write(out/'protocol.json',dict(job=jobs[0],targets=targets,source_trials=list(map(str,args.trials)),source_hashes=hashes,
        phase_step_s=args.phase_step,offsets_km=offsets,position_source='saved RF incumbent per c arm; no GPS initialization',
        frozen_phase_reference=True,positions_refitted=False,causal_only=True,receiver_covariance_integrated_once=True,
        no_production_change=True))
    rows=[];centers={}
    for arm,(p,x) in d['problems'].items():
        centers[arm]=np.asarray(x);before=(p.curved_calculate(x) if d['entries'] else p.calculate(x))['coefficient'].copy()
        for offset in offsets:
            z=np.asarray(x)+offset
            if np.max(abs(z))>12.5:raise ValueError('local probe leaves regional box')
            began=time.monotonic();inputs=joint_inputs(families,p,z,d['powers'],d['entries']);joint=two_family_phase_evidence(*inputs)
            y,m,b,u,lp,v=inputs;n1=len(y[0]);individual=[]
            for k,sl in enumerate((slice(0,n1),slice(n1,len(b)))):
                score=phase_mixture_evidence(y[k],m[k],b[sl,sl],u[k],lp[k],v[k])['negative_twice_log_density']
                replay=families[k].evaluate(p,z,d['powers'],d['entries'])
                if abs(score-replay)>1e-6:raise ValueError('individual-family likelihood replay failed')
                individual.append(score)
            l1=np.linalg.cholesky(b[:n1,:n1]);l2=np.linalg.cholesky(b[n1:,n1:]);cross=np.linalg.solve(l2,np.linalg.solve(l1,b[:n1,n1:]).T).T
            row=dict(arm=arm,offset_km=offset,position_east_north_km=z,seconds=time.monotonic()-began,
                joint_score=joint['negative_twice_log_density'],factorized_score=sum(individual),individual_scores=individual,
                joint_minus_factorized=joint['negative_twice_log_density']-sum(individual),
                largest_cross_correlation=float(np.linalg.svd(cross,compute_uv=False)[0]),
                phase_marginals=joint['phase_marginals'],joint_map_phases_s=[float(f.phases[k]) for f,k in zip(families,joint['joint_map_indices'],strict=True)],
                phase_boundary_mass=[float(w[abs(f.phases)>=14.9].sum()) for f,w in zip(families,joint['phase_marginals'],strict=True)],
                orbital_map_mean=joint['orbital_map_mean'],phase_pair_count=joint['phase_pair_count'])
            rows.append(row);write(out/f'point-{len(rows):02d}.json',row)
            print(arm,offset.tolist(),round(row['seconds'],3),round(row['joint_minus_factorized'],6),flush=True)
        after=(p.curved_calculate(x) if d['entries'] else p.calculate(x))['coefficient'];np.testing.assert_array_equal(before,after)
    gradients={}
    for arm in centers:
        group=[r for r in rows if r['arm']==arm];gradients[arm]={key:[(group[1][key]-group[2][key])/.2,(group[3][key]-group[4][key])/.2] for key in ('joint_score','factorized_score')}
    write(out/'result.json',dict(rows=rows,gradients_per_km=gradients,centers=centers,
        all_individual_replays_verified=True,receiver_calibration_unchanged=True,position_inclusion_authorized=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--trials',type=Path,nargs=2,required=True);p.add_argument('--phase-step',type=float,default=.25)
    run(p.parse_args())
