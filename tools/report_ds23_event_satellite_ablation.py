"""Report satellite influence separately from RF qualification and identity truth."""

import argparse
import csv
import itertools
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from ablate_ds23_frequency_event_satellites import OUT,MODELS,CASE
from probe_ds23_frequency_events import OUT as EVENTS,ARMS
from probe_algo03_frame_peak_recovery import context
from report_algo02_ds23 import position_error,REFERENCE
from prototype_dsx01_continuous_position import CENTER
from run_algo01_ds23_sample import read,write


def evaluation():
    rows=[]
    for model in MODELS:
        baseline=read(EVENTS/CASE/(model+'.json'))
        for path in sorted((OUT/model).glob('drop_*.json')):
            result=read(path)
            for arm in ARMS:
                saved=result['arms'][arm];origin=baseline['arms'][arm]
                error=position_error(saved['endpoint_latlon']);before=position_error(origin['endpoint_latlon'])
                failed=[r for r in saved['gates']['tracks']+saved['linear_gates'] if not r['compatible']]
                rows.append(dict(model=model,label=path.stem,arm=arm,
                    removed_norads=';'.join(map(str,result['norads'])),removed_components=';'.join(result['components']),
                    original_error_km=before,error_km=error,error_reduction_km=before-error,
                    paired_valid=result['paired_valid'],failed_tracks=len(failed),
                    failed_components=';'.join(r['component'] for r in failed),
                    removed_curved_points=result['removed_curved_points'],removed_predictive_points=result['removed_predictive_points'],
                    remaining_curved_points=result['remaining_curved_points'],remaining_predictive_points=result['remaining_predictive_points'],
                    event_amplitude_hz=saved['event_amplitudes_hz'][0],
                    east_km=saved['endpoint_east_north_km'][0],north_km=saved['endpoint_east_north_km'][1]))
    with (OUT/'ablation_metrics.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write(OUT/'evaluation.json',dict(case=CASE,rows=rows,
        lower_position_error_is_influence_diagnostic_not_identity_proof=True,
        invalid_fits_never_count_as_accepted_fixes=True,
        losses_on_different_observation_masks_are_not_compared=True))
    return rows


def followup(rows):
    singles=[r for r in rows if r['model']=='receiver_reentry' and r['arm']=='c0' and
             r['removed_norads'] and ';' not in r['removed_norads'] and not r['removed_components']]
    top=sorted(singles,key=lambda r:r['error_reduction_km'],reverse=True)[:3]
    scan,node,_,base,old=context(CASE);saved=read(EVENTS/CASE/'receiver_reentry.json');mask=np.asarray(saved['mask'],bool)
    jobs=[]
    for pair in itertools.combinations([int(r['removed_norads']) for r in top],2):
        jobs.append(dict(model='receiver_reentry',norads=list(pair)))
    for row in top[:2]:
        norad=int(row['removed_norads'])
        receiver_components={1:[],2:[]}
        for r,sl in zip(base.rows,base.slices,strict=True):
            if r['candidate_norad']==norad and mask[sl].any():
                jobs.append(dict(model='receiver_reentry',components=[r['component']]))
                index=next(i for i,t in enumerate(scan.tracks) if t['key']==r['component'])
                receiver_components[scan.tracks[index]['receiver']].append(r['component'])
        for rx,components in receiver_components.items():
            if len(components)>1 and len(components)<sum(map(len,receiver_components.values())):
                jobs.append(dict(model='receiver_reentry',components=components,
                                 description=f'family {norad} RX{rx} block'))
    write(OUT/'followup_request.json',dict(jobs=jobs,
        selected_families=[int(r['removed_norads']) for r in top],
        targets_selected_from_geographic_influence_for_explicit_debugging_only=True,
        not_an_RF_inference_or_operational_deletion_rule=True))
    print('Follow-up families:',[r['removed_norads'] for r in top],'; jobs',len(jobs),flush=True)


def save(fig,name):
    fig.savefig(OUT/(name+'.png'),dpi=185,bbox_inches='tight');fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight');plt.close(fig)


