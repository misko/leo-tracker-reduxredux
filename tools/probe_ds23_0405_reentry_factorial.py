"""Separate receiver-basis and inactive-curve selection changes on debug405."""

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor,as_completed
import signal
import time

import numpy as np

from probe_ds23_family_cavity_nominations import setup
from probe_ds23_family_cavity_position import fit_configuration,unused_count
from probe_ds23_owner_reentry import fine_view
from ds23_owner_reentry import strongest_per_owner
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_family_cavity import unused_student_gap
from audit_ds23_family_cavity import density
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import ROOT,read,write,sha

CASE='DS23-0405'
OUT=ROOT/'reports/2026_10_22_ds23_0405_reentry_factorial'
OLD=ROOT/'reports/2026_10_21_ds23_catalogue_reentry'
OLD_CASE=ROOT/'../../../../srv/bulk/leo/research/ds23-catalogue-reentry-20261021/DS23-0405.json'
# The historical artifact is on local bulk storage, outside the runtime corpus.
from pathlib import Path
OLD_CASE=Path('/srv/bulk/leo/research/ds23-catalogue-reentry-20261021/DS23-0405.json')


def prepare():
    path=OUT/'protocol.json'
    if path.exists():return read(path)
    old=read(OLD_CASE);authority=read(OLD/'independent_replay_evaluation.json')
    assert sha(OLD_CASE)==next(r['source_sha256'] for r in authority['receipts'] if r['case']==CASE)
    group=old['trials'][0]['group'];offers=[r['offer'] for r in old['trials']]
    tasks=[]
    for basis in ['original','fine']:
        tasks.append(dict(key=basis+'_none',basis=basis,curves='none',offer=None))
        for curves in ['owner','all']:
            for offer in offers:tasks.append(dict(key=basis+'_'+curves+'_'+str(offer['norad']),basis=basis,curves=curves,offer=offer))
    protocol=dict(case=CASE,scope='engineering factorial diagnostic, not a generalized policy',tasks=tasks,group=group,
        full_causal_catalogue_candidate_pool_reused_unchanged=True,source_old_case_sha256=sha(OLD_CASE),
        candidates_from_previous_RF_nomination_not_GPS=True,phase_and_orbit_shared_per_satellite=True,
        original_and_fine_receiver_basis_average_prior_variance_matched=True,
        every_original_active_GLRT_and_predictive_point_retained=True,new_curves_whole_not_truncated=True,
        no_loss_ranking_across_different_observation_masks=True,
        cold_start=[0,0],regional_width_km=25,phase_rounds=5,position_steps=48,
        same_original_Gamma_Student_fragment_and_orbit_priors=True,matched_c0_fitted_c=True,
        unchanged_original_paired_residual_gates=True,per_task_seconds=180,
        no_GPS_future_TLE_or_new_RF=True,source_tools_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_family_cavity_position.py']})
    write(path,protocol);return protocol


def context(task,protocol):
    d=setup(CASE);group=protocol['group']
    if task['curves']=='owner':group=strongest_per_owner(group,d['base'])
    rows=group['rows'] if task['curves']!='none' else []
    old_keep=d['keep'].copy();node=copy.deepcopy(d['node']);keep=old_keep.copy()
    if task['basis']=='fine':
        d['scan']=fine_view(d['scan']);node['seed']['state']['smooth']=np.zeros((2,d['scan'].rx_basis[0].shape[1])).tolist()
    if rows:
        aliases=dict(zip(protocol['group']['rows'],task['offer']['aliases'],strict=True))
        for k in rows:
            sl=d['base'].slices[k]
            if old_keep[sl].any():raise ValueError('factorial group contains original active observations')
            keep[sl]=True;node['seed']['rows'][k].update(candidate_index=task['offer']['candidate_index'],candidate_norad=task['offer']['norad'])
            node['aliases'][k]=aliases[k]
    labels=sorted({r['candidate_index'] for r in node['seed']['rows']});means=d['all_means'][labels]
    d.update(node=node,keep=keep,means=means)
    return d,old_keep,rows


def fit_task(task):
    path=OUT/(task['key']+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s factorial task cap')));signal.alarm(180)
    try:
        protocol=read(OUT/'protocol.json');assert sha(OLD_CASE)==protocol['source_old_case_sha256'];d,old_keep,rows=context(task,protocol)
        result=fit_configuration(d,d['node'],d['entries'],d['means']);result.update(status='complete',case=CASE,task=task,
            original_mask=old_keep,mask=d['keep'],powers=d['powers'],model=d['model'],selected_row_indices=rows,
            added_curved_points=int(d['keep'].sum()-old_keep.sum()))
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=CASE,task=task,status='failed',error=repr(exc))
    finally:signal.alarm(0)
    result['seconds']=time.monotonic()-began;write(path,result);return result


def audit_task(task):
    protocol=read(OUT/'protocol.json');saved=read(OUT/(task['key']+'.json'));assert saved['status']=='complete'
    d,original,rows=context(task,protocol);np.testing.assert_array_equal(saved['mask'],d['keep']);np.testing.assert_array_equal(saved['original_mask'],original)
    assert saved['node']==d['node'] and saved['entries']==d['entries'];np.testing.assert_array_equal(saved['powers'],d['powers']);assert saved['model']==d['model']
    checks=[];pair={}
    for arm,r in saved['arms'].items():
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,np.asarray(r['phase_reference']),d['powers'],d['means'],d['model'],[])
        attach_event_predictive(p,d['entries'],d['powers']);x=np.asarray(r['endpoint_east_north_km']);c=p.calculate(x)
        assert abs(c['negative_twice_elbo']-r['negative_twice_elbo'])<1e-6
        np.testing.assert_allclose(c['coefficient'],r['coefficient'],rtol=0,atol=1e-8)
        direct=density(d,p,x,d['means'],d['entries']);replay=summary(p,x,d['entries'])
        assert replay['gates']==r['gates'] and replay['linear_gates']==r['linear_gates']
        assert abs(c['negative_twice_elbo']-unused_count(p,d['entries'])*unused_student_gap(d['model']['nu'])-r['corrected_selection_loss'])<1e-6
        replay['final_phase_change_s']=r['final_phase_change_s'];pair[arm]=replay;checks.append(dict(arm=arm,**direct))
    assert bool(valid(pair) and all(r['final_phase_change_s']<=.01 for r in pair.values()))==saved['paired_valid']
    return dict(task=task['key'],checks=checks,all_passed=True,source_sha256=sha(OUT/(task['key']+'.json')),no_GPS=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['fit','audit'],required=True);parser.add_argument('--workers',type=int,default=14)
    args=parser.parse_args();OUT.mkdir(exist_ok=True);protocol=prepare();rows=[];function=fit_task if args.stage=='fit' else audit_task
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(function,t) for t in protocol['tasks']]):
            rows.append(f.result());write(OUT/(args.stage+'_progress.json'),dict(rows=rows,completed=len(rows),total=len(protocol['tasks'])))
    write(OUT/(args.stage+'_execution.json'),dict(rows=rows,all_terminal=True,all_passed=all(r.get('all_passed',r.get('status')=='complete') for r in rows),
        no_GPS_or_geographic_evaluation_yet=True))


if __name__=='__main__':main()
