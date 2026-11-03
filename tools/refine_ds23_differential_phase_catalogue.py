"""Exact-phase reranking of frozen full-catalogue differential proposals."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from functools import lru_cache
from pathlib import Path
import signal
import time
import numpy as np

from audit_ds23_differential_phase_tangents import frequencies
from ds23_exact_differential_phase import refine_pair
from ds23_causal_phase_location import adjust_means
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_sign_carrier_position import context_signed
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.research.retained_track_likelihood import PERIOD
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen

PARENT=ROOT/'reports/2026_10_22_ds23_exact_differential_phase'
OUT=PARENT/'refined'


@lru_cache(maxsize=2)
def context(case):
    scan,node,mask,powers,ordinary,hyper,entries,signed,signed_path=context_signed(case)
    widths,receipts=phase_widths(scan,list(range(len(scan.norads))));means=forecast_phase_mean(receipts,hyper['shrinkage'])
    if signed['accepted']:means=adjust_means(means,receipts,hyper,signed['selection'])
    return scan,np.asarray(means),np.asarray(widths)*hyper['multiplier'],signed


def one(item):
    case,group=item['case'],item['group'];path=OUT/(group+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s exact-phase group cap')));signal.alarm(180)
    try:
        root=Path(item['source']);old=read(root/'catalogue'/(group+'.json'));evaluation=read(root/'evaluation.json');protocol=read(root/'protocol.json')
        ids={j['probe'] for j in protocol['jobs'] if j['group']==group}
        rows=sorted([r for r in evaluation['rows'] if r['case']==case and r['probe'] in ids and r['status']=='complete' and r['two_components_qualified']],key=lambda r:r['time_s'])
        stat=next(r for r in evaluation['summary'] if r['group']==group)['RF_qualified_statistics']
        times=np.array([r['time_s'] for r in rows]);values=np.array([r['refined_second_value']-r['refined_first_value'] for r in rows])
        noise=stat['difference_sigma_hz'];lane=next(r['lane'] for r in protocol['selected'] if r['group']==group)
        scan,means,widths,signed=context(case);results={}
        for position_name,oldresult in old['results'].items():
            position=np.zeros(2) if position_name=='regional_centre' else np.asarray(signed['policy_arms']['c0']['endpoint_east_north_km'])
            candidates=[]
            for rank,proposal in enumerate(oldresult['candidates']):
                labels=np.array([proposal['first_index'],proposal['second_index']]);alias=proposal['difference_alias']
                def predict(phases):
                    f,_=frequencies(scan,labels,times,phases,position,lane[2]);return f[1]-f[0]
                fitted=refine_pair(values+alias*PERIOD,predict,means[labels],widths[labels],noise,
                    [proposal['phase_first_s'],proposal['phase_second_s']])
                diagnostics={k:v[0] for k,v in batch_noise_screen(np.asarray(fitted['residual_hz'])[None],times).items()}
                f,e=frequencies(scan,labels,times,fitted['phase_s'],position,lane[2])
                candidates.append(dict(proposal,old_rank=rank,old_tangent_score=proposal['score'],old_tangent_RMS_hz=proposal['RMS_hz'],
                    phase_first_s=float(fitted['phase_s'][0]),phase_second_s=float(fitted['phase_s'][1]),
                    relative_bias_hz=fitted['relative_bias_hz'],RMS_hz=fitted['RMS_hz'],score=fitted['local_Laplace_score'],
                    exact_fit=fitted,relative_residual_noise=diagnostics,above_horizon=bool(e.min()>=0)))
            eligible=[r for r in candidates if r['exact_fit']['valid_local_nomination'] and r['above_horizon']]
            eligible.sort(key=lambda r:r['score'])
            results[position_name]=dict(candidates=eligible,all_refined=candidates,
                visible_candidates=oldresult['visible_candidates'],ordered_distinct_pairs=oldresult['ordered_distinct_pairs'],
                finite_saved_proposal_pool_not_exhaustive_nonlinear_catalogue=True)
        result=dict(case=case,group=group,status='complete',results=results,lane=lane,noise_sigma_hz=noise,points=len(times),
            source=str(root),old_catalogue_sha256=sha(root/'catalogue'/(group+'.json')),
            original_data_priors_aliases_and_full_catalogue_proposal_pool_preserved=True,
            no_GPS_future_TLE_new_RF_or_new_position_result=True,physical_orbit_modes_omitted_from_nomination=True)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,group=group,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result)
    print(group,result['status'],result.get('error'),flush=True);return result


def main():
    OUT.mkdir(exist_ok=True);source=read(PARENT/'protocol.json');items=source['groups']
    protocol=dict(groups=items,source_protocol_sha256=sha(PARENT/'protocol.json'),
        same_RF_observations_noise_and_Gaussian_proposal_priors=True,relative_constant_sigma_hz=1000.,
        exact_two_phase_MAP_and_observed_Hessian_Laplace_score=True,phase_start_choices=['old tangent phase','causal forecast mean'],
        fixed_old_relative_aliases=True,maximum_phase_s=15,maximum_optimization_iterations=80,
        workers=12,per_group_seconds=180,regional_centre_and_current_RF_mode_are_separate_diagnostics=True,
        nomination_only_not_verified_identity_or_localization_gain=True,
        source_tools={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/ds23_exact_differential_phase.py']})
    path=OUT/'protocol.json'
    if path.exists() and read(path)!=protocol:raise ValueError('exact-phase reranking protocol changed')
    if not path.exists():write(path,protocol)
    with ProcessPoolExecutor(max_workers=12) as pool:rows=[f.result() for f in as_completed([pool.submit(one,r) for r in items])]
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,new_position_results_not_claimed=True))


if __name__=='__main__':main()