def followup_figure(rows):
    labels={'drop_53923':'All 53923', 'drop_63901':'All 63901', 'drop_69445':'All 69445',
            'drop_53923_63901':'53923 + 63901', 'drop_53923_69445':'53923 + 69445',
            'drop_63901_69445':'63901 + 69445',
            'drop_track_RX1-CH5-T003':'53923: RX1 CH5 T003',
            'drop_block_763af2959913':'53923: RX1 pair',
            'drop_block_85f65eac335d':'53923: RX2 quartet'}
    selected=[next(r for r in rows if r['model']=='receiver_reentry' and r['arm']=='c0' and r['label']==key)
              for key in labels]
    fig,ax=plt.subplots(figsize=(12,7));y=np.arange(len(selected));height=.34
    for k,arm,color in ((0,'c0','#257c85'),(1,'fitted_c','#9c529e')):
        data=[next(r for r in rows if r['model']=='receiver_reentry' and r['arm']==arm and r['label']==s['label']) for s in selected]
        bars=ax.barh(y+(k-.5)*height,[r['error_km'] for r in data],height,color=color,label=arm)
        for bar,row in zip(bars,data,strict=True):
            if not row['paired_valid']:bar.set_hatch('///');bar.set_alpha(.35)
            ax.text(row['error_km']+.04,bar.get_y()+bar.get_height()/2,f"{row['error_km']:.2f}"+
                    (' FAIL' if not row['paired_valid'] else ''),va='center',fontsize=8)
    ax.axvline(selected[0]['original_error_km'],color='black',ls='--',lw=1,label='Complete model c=0')
    ax.set_yticks(y,[labels[r['label']] for r in selected]);ax.invert_yaxis()
    ax.set_xlim(0,6.7);ax.set_xlabel('Position error after deletion and cold refit (km)');ax.grid(axis='x',alpha=.15)
    ax.set_title('DS23-0268 · Family, receiver and track influence\nHatched rows fail paired acceptance; lower error alone does not validate a repair')
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.1),ncol=3);fig.tight_layout();save(fig,'targeted_followup_ablation')


def gate_audit():
    """Replay saved endpoints and distinguish local residual failure from lost support."""
    from ablate_ds23_frequency_event_satellites import removal_mask
    from probe_ds23_frequency_events import parameters
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from leo.analysis.research.retained_track_likelihood import profile,whitening
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    scan,node,_,base,old=context(CASE);saved=read(EVENTS/CASE/'receiver_reentry.json')
    powers,means,hyper=parameters(scan,base,old);entries=old['linear_entries'];audits=[]
    for label in ('drop_53923','drop_track_RX1-CH7-T001'):
        result=read(OUT/'receiver_reentry'/(label+'.json'))
        mask,predictive=removal_mask(base.rows,base.slices,saved['mask'],entries,result['norads'],result['components'])
        for arm in ('c0','fitted_c'):
            record=result['arms'][arm];x=np.asarray(record['endpoint_east_north_km'])
            p=make_event_problem(scan,node,mask,arm,np.asarray(record['phase_reference']),powers,means,hyper,saved['events'])
            attach_event_predictive(p,predictive,powers);state=p.state(x);frequency,elevation=p.conditional_frequency(x)
            gates={r['component']:r for r in record['gates']['tracks']}
            for row,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
                active=p.keep[sl]
                if row['candidate_norad']!=63901 or not active.any():continue
                t=scan.tracks[i];q=t['rf_hz']/11.5e9;times=t['times'][active]
                y=t['values']-scan.hardware(t,state['beta'])-q*scan.rx_basis[i]@state['smooth'][t['receiver']-1]
                terms=profile(y[active],q*frequency[sl][active],*whitening(times))
                noise=batch_noise_screen(terms['innovations'],times);gate=gates[t['key']]
                checks=dict(profile_rms=bool(terms['rms'][0]<=450),profile_bias=bool(abs(terms['bias'][0])<=3000),
                    profile_noise=bool(noise['noise_screen_pass'][0]),conditional=gate['conditional_residual_gate']['compatible'],
                    alias=bool(int(terms['alias'][0])==alias),visible=bool(elevation[sl][active].min()>=0))
                audits.append(dict(deletion=label,arm=arm,component=t['key'],checks=checks,
                    local_checks_pass=all(checks.values()),final_compatible=gate['compatible'],
                    support_only_failure=bool(all(checks.values()) and not gate['compatible']),
                    profile_noise=noise,conditional=gate['conditional_residual_gate']))
    write(OUT/'gate_support_audit.json',dict(rows=audits,saved_endpoint_replay_no_new_optimization=True))
    inventory=[]
    for row,sl in zip(base.rows,base.slices,strict=True):
        active=np.asarray(saved['mask'],bool)[sl]
        if row['candidate_norad'] not in (53923,63901) or not active.any():continue
        t=next(t for t in scan.tracks if t['key']==row['component']);times=t['times'][active]
        inventory.append(dict(component=t['key'],norad=row['candidate_norad'],receiver=t['receiver'],channel=t['channel'],
            points=int(active.sum()),start_s=float(times.min()),end_s=float(times.max())))
    write(OUT/'influential_track_inventory.json',dict(rows=inventory))


