"""Replay hypothetical timing factors, densities, gates and paired fallbacks."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from scipy.special import gammaln,digamma

from ds23_phase_measurement_design import make_phase_measured_problem,attach_phase_measured_predictive
from probe_ds23_frequency_events import summary
from probe_ds23_synthetic_known_nuisance import setup,SOURCE
from probe_ds23_phase_measurement_design import OUT,BULK
from probe_ds23_phase_measurement_precision import BULK as FINER
from probe_ds23_phase_design_replication import BULK as REPLICATION
from run_ds23_combined_recovery_full import ARMS,valid
from run_algo01_ds23_sample import ROOT,read,write,sha


def independent_elbo(p,c,powers,means,hyper,measurements):
    """Expected log densities and entropies, separate from solver decomposition."""
    keep=np.asarray(p.keep,bool);_,g=np.unique(p.noise_groups[keep],return_inverse=True)
    present=np.unique(p.noise_groups[keep]);power=np.asarray(powers)[present]
    u=c['features'][keep];s=p.point_noise[keep];width=u.shape[1]
    scales=np.ones(width);scales[-len(p.members):]=.3
    offset=np.zeros(width);begin=p.hardware.shape[1]+p.smooth.shape[1]
    offset[begin:begin+len(p.labels)]=means/p.phase_sigma
    mu=(c['coefficient']-offset)/scales;cov=c['coefficient_covariance']
    a,b=c['noise_shape'],c['noise_rate'];pa,pb=c['prior_shape'],c['prior_rate']
    energy=c['conditional_residual_hz'][keep]**2+np.einsum('ij,jk,ik->i',u*scales,cov,u*scales)
    value=np.sum(power[g]*(np.log(2*np.pi*s*s)-digamma(a)[g]+np.log(b)[g]+(a/b)[g]*energy/s**2))
    d=np.zeros((len(measurements),width));sigma=np.array([r['sigma_s'] for r in measurements])
    for k,r in enumerate(measurements):
        index=p.labels.index(r['candidate_index']);d[k,begin+index]=p.phase_sigma[index]
    fixed_covariance=np.einsum('ij,jk,ik->i',d*scales,cov,d*scales)
    value+=np.sum(np.log(2*np.pi*sigma*sigma)+(c['phase_measurement_residual_s']**2+fixed_covariance)/sigma**2)
    precision=np.ones(width);elog=np.zeros(width)
    if hyper['nu'] is not None:
        precision[begin:begin+len(p.labels)]=pa/pb
        elog[begin:begin+len(p.labels)]=digamma(pa)-np.log(pb)
    value+=width*np.log(2*np.pi)-elog.sum()+precision@(mu**2+np.diag(cov))
    value-=width*(1+np.log(2*np.pi))+np.linalg.slogdet(cov)[1]
    def kl(a,b,a0,b0):
        return 2*((a-a0)*digamma(a)-gammaln(a)+gammaln(a0)+a0*np.log(b/b0)+a*(b0/b-1)).sum()
    value+=kl(a,b,2.,2.)
    if hyper['nu'] is not None:value+=kl(pa,pb,hyper['nu']/2,(hyper['nu']-2)/2)
    return float(value)


def one(case):
    protocol=read(OUT/'protocol.json');site=protocol['site_by_case'][case]
    scan,node,mask,powers,means,hyper,entries,truth,baseline=setup(case,site)
    sources=[]
    for directory in (BULK,FINER,REPLICATION):
        for path in directory.glob(case+'_*.json'):
            record=read(path)
            if 'arms' in record:sources.append((path,record))
    max_replay=max_elbo=max_factor=0.;count=0;rows=[];standardized=[]
    for path,record in sources:
        measurements=record['measurements'];draw=record.get('draw',0)
        noise=np.random.default_rng(194819+1009*draw+int(case.split('-')[1])).normal(size=len(means))
        labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
        for r in measurements:
            k=labels.index(r['candidate_index'])
            expected=truth['true_phases_s'][k]+r['sigma_s']*noise[k]
            assert abs(expected-r['phase_s'])<1e-12
        replay={}
        for arm,saved in record['arms'].items():
            p=make_phase_measured_problem(scan,node,mask,arm,np.array(saved['phase_reference']),powers,means,hyper,measurements)
            attach_phase_measured_predictive(p,entries,powers);x=np.array(saved['endpoint_east_north_km']);c=p.calculate(x)
            delta=abs(c['negative_twice_elbo']-saved['negative_twice_elbo']);max_replay=max(max_replay,delta);assert delta<1e-6
            expected=independent_elbo(p,c,powers,means,hyper,measurements)
            delta=abs(expected-c.get('curved_negative_twice_elbo',c['negative_twice_elbo']))
            max_elbo=max(max_elbo,delta);assert delta<1e-4
            residual=np.array([r['phase_s']-c['coefficient'][p.hardware.shape[1]+p.smooth.shape[1]+p.labels.index(r['candidate_index'])]*p.phase_sigma[p.labels.index(r['candidate_index'])] for r in measurements])
            delta=float(np.max(abs(residual-c['phase_measurement_residual_s']),initial=0))
            max_factor=max(max_factor,delta);assert delta<1e-12
            current=summary(p,x,entries);current['final_phase_change_s']=saved['final_phase_change_s']
            assert np.array_equal(mask,p.keep) and current['active_points']==baseline['arms'][arm]['active_points']
            assert current['linear_calibration_max_difference']==0
            assert [r['compatible'] for r in current['gates']['tracks']]==[r['compatible'] for r in saved['gates']['tracks']]
            replay[arm]=current;count+=1
            standardized.extend((residual/np.array([r['sigma_s'] for r in measurements])).tolist())
        accepted=valid(replay);assert accepted==record['paired_qualified']
        method=record.get('variant',record.get('setting','')+'/'+record.get('method',''))
        for arm,saved in record['arms'].items():
            old=baseline['arms'][arm]
            rows.append(dict(case=case,method=method,draw=draw,arm=arm,paired_valid=accepted,
                raw_error_km=saved['synthetic_position_error_km'],baseline_error_km=old['synthetic_position_error_km'],
                policy_error_km=saved['synthetic_position_error_km'] if accepted else old['synthetic_position_error_km'],
                frequency_RMS_hz=saved['RMS_hz'],baseline_RMS_hz=old['RMS_hz'],
                measurements=len(measurements),measurement_SD_s=measurements[0]['sigma_s'],
                source_path=str(path),source_sha256=sha(path)))
    return dict(case=case,endpoint_arms=count,maximum_objective_replay_difference=max_replay,
        maximum_independent_expected_log_density_difference=max_elbo,maximum_phase_factor_mapping_difference_s=max_factor,
        rows=rows,phase_factor_standardized_residuals=standardized)


def main():
    protocol=read(OUT/'protocol.json')
    execution=read(OUT/'noise_replication/execution.json')
    assert execution['all_terminal'] and execution['all_instances_complete']
    with ProcessPoolExecutor(max_workers=8) as pool:
        audits=[f.result() for f in as_completed([pool.submit(one,c) for c in protocol['cases']])]
    rows=[r for a in audits for r in a.pop('rows')];z=np.concatenate([a.pop('phase_factor_standardized_residuals') for a in audits])
    groups={}
    for r in rows:groups.setdefault((r['method'],r['draw'],r['arm']),[]).append(r)
    summaries=[]
    for (method,draw,arm),values in groups.items():
        errors=[v['policy_error_km'] for v in values];raw=[v['raw_error_km'] for v in values]
        summaries.append(dict(method=method,draw=draw,arm=arm,n=len(values),mean_km=float(np.mean(errors)),
            median_km=float(np.median(errors)),raw_mean_km=float(np.mean(raw)),
            paired_valid=sum(v['paired_valid'] for v in values)))
    assert len(rows)==1040  # (160 coarse +120 finer +240 replication) paired arms
    result=dict(audits=audits,rows=rows,summary=summaries,all_checks_pass=True,
        endpoint_arms=len(rows),independent_timing_noise_draws=3,independent_templates=20,
        source_protocol_sha256={str(p):sha(p) for p in [OUT/'protocol.json',OUT/'finer_precision/protocol.json',OUT/'noise_replication/protocol.json']},
        paired_gate_failures_use_exact_original_synthetic_incumbent=True,
        phase_factor_standardized_residual_mean=float(np.mean(z)),phase_factor_standardized_residual_RMS=float(np.sqrt(np.mean(z*z))),
        conditional_simulation_only=True,real_DS23_accuracy_gain=False,all_current_GPS_and_postscan_TLE_used=False)
    write(OUT/'independent_audit.json',result)
    print({k:v for k,v in result.items() if k not in ['audits','rows','summary']},flush=True)
    for r in summaries:
        if r['arm']=='fitted_c':print(r,flush=True)


if __name__=='__main__':main()
