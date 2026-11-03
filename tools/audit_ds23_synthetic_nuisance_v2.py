"""Independent endpoint replay, horizon checks and paired simulation figures."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import numpy as np

from run_algo01_ds23_sample import ROOT,read,write,sha
from run_ds23_synthetic_nuisance_v2 import OUT
from run_ds23_combined_recovery_full import context,ARMS,valid
from probe_ds23_frequency_events import parameters,summary,cached
from probe_ds23_synthetic_noise import perturb_tracks
from probe_ds23_synthetic_closure import generate
from ds23_synthetic_phase_law import bounded_phase_draw
from ds23_frequency_events import make_event_problem,attach_event_predictive
from ds23_predictive_linear import linear_geometry
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from prototype_dsx01_continuous_position import latlon


def replay_case(entries,site):
    import probe_ds23_synthetic_nuisance_components as component
    component.SITE=tuple(site);component.bounded_phase_draw=bounded_phase_draw
    case,draw=entries[0]['case'],entries[0]['draw']
    scan,node,mask,base,old=context(case);powers,means,hyper=parameters(scan,base,old)
    predictive=old['linear_entries'] if old['linear_paired_valid'] else []
    rows=[]
    for binding in entries:
        path=ROOT/binding['path']
        if sha(path)!=binding['sha256']:raise ValueError('sealed simulation changed')
        saved=read(path)
        if saved['status']!='complete':
            rows.append(dict(case=case,draw=draw,group=binding['group'],stratum=binding['stratum'],status=saved['status']))
            continue
        if binding['group']=='noise_only':
            synthetic,copied,entries_now,_=generate(scan,node,base,means,predictive,site);phases=means
        else:
            synthetic,copied,entries_now,truth=component.synthesize(scan,node,mask,base,powers,means,hyper,predictive,binding['group'],draw)
            for key in ('standard_normal_draw','selected_coefficients','true_phases_s','phase_prior_sigma_s'):
                np.testing.assert_allclose(truth[key],saved['generation_truth'][key],atol=1e-12,rtol=0)
            phases=np.asarray(truth['true_phases_s'])
        noise=perturb_tracks(synthetic,set(base.members)|{e['track_index'] for e in entries_now},194729+1009*draw+int(case.split('-')[1]))
        if noise!=saved['noise']:raise ValueError('common random observation noise changed')
        elevation=paired_phase_frequency(base.sky,base.flat_times,base.flat_labels,phases,*latlon(site))[1][mask]
        if predictive:
            view,_,_,_,_=linear_geometry(base,predictive)
            el=paired_phase_frequency(view.sky,view.flat_times,view.flat_labels,phases,*latlon(site))[1]
            elevation=np.r_[elevation,el]
        pair={}
        for arm in ARMS:
            r=saved['arms'][arm]
            p=make_event_problem(synthetic,copied,mask,arm,np.asarray(r['phase_reference']),powers,means,hyper,[])
            attach_event_predictive(p,entries_now,powers);cached(p)
            fresh=summary(p,np.asarray(r['endpoint_east_north_km']),entries_now)
            delta=float(fresh['negative_twice_elbo']-r['negative_twice_elbo'])
            if abs(delta)>1e-3:raise ValueError('synthetic RF objective replay differs')
            if fresh['linear_calibration_max_difference']!=0:raise ValueError('linear data changed calibration')
            for key in ('gates','linear_gates'):
                a=fresh[key]['tracks'] if key=='gates' else fresh[key]
                b=r[key]['tracks'] if key=='gates' else r[key]
                if [(t['component'],t['compatible']) for t in a]!=[(t['component'],t['compatible']) for t in b]:
                    raise ValueError('original synthetic gates changed')
            fresh['final_phase_change_s']=r['final_phase_change_s'];pair[arm]=fresh
            rows.append(dict(case=case,draw=draw,group=binding['group'],stratum=binding['stratum'],status='complete',arm=arm,
                error_km=r['synthetic_position_error_km'],endpoint=r['endpoint_east_north_km'],
                RF_objective_replay_difference=delta,minimum_true_elevation_deg=float(elevation.min()),
                all_true_observations_above_horizon=bool(elevation.min()>=0),
                residual_RMS_hz=fresh['RMS_hz']))
        if valid(pair)!=valid(saved['arms']):raise ValueError('paired original qualification changed')
    return rows


def main():
    protocol=read(OUT/'protocol.json');evaluation=read(OUT/'evaluation.json')
    if evaluation['protocol_sha256']!=sha(OUT/'protocol.json'):raise ValueError('evaluation protocol changed')
    for name,expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=expected:raise ValueError('simulation implementation changed')
    grouped={}
    for r in evaluation['receipts']:grouped.setdefault((r['case'],r['draw']),[]).append(r)
    rows=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(replay_case,v,protocol['site_by_case'][v[0]['case']]) for v in grouped.values()]
        for f in as_completed(futures):rows.extend(f.result())
    complete=[r for r in rows if r['status']=='complete'];matched=[]
    baseline={(r['case'],r['draw'],r['arm']):r for r in complete if r['group']=='noise_only'}
    for row in complete:
        old=baseline[(row['case'],row['draw'],row['arm'])]
        matched.append(dict(row,error_change_vs_same_noise_km=row['error_km']-old['error_km'],
            endpoint_shift_vs_same_noise_km=float(np.linalg.norm(np.asarray(row['endpoint'])-old['endpoint']))))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    groups=['noise_only','radio','smooth','orbit','fragment','phase','all']
    fig,axes=plt.subplots(1,2,figsize=(15,5.6),sharey=True)
    labels=['Noise','RX offsets\n+ drift','RX smooth','Orbital\nshape','Fragment\nbias','Phase','All']
    for ax,arm in zip(axes,ARMS,strict=True):
        for k,g in enumerate(groups):
            data=[r for r in matched if r['stratum']=='random_validation' and r['group']==g and r['arm']==arm]
            values=[r['error_km'] for r in data]
            if values:
                ax.scatter(k+np.linspace(-.13,.13,len(values)),values,s=16,alpha=.7,color='#197c91')
                ax.plot([k-.22,k+.22],[np.median(values)]*2,color='#c44c31',lw=2)
        ax.axhline(.5,ls='--',color='black',lw=.8)
        ax.set(xticks=range(len(groups)),xticklabels=labels,yscale='log',ylabel='Synthetic position error (km)',title=arm)
        ax.grid(alpha=.2)
    fig.suptitle('Conditional known-label simulation · 20 fixed random DS23 templates · matched noise draws\nStudent phase law matches the frozen unit-variance prior; red bars are medians; not real-data accuracy')
    fig.tight_layout();fig.savefig(OUT/'component_error_distributions.png',dpi=175);plt.close(fig)
    write(OUT/'independent_replay_audit.json',dict(rows=matched,evaluation_sha256=sha(OUT/'evaluation.json'),
        protocol_sha256=sha(OUT/'protocol.json'),audit_source_sha256=sha(Path(__file__)),
        successful_instance_arm_replays=len(complete),failed_instances=[r for r in rows if r['status']!='complete'],
        all_true_synthetic_observations_visible=all(r['all_true_observations_above_horizon'] for r in complete),
        maximum_RF_objective_replay_difference=max(abs(r['RF_objective_replay_difference']) for r in complete),
        no_real_GPS_or_new_RF_collection=True))
    print('INDEPENDENT_REPLAY_COMPLETE',len(complete),'arms; visibility failures',sum(not r['all_true_observations_above_horizon'] for r in complete),flush=True)


if __name__=='__main__':main()