def figures(rows):
    fig,axes=plt.subplots(2,1,figsize=(16,11))
    for ax,model in zip(axes,MODELS,strict=True):
        selected=[r for r in rows if r['model']==model and r['arm']=='c0' and r['removed_norads'] and ';' not in r['removed_norads']]
        selected.sort(key=lambda r:r['error_km']);x=np.arange(len(selected));width=.37
        for k,arm,color in ((0,'c0','#257c85'),(1,'fitted_c','#9c529e')):
            data=[next(r for r in rows if r['model']==model and r['arm']==arm and r['label']==s['label']) for s in selected]
            bars=ax.bar(x+(k-.5)*width,[r['error_km'] for r in data],width,color=color,alpha=.85,label=arm)
            for bar,row in zip(bars,data,strict=True):
                if not row['paired_valid']:
                    bar.set_hatch('///');bar.set_alpha(.35)
                    ax.plot(bar.get_x()+bar.get_width()/2,row['error_km'],'rx',ms=7)
        baseline=selected[0]['original_error_km']
        ax.axhline(baseline,color='black',ls='--',lw=1,label=f'Full model c=0: {baseline:.3f} km')
        ax.set_xticks(x,[r['removed_norads'] for r in selected],rotation=45)
        ax.set_ylabel('Remaining-fit position error (km)');ax.set_xlabel('Removed NORAD family')
        ax.set_title('Shared receiver-step model'+(' + independent 67935 re-entry' if model=='receiver_reentry' else ''))
        ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True);ax.legend(fontsize=9)
    fig.suptitle('DS23-0268 · Remove one satellite family at a time, then cold-refit position\n'
                 'Hatched bars / red crosses fail the original paired gates; they are not accepted repairs',fontsize=14)
    fig.tight_layout(rect=(0,0,1,.94));save(fig,'single_satellite_ablation')

    model='receiver_reentry';baseline=read(EVENTS/CASE/(model+'.json'))
    reference=np.array([(REFERENCE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),(REFERENCE[0]-CENTER[0])*111.0])
    selected=[r for r in rows if r['model']==model and r['arm']=='c0' and r['removed_norads'] and ';' not in r['removed_norads']]
    fig,ax=plt.subplots(figsize=(10,9));origin=np.array(baseline['arms']['c0']['endpoint_east_north_km'])-reference
    ax.scatter([0],[0],marker='*',s=220,color='black',label='Evaluation reference only',zorder=5)
    ax.scatter(*origin,marker='X',s=130,color='#d83252',label='Complete model',zorder=5)
    for k,row in enumerate(sorted(selected,key=lambda r:r['error_km'])):
        point=np.array([row['east_km'],row['north_km']])-reference
        color=plt.get_cmap('tab20')(k)
        ax.plot([origin[0],point[0]],[origin[1],point[1]],color=color,alpha=.5,lw=1)
        ax.scatter(*point,color=color,s=65,marker='o' if row['paired_valid'] else 'x')
        if int(row['removed_norads']) in (53923,63901,69445,61977,63913,64908):
            ax.annotate(row['removed_norads'],point,xytext=(5,5),textcoords='offset points',fontsize=9,color=color)
    ax.add_patch(plt.Circle((0,0),.5,fill=False,ls='--',color='black',lw=1))
    ax.axhline(0,color='gray',lw=.5);ax.axvline(0,color='gray',lw=.5);ax.grid(alpha=.18);ax.set_aspect('equal');ax.set_xlim(-3.5,3.5)
    ax.set_xlabel('East from evaluation reference (km)');ax.set_ylabel('North from evaluation reference (km)')
    ax.set_title('Which family moves the estimate?\nCircles pass paired gates; crosses fail · c = 0')
    ax.legend(fontsize=9,loc='upper left');fig.tight_layout();save(fig,'ablation_position_vectors')

    single_results=[read(path) for path in sorted((OUT/model).glob('drop_*.json'))
                    if len(read(path)['norads'])==1 and not read(path)['components']]
    families=sorted({n for r in single_results for n in r['norads']})
    matrix=np.zeros((len(families),len(families)),int)
    for result in single_results:
        i=families.index(result['norads'][0]);failures={}
        for arm in ARMS:
            for track in result['arms'][arm]['gates']['tracks']:
                if not track['compatible']:failures.setdefault(track['component'],track['norad'])
        for norad in failures.values():
            if norad in families:matrix[i,families.index(norad)]+=1
    fig,ax=plt.subplots(figsize=(11,9));im=ax.imshow(matrix,cmap='Reds',vmin=0,vmax=max(1,int(matrix.max())))
    for i,j in np.argwhere(matrix>0):ax.text(j,i,str(matrix[i,j]),ha='center',va='center',fontsize=9)
    ax.set_xticks(range(len(families)),families,rotation=60);ax.set_yticks(range(len(families)),families)
    ax.set_xlabel('Remaining satellite family with a failing curved track');ax.set_ylabel('Deleted family')
    ax.set_title('Cross-family tensions after deletion\nCount each remaining failed track once across the two c arms')
    fig.colorbar(im,ax=ax,label='Failed curved tracks');fig.tight_layout();save(fig,'cross_family_gate_failures')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--followup',action='store_true');args=parser.parse_args()
    rows=evaluation()
    if args.followup:followup(rows)
    else:
        figures(rows);followup_figure(rows);gate_audit()
