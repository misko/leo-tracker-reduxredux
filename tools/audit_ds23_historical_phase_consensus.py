"""Independent chronology/orbit/endpoint audit, then report-only geography."""

from pathlib import Path
import numpy as np
from sgp4.api import Satrec

from ds23_frequency_events import make_event_problem,attach_event_predictive
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_frequency_events import summary
from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_historical_phase_consensus_v2 import OUT
from run_algo01_ds23_sample import read,write,sha
from run_ds23_combined_recovery_full import valid


def main():
    prior_path=OUT/'evaluation.json';position_path=OUT/'position/evaluation.json'
    prior=read(prior_path);position=read(position_path)
    checks=[];max_orbit_error=0.;max_endpoint_error=0.;endpoint_checks=0
    for saved in prior['rows']:
        history=read(Path(saved['history_path']));selection=saved['selection'];cutoff=history['cutoff_utc_ns']
        assert sha(Path(saved['history_path']))==saved['history_sha256']
        assert sha(Path(saved['forecast_path']))==saved['forecast_sha256']
        assert all(max(v['epoch'],v['collected_utc_ns'])<=cutoff
                   for versions in history['past_versions'].values() for v in versions)
        rows=saved['rows'];boundary=selection['boundary_ns']
        train=[r for r in rows if r['label_available_utc_ns']<=boundary and r['norad']%5!=0]
        future=[r for r in rows if r['target_utc_ns']>boundary and r['label_available_utc_ns']<=cutoff]
        held=[r for r in future if r['norad']%5==0]
        assert len(train)==selection['counts']['training']
        assert len(future)==selection['counts']['future_issue_and_label']
        assert len(held)==selection['counts']['satellite_disjoint_future']
        assert not ({i for r in train for i in r['reference_ids']}&{i for r in future for i in r['reference_ids']})
        original=read(Path(saved['forecast_path']))['transitions']
        prefix=[r for r in original if r['validation_time_ns']<=boundary and r['norad']%5!=0]
        assert len(prefix)==selection['counts']['original_training']
        candidates=selection['boundary_selection']['candidates']
        best=max(candidates,key=lambda r:(r['minimum_distinct_satellite_support'],r['minimum_total_row_support'],-r['boundary_ns']))
        assert best['boundary_ns']==boundary
        for r in [rows[k] for k in np.linspace(0,len(rows)-1,min(12,len(rows)),dtype=int)]:
            versions=history['past_versions'][str(r['norad'])]
            k=next(k for k,v in enumerate(versions) if v['collected_utc_ns']==r['target_utc_ns']
                   and v['epoch']==r['reference_epochs_ns'][0])
            chosen=versions[k-1:k+3];day=86_400_000_000_000;t=r['target_utc_ns']
            states=[Satrec.twoline2rv(*v['lines']).sgp4(2440587.5+t//day,(t%day)/day) for v in chosen]
            assert all(s[0]==0 for s in states)
            nominal=np.array(states[0][1]);velocity=np.array(states[0][2])
            phases=[float((np.array(s[1])-nominal)@velocity/(velocity@velocity)) for s in states[1:]]
            delta=float(np.max(abs(np.array(phases)-r['reference_phase_s'])))
            max_orbit_error=max(max_orbit_error,delta);assert delta<1e-7
            assert abs(np.median(phases)-r['consensus_phase_s'])<1e-7
            assert r['label_available_utc_ns']==chosen[-1]['collected_utc_ns']
        checks.append(dict(case=saved['case'],historical_rows=len(rows),strict_temporal_rows=len(future),
            held_satellite_rows=len(held),qualified=selection['qualified']))
    for result in position['rows']:
        assert result['status']=='complete'
        if not result['historical_prior_qualified']:continue
        scan,node,mask,powers,means,model,entries,incumbent,_=context_signed(result['case'])
        historical=next(r for r in prior['rows'] if r['case']==result['case'])
        for method,saved in result['results'].items():
            fit=historical['selection']['final_mean_models'][method]
            base=make_event_problem(scan,node,mask,'c0',np.zeros(len(means)),powers,means,model,[])
            _,receipts=phase_widths(scan,base.labels);changed=np.array(means,copy=True)
            for k,r in enumerate(receipts):
                old,gap=r['old_new_alignment_s'],r['previous_epoch_gap_s']
                if old is None or gap is None or gap<1:continue
                age=r['age_s']+150.;raw=-min(2.,max(0.,age/gap))*old
                feature={None:0.,'seconds':1.,'standardized':r['sigma_s']*model['multiplier'],
                         'age':age/43200.,'age_squared':(age/43200.)**2}[fit['kind']]
                limit=min(15.,3*r['sigma_s'])
                changed[k]=np.clip(fit['shrinkage']*raw+fit['coefficient']*feature,-limit,limit)
            np.testing.assert_allclose(changed,saved['modified_means_s'],rtol=0,atol=1e-12)
            assert saved['original_sigma_multiplier']==model['multiplier']
            assert saved['original_phase_tail_degrees']==model['nu']
            replay={}
            for arm,record in saved['arms'].items():
                p=make_event_problem(scan,node,mask,arm,np.array(record['phase_reference']),powers,changed,model,[])
                np.testing.assert_allclose(p.phase_sigma,base.phase_sigma,rtol=0,atol=0)
                attach_event_predictive(p,entries,powers)
                current=summary(p,np.array(record['endpoint_east_north_km']),entries)
                delta=abs(current['negative_twice_elbo']-record['negative_twice_elbo'])
                max_endpoint_error=max(max_endpoint_error,delta);assert delta<1e-6
                assert current['active_points']==record['active_points']
                current['final_phase_change_s']=record['final_phase_change_s']
                replay[arm]=current;endpoint_checks+=1
            assert valid(replay)==saved['accepted']
    # Coordinates are read for evaluation only after causal and numerical checks.
    from report_algo02_ds23 import position_error
    geography=[]
    for result in position['rows']:
        for method,saved in [('incumbent',dict(policy_arms=result['incumbent_arms']))]+list(result['results'].items()):
            for arm,r in saved['policy_arms'].items():
                geography.append(dict(case=result['case'],method=method,arm=arm,
                    error_km=position_error(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],
                    normalized_loss=r['negative_twice_elbo'],accepted=saved.get('accepted')))
    output=dict(checks=checks,orbit_projection_checks=sum(min(12,c['historical_rows']) for c in checks),
        maximum_orbit_phase_difference_s=max_orbit_error,replayed_endpoint_arms=endpoint_checks,
        maximum_normalized_endpoint_loss_difference=max_endpoint_error,all_checks_pass=True,
        geography=geography,reference_panels_remain_correlated_orbit_proxies=True,
        full_DS23_benchmark_changed=False,geography_used_for_inference_or_selection=False,
        prior_evaluation_sha256=sha(prior_path),position_evaluation_sha256=sha(position_path))
    write(OUT/'position/independent_audit.json',output)
    print({k:v for k,v in output.items() if k not in ('geography','checks')},flush=True)
    for r in geography:
        if r['case']=='DS23-0314':print(r,flush=True)


if __name__=='__main__':main()
