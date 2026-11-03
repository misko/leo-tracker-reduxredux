"""Geographic reporting for the three frozen family-position estimators."""

import argparse
import csv
from collections import Counter

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from evaluate_ds23_candidate_policies import metrics
from evaluate_ds23_causal_phase_location_full import capture_format
from probe_ds23_family_position_consensus import OUT,KINDS
from report_algo02_ds23 import position_error,REFERENCE
from prototype_dsx01_continuous_position import CENTER
from run_algo01_ds23_sample import ROOT,read,write,sha


def pilot_plot(out,case):
    directory=out/case;result=read(directory/'result.json');plan=read(directory/'plan.json')
    if not result['candidate_positions']:return
    folds=[read(directory/f'without_{j}.json') for j in plan['families']]
    truth=np.array([(REFERENCE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),
                    (REFERENCE[0]-CENTER[0])*111.0])
    fig,axes=plt.subplots(1,2,figsize=(13,6))
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        original=np.asarray(result['incumbent_arms'][arm]['endpoint_east_north_km'])
        deleted=np.array([r['arms'][arm]['endpoint_east_north_km'] for r in folds])
        ax.scatter(deleted[:,0],deleted[:,1],s=18,color='gray',label='Leave one family out')
        ax.scatter(*original,marker='D',s=65,color='#333333',label='Published incumbent')
        ax.scatter(*truth,marker='*',s=140,color='#e9a132',edgecolors='black',label='Evaluation coordinate')
        extent=np.vstack((deleted,original,truth))
        for kind,color in zip(KINDS,('#317bb2','#267b44','#a363a8'),strict=True):
            point=np.asarray(result['candidate_positions'][arm][kind])
            accepted=result['policies'][kind]['accepted']
            ax.scatter(*point,s=55,color=color,marker='o' if accepted else 'x',label=kind+(' (accepted)' if accepted else ' (rejected)'))
        lo=extent.min(axis=0)-.3;hi=extent.max(axis=0)+.3
        ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),title=arm,xlabel='East of regional centre (km)',ylabel='North of regional centre (km)')
        ax.grid(alpha=.15);ax.set_aspect('equal',adjustable='box');ax.legend(fontsize=7)
    fig.suptitle(case+': satellite-family deletion positions\nGPS is shown only by this reporter; rejected candidates never replace the incumbent')
    fig.tight_layout(rect=(0,0,1,.91));fig.savefig(out/(case+'_family_deletion_positions.png'),dpi=175);plt.close(fig)


def main(out=OUT):
    out=out.resolve()
    protocol,execution=read(out/'protocol.json'),read(out/'execution_cohort.json')
    if not execution['all_terminal'] or execution['errors'] or len(execution['final'])!=len(protocol['cases']):
        raise ValueError('complete error-free cohort required')
    if {r['case'] for r in execution['final']}!=set(protocol['cases']):raise ValueError('cohort coverage changed')
    for path,digest in protocol['source_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('frozen estimator changed')
    members={r['dataset_label']:r for r in read(ROOT/'reports/2026_10_18_ds23_post_ds22/manifest.json')['members']}
    rows=[];bindings={}
    for case in protocol['cases']:
        path=out/case/'result.json';result=read(path);bindings[case]=dict(path=str(path.relative_to(ROOT)),sha256=sha(path))
        if result['GPS_used'] or result['future_TLE_used']:raise ValueError('invalid inference source')
        for kind,policy in result['policies'].items():
            for arm in ('c0','fitted_c'):
                trial=policy['policy_arms'][arm];old=result['incumbent_arms'][arm]
                rows.append(dict(case=case,kind=kind,arm=arm,format=capture_format(members[case]['recording_format']),
                    accepted=policy['accepted'],folds_qualified=result['all_deletion_fits_qualified'],
                    families=result['held_family_count'],
                    original_error_km=position_error(result['baseline_arms'][arm]['endpoint_latlon']),
                    incumbent_error_km=position_error(old['endpoint_latlon']),
                    policy_error_km=position_error(trial['endpoint_latlon']),
                    RF_loss_change=trial['negative_twice_elbo']-old['negative_twice_elbo'],
                    RMS_hz=trial['RMS_hz']))
    summary={};positive={}
    for kind in KINDS:
        summary[kind]={}
        for group in ('all','fast','adaptive'):
            summary[kind][group]={}
            for arm in ('c0','fitted_c'):
                selected=[r for r in rows if r['kind']==kind and r['arm']==arm and (group=='all' or r['format']==group)]
                if not selected:continue
                summary[kind][group][arm]={name:metrics([r[name+'_error_km'] for r in selected]) for name in ('original','incumbent','policy')}
                summary[kind][group][arm]['accepted']=sum(r['accepted'] for r in selected)
        positive[kind]=all(summary[kind]['all'][a]['policy'][m]<summary[kind]['all'][a][reference][m]
            for a in ('c0','fitted_c') for m in ('mean_km','median_km') for reference in ('original','incumbent'))
    fitted_positive={kind:all(summary[kind]['all']['fitted_c']['policy'][m]<summary[kind]['all']['fitted_c'][reference][m]
        for m in ('mean_km','median_km') for reference in ('original','incumbent')) for kind in KINDS}
    write(out/'evaluation.json',dict(summary=summary,positive_development_by_prespecified_policy=positive,
        fitted_c_primary_positive_by_prespecified_policy=fitted_positive,
        stage=protocol.get('stage','development'),
        goal_achieved=False,full_413_position_goal_still_unverified=True,
        independent_confirmation_required_before_success_report=protocol.get('stage')!='disjoint_recording_confirmation',GPS_only_in_reporter=True,
        evidence=bindings))
    with (out/'positions.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        baseline=[r['incumbent_error_km'] for r in rows if r['arm']==arm and r['kind']=='mean']
        values=np.sort(baseline);ax.step(np.r_[0,values],np.r_[0,np.arange(1,len(values)+1)/len(values)],where='post',label='Published signed prior',color='black')
        for kind,color in zip(KINDS,('#317bb2','#267b44','#a363a8'),strict=True):
            values=np.sort([r['policy_error_km'] for r in rows if r['arm']==arm and r['kind']==kind])
            ax.step(np.r_[0,values],np.r_[0,np.arange(1,len(values)+1)/len(values)],where='post',label=kind,color=color)
        ax.axvline(.5,color='gray',ls=':');ax.set(title=arm,xlabel='Position error (km)',ylabel='Fraction of full cohort population',ylim=(0,1.02))
        ax.grid(alpha=.15);ax.legend(fontsize=8)
    fig.suptitle('DS23 family-position estimators: all original-data gates retained\nEvery rejected candidate falls back; all twenty recordings remain in each curve')
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(out/'position_error_distribution.png',dpi=175);plt.close(fig)
    pilot_plot(out,'DS23-0026' if 'DS23-0026' in protocol['cases'] else protocol['cases'][0])
    print('Positive development policies',positive,flush=True)
    print('Fitted-c primary positive',fitted_positive,flush=True)
    print({k:summary[k]['all'] for k in KINDS},flush=True)


if __name__=='__main__':
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('--run-dir',type=Path,default=OUT)
    main(parser.parse_args().run_dir)
