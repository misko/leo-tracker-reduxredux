"""Independent RF densities, original gates and IDs for bounded013 recovery."""

from pathlib import Path
import numpy as np

import probe_ds23_iteration013_existing_recovery as binding
import probe_ds23_iteration013_supported_step as supported
from audit_ds23_family_cavity import density
from audit_ds23_joint_relative_position import absolute_features
from ds23_joint_relative_audit import expected_log_density
from ds23_frequency_events import make_event_problem,attach_event_predictive,event_design
from ds23_predictive_linear import linear_geometry
from probe_ds23_frequency_events import summary
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay,assert_linear_gate_replay
from leo.analysis.research.retained_track_likelihood import profile
from run_algo01_ds23_sample import read,write,sha

RAW=binding.runner.RAW


def independent_event_density(d,p,x):
    full=p.calculate(x);curved=p.curved_calculate(x) if d['entries'] else full
    intercept,u,_=absolute_features(p,x)
    rx=np.concatenate([np.full(len(p.scan.tracks[i]['times']),p.scan.tracks[i]['receiver']) for i in p.members])
    ch=np.concatenate([np.full(len(p.scan.tracks[i]['times']),p.scan.tracks[i]['channel']) for i in p.members])
    ev=event_design(p.flat_times,rx,ch,p.q*11.5e9,np.asarray(p.labels)[p.flat_labels],p.events);u=np.column_stack((u,ev))
    width=u.shape[1];begin=p.hardware.shape[1]+p.smooth.shape[1];mu=np.zeros(width);mu[begin:begin+len(p.labels)]=d['means']/p.phase_sigma
    scales=np.ones(width);scales[p.event_start-len(p.members):p.event_start]=.3;present=np.unique(p.noise_groups[p.keep])
    direct=expected_log_density((p.values-intercept)[p.keep],u[p.keep],p.point_noise[p.keep],p.noise_groups[p.keep],d['powers'][present],mu,scales,
        curved['coefficient'],curved['noise_precision'][present],curved['coefficient_prior_precision'],list(range(begin,begin+len(p.labels))),d['model']['nu'])
    delta=abs(direct['negative_twice_elbo']-curved['negative_twice_elbo'])
    if delta>2e-3 or direct['maximum_coefficient_normal_equation_error']>1e-4:raise ValueError('event expected density failed independent replay')
    predictive_delta=0.
    if d['entries']:
        view,values,sigma,groups,_=linear_geometry(p,d['entries']);vi,vu,_=absolute_features(view,x)
        vrx=np.concatenate([np.full(e['points'],p.scan.tracks[e['track_index']]['receiver']) for e in d['entries']]);vch=np.concatenate([np.full(e['points'],p.scan.tracks[e['track_index']]['channel']) for e in d['entries']])
        ve=event_design(view.flat_times,vrx,vch,view.q*11.5e9,np.asarray(p.labels)[view.flat_labels],p.events);vu=np.column_stack((vu,ve))
        residual=values-vi-vu@curved['coefficient'];cov=vu@direct['covariance_physical']@vu.T+np.diag(2*sigma**2)+300**2*(groups[:,None]==groups[None,:])
        objective=float(residual@np.linalg.solve(cov,residual)+np.linalg.slogdet(cov)[1]+len(values)*np.log(2*np.pi));predictive_delta=abs(objective-(full['negative_twice_elbo']-curved['negative_twice_elbo']))
        if predictive_delta>2e-3:raise ValueError('event dense predictive covariance failed independent replay')
    return dict(density_difference=delta,coefficient_equation_error=direct['maximum_coefficient_normal_equation_error'],predictive_dense_covariance_difference=predictive_delta)


def check(d,p,arm,saved,label):
    x=np.asarray(saved['endpoint_east_north_km']);c=p.calculate(x);delta=c['negative_twice_elbo']-saved['negative_twice_elbo']
    if abs(delta)>1e-5:raise ValueError('013 endpoint objective changed')
    audit=independent_event_density(d,p,x) if p.events else density(d,p,x,d['means'],d['entries'])
    replay=summary(p,x,d['entries']);assert_curved_gate_replay(saved['gates'],replay['gates'])
    for old,new,e,sl in zip(saved['linear_gates'],replay['linear_gates'],d['entries'],p.linear_slices,strict=True):
        raw=c['linear_raw_prediction_residual_hz'][sl];terms=profile(raw,np.zeros(len(raw)),*p.scan.white[e['track_index']],bias_sigma=300.)
        assert_linear_gate_replay(old,new,dict(rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0])))
    return dict(case=d['scan'].case,method=label,arm=arm,objective_difference=delta,all_original_gates_replayed=True,**audit)


def event_coverage(d,trial,arm,p):
    old=binding.runner.engine.baseline.build
    binding.runner.engine.baseline.build=lambda *_:p
    try:return binding.runner.engine.baseline.inventory(dict(d,arms=trial['arms']),arm)
    finally:binding.runner.engine.baseline.build=old


def main():
    binding.configure('paths');out=RAW/'recovery_endpoint_audit.json'
    if out.exists():raise FileExistsError('preserve013 numerical replay')
    rows=[];memberships=[]
    for case in read(RAW/'protocol.json')['cases']:
        original=binding.runner.engine.current_setup(case);d,cov,kind,_=binding.paths.paths.parent(case);folder=RAW/'graph_seeded_paths'
        records=list(read(folder/(case+'.json'))['methods'].items());constrained=read(RAW/'temporal_feasibility'/(case+'.json'))
        if 'arms' in constrained:records.append(('constrained',constrained))
        for method,t in records:
            if 'arms' not in t:continue
            fragments=t.get('selected_paths') or read(folder/(case+'_'+method+'_selection.json'))['selected']
            scan,entries=binding.paths.paths.native.append_native_paths(d['scan'],d['entries'],fragments,binding.paths.paths.native.receiver_basis(d['scan']));dd=dict(d,scan=scan,entries=entries)
            for arm,saved in t['arms'].items():
                p=binding.paths.paths.build(dd,kind,arm,saved['phase_reference']);rows.append(check(dd,p,arm,saved,'temporal_'+method))
                replay=binding.paths.paths.coverage(dd,kind,arm,saved)
                if set(replay['accepted_observation_ids'])!=set(t['coverage'][arm]['accepted_observation_ids']):raise ValueError('native013 membership changed')
        for i,t in enumerate(read(RAW/'point_rich_extra_curve'/(case+'.json'))['trials']):
            dd=dict(original,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries'])
            for arm,saved in t['arms'].items():
                p=binding.runner.engine.support.build(original,t['node'],dd['keep'],arm,saved['phase_reference'],dd['means']);rows.append(check(dd,p,arm,saved,'extra_'+str(i)))
        for variant,folder in [('default','shared_step'),('support','supported_shared_step')]:
            record=read(RAW/folder/(case+'.json'));initial=read(RAW/case/'inventory.json')['arms'];selection=[]
            for i,t in enumerate(record['trials']):
                dd=dict(original,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries']);coverage={}
                for arm,saved in t['arms'].items():
                    if variant=='support':p=supported.build(original,t,arm,saved['phase_reference'],t['events'])
                    else:
                        p=make_event_problem(dd['scan'],dd['node'],dd['keep'],arm,np.asarray(saved['phase_reference']),dd['powers'],dd['means'],dd['model'],t['events']);attach_event_predictive(p,dd['entries'],dd['powers'])
                    rows.append(check(dd,p,arm,saved,variant+'_step_'+str(i)));coverage[arm]=event_coverage(dd,t,arm,p)
                retained={a:set(initial[a]['accepted_observation_ids'])<=set(v['accepted_observation_ids']) for a,v in coverage.items()}
                if t['accepted'] and not all(retained.values()):raise ValueError('accepted event proposal loses an original accepted ID')
                selection.append(dict(trial=i,coverage=coverage,all_original_IDs_preserved=retained))
            memberships.append(dict(case=case,variant=variant,trials=selection))
    write(out,dict(rows=rows,memberships=memberships,all_passed=True,no_new_optimization_or_GPS=True,source_sha256=sha(Path(__file__))))
    print('013 independently audited endpoint arms',len(rows),flush=True)


if __name__=='__main__':main()
