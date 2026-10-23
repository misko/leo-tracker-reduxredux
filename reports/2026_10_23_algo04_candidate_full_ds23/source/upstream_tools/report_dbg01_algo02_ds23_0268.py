"""DBG01 reporting and explicitly evaluation-centered diagnostic requests."""

import argparse
import csv
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

from debug_algo02_ds23_0268 import CASE,OUT,SOURCE,ARMS,STARTS,DISCOVERY_STARTS,context,build,fixed,entries_for
from dsx01_inference_audit import disk_grid
from prototype_dsx01_continuous_position import CENTER
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha

REFERENCE=(37.849061591561885,-122.48574968092912)
REFERENCE_XY=np.array([(REFERENCE[1]-CENTER[1])*111.32*np.cos(np.deg2rad(CENTER[0])),
                        (REFERENCE[0]-CENTER[0])*111])


def prepare():
    if OUT.exists():raise FileExistsError('preserve DBG01 evidence')
    OUT.mkdir();scan,node,keep,base,old=context()
    rows=list(csv.DictReader((SOURCE/'positions.csv').open()))
    fast=[r for r in rows if r['recording_format']=='short_window_iq_recording' and r['status']=='accepted']
    winners={a:max((r for r in fast if r['arm']==a),key=lambda r:float(r['error_km'])) for a in ARMS}
    assert all(r['case']==CASE for r in winners.values())
    axis,regional=disk_grid(step_km=1);local_axis=np.arange(-2,2.001,.25)
    local=REFERENCE_XY+np.array([(x,y) for y in local_axis for x in local_axis])
    assert np.all(abs(local)<=12.5)
    write(OUT/'request.json',dict(case=CASE,algorithm='ALGO02-v1',diagnostic_point=REFERENCE_XY,
        surface_points=np.vstack([regional,local]),regional_count=len(regional),regional_axis=axis,
        local_axis=local_axis,reference_xy=REFERENCE_XY,no_grid_points_clipped=True,
        regional_radius_km=10,regional_spacing_km=1,local_half_width_km=2,local_spacing_km=.25,
        GPS_used_only_for_explicit_diagnostic_views=True,production_initialization_unchanged=True))
    families=sorted({r['candidate_norad'] for r,sl in zip(base.rows,base.slices,strict=True) if keep[sl].any()})
    tracks=[r['component'] for r,sl in zip(base.rows,base.slices,strict=True) if keep[sl].any()]
    write(OUT/'interventions.json',dict(family=families,track=tracks,
        prior=['baseline','phase_x2','phase_zero_mean','bias1000','drift1','orbit3','smooth50'],
        controls_predeclared_before_this_case_results=True))
    files=['algo02_result.json','result.json','tracks.json','observations.json','radio_noise.json','receipt.json',
           'selected.tle','previous.tle','previous_receipt.json','preparation_receipt.json','bank.npz']
    write(OUT/'protocol.json',dict(case=CASE,algorithm='ALGO02-v1',worst_fast_selection=winners,
        benchmark_policy='original frozen ALGO02; experimental ALGO03 changes excluded',
        input_sha256={f:sha(SOURCE/CASE/f) for f in files},
        source_sha256={f:sha(ROOT/'tools'/f) for f in ['debug_algo02_ds23_0268.py','report_dbg01_algo02_ds23_0268.py']},
        center=CENTER,box_width_km=25,source_protocol_sha256=sha(SOURCE/'protocol.json'),
        standard='reports/DBG01/README.md',standard_sha256=sha(ROOT/'reports/DBG01/README.md'),
        workers=24,BLAS_threads_per_worker=1,starts=STARTS,discovery_starts=DISCOVERY_STARTS,
        phase_rounds=5,steps_per_round=48,discovery_budget=4,
        mask=keep,weights=old['weights'],node=node,
        no_new_RF_or_IQ_remeasurement=True,no_postscan_TLE=True,
        same_c0_fitted_c_observations_identities_aliases_priors_and_budgets=True))
    print(dict(case=CASE,families=len(families),tracks=len(tracks),surface_points=len(regional)+len(local),starts=len(STARTS)))


def save_csv(path,rows):
    with path.open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def memberships(audit,tracks):
    bykey={t['key']:t for t in tracks};out={}
    for arm in ARMS:
        rows=[];owned=set()
        for row in audit['arms'][arm]['associations']['tracks']:
            if not row['compatible']:continue
            ids=row.get('observation_ids',bykey[row['component']]['observation_ids'])
            if owned.intersection(ids):raise ValueError('duplicate association ownership')
            owned.update(ids);rows.append(dict(row,observation_ids=ids))
        out[arm]=dict(rows=rows,observation_ids=sorted(owned))
    return out


def glrt_figures(audit):
    observations=read(SOURCE/CASE/'observations.json');tracks=read(SOURCE/CASE/'tracks.json')
    scan=context()[0];curved_keys={scan.tracks[i]['key'] for i in scan.curved}
    raw={r['observation_id']:r for r in observations};member=memberships(audit,tracks)
    totals=[];trackrows=[]
    graph_ids={o for t in tracks for o in t['observation_ids']}
    for arm in ARMS:
        accepted={o:r['norad'] for r in member[arm]['rows'] for o in r['observation_ids']}
        sats=sorted(set(accepted.values()));colors={s:plt.colormaps['turbo']((i+.5)/len(sats)) for i,s in enumerate(sats)}
        for kind in ('associated','unassociated'):
            fig,axes=plt.subplots(4,4,figsize=(18,12),sharex=True)
            for rx in (1,2):
                for ch in range(1,9):
                    ax=axes[(rx-1)*2+(ch-1)//4,(ch-1)%4]
                    lane=[o for o in observations if o['receiver']==rx and o['channel']==ch]
                    ax.scatter([o['time_s'] for o in lane],[o['measured_cfo_hz']/1000 for o in lane],c='.85',s=5,rasterized=True)
                    for tindex,t in enumerate(tracks):
                        if t['receiver']!=rx or t['channel']!=ch:continue
                        ids=t['observation_ids'];selected=np.array([(o in accepted)==(kind=='associated') for o in ids])
                        if not selected.any():continue
                        times=np.array(t['times']);values=np.array(t['values'])
                        for piece in t['pieces']:
                            use=(times>=piece['start_s'])&(times<=piece['end_s'])
                            z=(times-piece['reference_time_s'])/piece['time_scale_s']
                            y=np.polynomial.legendre.legval(z,piece['coefficients_hz'])
                            native=np.array([raw[o]['measured_cfo_hz'] for o in ids]);y-=values-native
                            y[~(use&selected)]=np.nan;y[np.r_[False,abs(np.diff(y))>100000]]=np.nan
                            color=colors[accepted[ids[np.flatnonzero(selected)[0]]]] if kind=='associated' else plt.colormaps['tab20'](tindex%20)
                            ax.plot(times,y/1000,color=color,lw=1.1)
                    if kind=='associated':
                        for sat,color in colors.items():
                            marks=[o for o in lane if accepted.get(o['observation_id'])==sat]
                            ax.scatter([o['time_s'] for o in marks],[o['measured_cfo_hz']/1000 for o in marks],color=color,s=9)
                    else:
                        marks=[o for o in lane if o['observation_id'] not in accepted]
                        ax.scatter([o['time_s'] for o in marks],[o['measured_cfo_hz']/1000 for o in marks],color='crimson',s=9)
                    ax.set(title=f'RX{rx} CH{ch}',xlabel='Device time (s)',ylabel='Native CFO (kHz)');ax.grid(alpha=.2)
            fig.suptitle(f'{CASE} · ALGO02-v1 · {arm} · {kind} GLRT and graph polynomials\n'
                         'Gray = all winning GLRT; '+('color = accepted satellite hypothesis' if kind=='associated' else 'red = unassociated points; lines colored by graph track'))
            fig.tight_layout();fig.savefig(OUT/f'{kind}_GLRT_{arm}.png',dpi=145)
            if arm=='c0':fig.savefig(OUT/f'{kind}_GLRT.png',dpi=145)
            plt.close(fig)
        accepted_ids=set(accepted);unassociated=set(raw)-accepted_ids
        totals.append(dict(arm=arm,GLRT_points=len(raw),graph_points=len(graph_ids),graph_tracks=len(tracks),
            associated_points=len(accepted_ids),associated_percent=100*len(accepted_ids)/len(raw),
            associated_tracks=len(member[arm]['rows']),unassociated_points=len(unassociated),
            graph_owned_unassociated=len(unassociated&graph_ids),outside_graph=len(unassociated-graph_ids),
            calibration_points=audit['arms'][arm]['endpoint']['active_points']))
        for t in tracks:
            active=set(t['observation_ids'])&accepted_ids
            trackrows.append(dict(arm=arm,component=t['key'],receiver=t['receiver'],channel=t['channel'],
                points=len(t['times']),associated_points=len(active),unassociated_points=len(t['times'])-len(active),
                duration_s=t['end_s']-t['start_s'],active_curvature=t['key'] in curved_keys))
    write(OUT/'memberships.json',member);save_csv(OUT/'coverage.csv',totals);save_csv(OUT/'track_membership.csv',trackrows)
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,arm in zip(axes,ARMS,strict=True):
        data=audit['arms'][arm]['endpoint'];bykey={t['key']:t for t in tracks}
        for r in data['gates']['tracks']:
            t=bykey[r['component']]
            ax.scatter(t['end_s']-t['start_s'],r['conditional_residual_gate']['rms_hz'],s=max(15,r['points']),
                       color='tab:blue' if r['compatible'] else 'crimson',alpha=.6)
        ax.axhline(450,ls='--',color='grey');ax.set(title=arm,xlabel='Track duration (s)',ylabel='Conditional RMS (Hz)');ax.grid(alpha=.2)
    fig.suptitle(f'{CASE} · ALGO02 · original retained curved tracks; point area = sample count')
    fig.savefig(OUT/'track_residuals.png',dpi=160);plt.close(fig)
    return totals


def surfaces(audit):
    request=read(OUT/'request.json')
    rows=[r for i in range(24) for r in read(OUT/f'grid_{i:02d}.json')['rows']]
    rows.sort(key=lambda r:r['index'])
    assert len(rows)==len(request['surface_points']) and len({r['index'] for r in rows})==len(rows)
    fig,axes=plt.subplots(2,2,figsize=(13,11),layout='constrained')
    for col,arm in enumerate(ARMS):
        n=request['regional_count'];endpoint=audit['arms'][arm]['endpoint']
        for rowid,selected,axis,shift in [(0,rows[:n],np.array(request['regional_axis']),np.zeros(2)),
                (1,rows[n:],np.array(request['local_axis']),REFERENCE_XY)]:
            ax=axes[rowid,col];image=np.full((len(axis),len(axis)),np.nan)
            for r in selected:
                x=np.asarray(r['point'])-shift
                image[np.argmin(abs(axis-x[1])),np.argmin(abs(axis-x[0]))]=r['arms'][arm]['negative_twice_elbo']-endpoint['negative_twice_elbo']
            lo=float(np.nanmin(image));hi=float(np.nanpercentile(image,95))
            levels=np.linspace(min(0,lo),max(1,hi),24)
            contour=ax.contourf(axis,axis,image,levels=levels,cmap='viridis',extend='both')
            if lo<0<np.nanmax(image):ax.contour(axis,axis,image,levels=[0],colors='white',linewidths=1)
            dy,dx=np.gradient(image,axis,axis);norm=np.hypot(dx,dy);xx,yy=np.meshgrid(axis,axis)
            stride=2 if rowid==0 else 3;scale=.5 if rowid==0 else .16
            ax.quiver(xx[::stride,::stride],yy[::stride,::stride],
                (-dx/np.maximum(norm,1e-12)*scale)[::stride,::stride],
                (-dy/np.maximum(norm,1e-12)*scale)[::stride,::stride],
                angles='xy',scale_units='xy',scale=1,color='orange',width=.004)
            truth=REFERENCE_XY-shift;fitted=np.asarray(endpoint['endpoint_east_north_km'])-shift
            ax.scatter(*truth,marker='*',s=160,color='red',edgecolor='white',label='Reference (evaluation)',zorder=8)
            within=all(axis.min()<=v<=axis.max() for v in fitted)
            if within:ax.scatter(*fitted,marker='X',s=100,color='magenta',edgecolor='white',label='ALGO02 endpoint',zorder=9)
            else:ax.text(.03,.03,'ALGO02 endpoint outside this view',transform=ax.transAxes,color='white',fontsize=8,
                         bbox=dict(facecolor='black',alpha=.6,edgecolor='none'))
            if rowid==0:ax.add_patch(Circle((0,0),10,fill=False,ls='--',color='white',lw=1))
            ax.set(xlim=(axis.min()-.1,axis.max()+.1),ylim=(axis.min()-.1,axis.max()+.1),aspect='equal',
                xlabel='East from '+('regional center' if rowid==0 else 'reference')+' (km)',
                ylabel='North from '+('regional center' if rowid==0 else 'reference')+' (km)',title=arm)
            ax.legend(fontsize=7);fig.colorbar(contour,ax=ax,label='−2 ELBO minus saved endpoint')
    endpoint = audit['arms']['c0']['endpoint']
    fig.suptitle(f'{CASE} · ALGO02 · conditional phase-refreshed loss\n'
        f"Same {endpoint['active_points']:,} curved + {endpoint.get('predictive_points', 0):,} predictive points at each pixel; arrows show descent direction only")
    fig.savefig(OUT/'loss_gradient_10km.png',dpi=165);plt.close(fig)
    write(OUT/'surface_values.json',dict(rows=rows,full_pipeline_rerun_at_each_pixel=False,
        nuisance_and_group_precisions_refit=True,absolute_phase_refresh_rounds=5,
        fixed_labels_aliases_and_observations=True))


def restarts(audit):
    records=[read(OUT/f'restart_{i:02d}.json') for i in range(81)];rows=[]
    fig,axes=plt.subplots(1,2,figsize=(15,7),layout='constrained')
    for ax,arm in zip(axes,ARMS,strict=True):
        for r in records:
            a=r['arms'][arm];color=plt.colormaps['tab10'](a['final_mode']%10);start=np.asarray(r['start'])
            ax.scatter(*start,s=22,color='firebrick',edgecolor='black',lw=.4,zorder=4)
            ax.annotate(str(r['start_id']),start,xytext=(3,3),textcoords='offset points',fontsize=5.5)
            for h in a['history']:
                trace=np.asarray([v['point'] for v in h['descent']['trace']])
                if len(trace):ax.plot(trace[:,0],trace[:,1],color=color,alpha=.25,lw=.7)
            endpoint=a['endpoint_east_north_km'];ax.scatter(*endpoint,marker='x',s=35,color=color,zorder=6)
            rows.append(dict(start_id=r['start_id'],arm=arm,start_east_km=start[0],start_north_km=start[1],
                endpoint_east_km=endpoint[0],endpoint_north_km=endpoint[1],error_km=position_error(a['endpoint_latlon']),
                negative_twice_elbo=a['negative_twice_elbo'],final_mode=a['final_mode'],
                switches=sum(len(h['descent']['switches']) for h in a['history']),
                paired_gates_valid=r['paired_valid'],last_phase_change_s=a['final_phase_change_s'],
                numerical_stop=a['history'][-1]['descent']['stopped']))
        ax.scatter(*REFERENCE_XY,marker='*',s=220,color='limegreen',edgecolor='black',label='Reference (evaluation)',zorder=8)
        ax.add_patch(Circle((0,0),10,fill=False,ls='--',color='grey'));ax.grid(alpha=.2)
        ax.set(xlim=(-12.6,12.6),ylim=(-12.6,12.6),aspect='equal',title=arm,
               xlabel='East from regional center (km)',ylabel='North from regional center (km)');ax.legend(fontsize=8)
    bank=read(OUT/'hypothesis_bank.json')
    valid = sum(r['paired_valid'] for r in records)
    fig.suptitle(f'{CASE} · ALGO02 diagnostic · 81 starts in the 10 km disk · {valid}/81 pass paired gates\n'
        f"Curved identities/aliases reselected per accepted c0 step among {len(bank['nodes'])} complete-data hypotheses; predictive identities fixed")
    fig.savefig(OUT/'convergence_10km.png',dpi=170);plt.close(fig)
    save_csv(OUT/'restart_comparison.csv',rows)
    stats={}
    for arm in ARMS:
        selected=[r for r in rows if r['arm']==arm];xy=np.array([[r['endpoint_east_km'],r['endpoint_north_km']] for r in selected])
        stats[arm]=dict(error_range_km=[min(r['error_km'] for r in selected),max(r['error_km'] for r in selected)],
            endpoint_max_pairwise_distance_km=float(np.max(np.linalg.norm(xy[:,None]-xy[None,:],axis=2))),
            final_modes=sorted({r['final_mode'] for r in selected}),switches=sum(r['switches'] for r in selected),
            paired_valid_starts=sum(r['paired_gates_valid'] for r in selected),
            maximum_final_phase_change_s=max(r['last_phase_change_s'] for r in selected))
    write(OUT/'restart_summary.json',stats)
    return stats


def influence(audit):
    rows=[]
    for kind in ('family','track','prior'):
        for path in sorted(OUT.glob(kind+'_[0-9][0-9].json')):
            d=read(path)
            for arm,a in d['arms'].items():
                baseline=audit['arms'][arm]['endpoint']
                rows.append(dict(kind=kind,target=d['target'],arm=arm,error_km=position_error(a['endpoint_latlon']),
                    endpoint_shift_km=float(np.linalg.norm(np.asarray(a['endpoint_east_north_km'])-baseline['endpoint_east_north_km'])),
                    error_change_km=position_error(a['endpoint_latlon'])-position_error(baseline['endpoint_latlon']),
                    paired_gates_valid=d['paired_gates_valid'],deleted_curved_points=d['deleted_curved_points'],
                    deleted_predictive_points=d['deleted_predictive_points']))
    save_csv(OUT/'interventions.csv',rows)
    fig,axes=plt.subplots(1,3,figsize=(17,6),layout='constrained')
    for ax,kind in zip(axes,('family','track','prior'),strict=True):
        targets=list(dict.fromkeys(r['target'] for r in rows if r['kind']==kind))
        if kind=='track':
            targets=sorted(targets,key=lambda t:min(r['error_km'] for r in rows if r['target']==t))[:15]
        for offset,arm,color in [(-.12,'c0','tab:blue'),(.12,'fitted_c','tab:orange')]:
            selected=[next(r for r in rows if r['kind']==kind and r['target']==t and r['arm']==arm) for t in targets]
            y=np.arange(len(targets))+offset
            ax.scatter([r['error_km'] for r in selected],y,color=color,s=30,label=arm)
            bad=[i for i,r in enumerate(selected) if not r['paired_gates_valid']]
            ax.scatter([selected[i]['error_km'] for i in bad],y[bad],marker='x',s=65,color='crimson')
            ax.axvline(position_error(audit['arms'][arm]['endpoint']['endpoint_latlon']),color=color,ls='--',lw=1)
        labels=[str(t).replace(CASE+'-','').split('-RF')[0] for t in targets]
        ax.set_yticks(np.arange(len(targets)),labels,fontsize=8);ax.invert_yaxis();ax.grid(axis='x',alpha=.2)
        ax.set(xlabel='Post-fit position error (km)',title=kind+(' (15 lowest errors shown)' if kind=='track' else ''));ax.legend(fontsize=8)
    fig.suptitle(f'{CASE} · influence and generic controls; red × = fails paired gates\n'
        'Diagnostic deletions preserve original nuisance design; geographic improvement is not a rejection rule')
    fig.savefig(OUT/'influence_and_controls.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
    for ax,arm in zip(axes,ARMS,strict=True):
        e=audit['arms'][arm]['endpoint']['decomposition']['terms'];q=audit['arms'][arm]['diagnostic_point']['decomposition']['terms']
        keys=list(e);delta=[q[k]-e[k] for k in keys]
        ax.barh(keys,delta,color=['tab:red' if v>0 else 'tab:blue' for v in delta]);ax.axvline(0,color='black',lw=.8)
        ax.set(title=arm,xlabel='Reference minus endpoint contribution to −2 ELBO');ax.grid(axis='x',alpha=.2)
    fig.suptitle(f'{CASE} · objective decomposition; positive favors the displaced endpoint')
    fig.savefig(OUT/'loss_decomposition.png',dpi=165);plt.close(fig)
    return rows


def finish(audit,coverage,restart_stats,interventions):
    scan,node,keep,base,old=context();protocol=read(OUT/'protocol.json');bank=read(OUT/'hypothesis_bank.json')
    causal=next(r for r in read(SOURCE/'causal_audit.json')['cases'] if r['case']==CASE)
    assert causal['all_collection_and_encoded_epoch_causal']
    assert all(sha(SOURCE/CASE/name)==digest for name,digest in protocol['input_sha256'].items())
    assert len(list(OUT.glob('restart_[0-9][0-9].json')))==81
    assert len([r for r in interventions if r['kind']=='family'])==26
    assert len([r for r in interventions if r['kind']=='track'])==74
    assert len([r for r in interventions if r['kind']=='prior'])==14
    residual_rows=[]
    for arm in ARMS:
        e=audit['arms'][arm]['endpoint'];details={t['component']:t for t in e['tracks']}
        for g in e['gates']['tracks']:
            t=details[g['component']];diag=g['conditional_residual_gate']['diagnostics']
            residual_rows.append(dict(arm=arm,component=g['component'],norad=g['norad'],points=g['points'],
                compatible=g['compatible'],rms_hz=g['conditional_residual_gate']['rms_hz'],
                profile_rms_hz=g['profile_rms_hz'],profile_bias_hz=g['profile_bias_hz'],
                alias_changes=g['aliases_changed'],minimum_elevation_deg=t['minimum_elevation_deg'],
                maximum_independent_radio_standardized_residual=t['maximum_radio_standardized_residual'],
                **{k:v for k,v in diag.items() if k!='noise_screen_pass'},
                **{'profile_'+k:v for k,v in t['profile_noise'].items() if k!='noise_screen_pass'}))
    save_csv(OUT/'residual_diagnostics.csv',residual_rows)
    contributions=[]
    for arm in ARMS:
        e=audit['arms'][arm]['endpoint'];point=np.asarray(read(OUT/'request.json')['diagnostic_point'])
        ep=build(node,keep,arm,np.asarray(e['phase_reference']),entries_for(old))
        tp,_=fixed(node,keep,arm,point,entries_for(old));quantities=[]
        for p,x in [(ep,np.asarray(e['endpoint_east_north_km'])),(tp,point)]:
            c=p.calculate(x);trackterms={}
            for k,(row,sl) in enumerate(zip(p.rows,p.slices,strict=True)):
                active=keep[sl]
                if not active.any():continue
                count=int(active.sum());power=old['weights'][k];tau=c['noise_precision'][k]
                alpha=2+power*count/2;rate=alpha/tau
                r=c['conditional_residual_hz'][sl][active];sigma=p.point_noise[sl][active]
                trackterms[row['component']]=dict(norad=row['candidate_norad'],points=count,
                    noise_Gamma=float(2*alpha*(np.log(rate/2)+2/rate-1)),noise_precision=float(tau),
                    weighted_data=float(power*tau*np.sum((r/sigma)**2)))
            quantities.append(trackterms)
        group=[]
        for key,v in quantities[0].items():
            q=quantities[1][key]
            group.append(dict(arm=arm,component=key,norad=v['norad'],points=v['points'],endpoint=v,reference=q,
                noise_Gamma_delta=q['noise_Gamma']-v['noise_Gamma'],weighted_data_delta=q['weighted_data']-v['weighted_data']))
        expected=audit['arms'][arm]['diagnostic_point']['decomposition']['terms']['noise_Gamma']-e['decomposition']['terms']['noise_Gamma']
        assert abs(sum(r['noise_Gamma_delta'] for r in group)-expected)<1e-6
        contributions.extend(group)
    write(OUT/'track_loss_contributions.json',dict(rows=contributions,
        group_Gamma_differences_close_to_full_objective=True,not_a_complete_per_family_prior_allocation=True))
    validation=dict(case=CASE,algorithm='ALGO02-v1',worst_qualified_fast_in_both_c_arms=True,
        original_input_hashes_unchanged=True,source_protocol_sha256=protocol['source_protocol_sha256'],
        endpoint_normalized_loss_replay_differences={a:audit['arms'][a]['objective_replay_difference'] for a in ARMS},
        objective_decomposition_reconstruction_error={a:{k:audit['arms'][a][k]['decomposition']['reconstruction_error']
            for k in ('endpoint','diagnostic_point')} for a in ARMS},
        unique_physical_association_ownership=True,partial_masks_respected=True,
        reference_position_only_in_explicit_evaluation_requests=True,causal_TLE_audit=causal,
        source_freeze_of_original_ALGO02_independently_verified=True,
        starts_complete=81,regional_pixels=317,local_pixels=289,paired_family_ablations=13,
        paired_track_ablations=37,paired_prior_controls=7,
        no_new_RF_or_IQ_access=True,no_production_algorithm_changed=True,
        prior_control_correction='prior_control_correction.json; initial two incorrect sensitivity outputs explicitly superseded',
        final_tool_hashes={f:sha(ROOT/'tools'/f) for f in ['debug_algo02_ds23_0268.py','report_dbg01_algo02_ds23_0268.py']},
        no_claim_of_exhaustive_satellite_search_or_proven_bad_identity=True)
    write(OUT/'validation.json',validation)
    def tab(rows):
        return '| Intervention | c0 error km | Fitted-c error km | Paired gates |\n|---|---:|---:|---|\n'+''.join(
            f"| {target} | {a:.3f} | {b:.3f} | {'pass' if valid else 'fail'} |\n" for target,a,b,valid in rows)
    family_rows=[]
    for target in sorted({r['target'] for r in interventions if r['kind']=='family'},
                         key=lambda t:next(r['error_km'] for r in interventions if r['kind']=='family' and r['target']==t and r['arm']=='fitted_c')):
        r=[next(r for r in interventions if r['kind']=='family' and r['target']==target and r['arm']==a) for a in ARMS]
        family_rows.append((target,r[0]['error_km'],r[1]['error_km'],r[0]['paired_gates_valid']))
    controls=[]
    for target in read(OUT/'interventions.json')['prior']:
        r=[next(r for r in interventions if r['kind']=='prior' and r['target']==target and r['arm']==a) for a in ARMS]
        controls.append((target,r[0]['error_km'],r[1]['error_km'],r[0]['paired_gates_valid']))
    errors={a:position_error(audit['arms'][a]['endpoint']['endpoint_latlon']) for a in ARMS}
    gaps={a:audit['arms'][a]['diagnostic_point']['negative_twice_elbo']-audit['arms'][a]['endpoint']['negative_twice_elbo'] for a in ARMS}
    text=f'''# DBG01: ALGO02 on DS23-0268, the worst qualified fast scan

DS23-0268 (`{protocol['worst_fast_selection']['c0']['recording_id']}`) is the largest position error among the **198 qualified fast recordings**, in both c arms. Fast scans without qualified positions cannot be ranked by error and remain failures in the full 207-recording fast denominator. This case was selected using evaluation error for diagnosis, not algorithm tuning or a new validation sample.

The saved ALGO02-v1 result replays exactly: **{errors['c0']:.3f} km c0 and {errors['fitted_c']:.3f} km fitted c**. All 81 regional starts converge within 1 cm of their respective restart solutions (a numerical spread, not physical accuracy). A diagnostic refit initialized at the reference site also returns to the displaced basin. Under this finite hypothesis pool, initialization alone does not explain the error.

The reference-site nuisance fit is worse by **{gaps['c0']:.3f} / {gaps['fitted_c']:.3f} normalized loss units**. Its curved residual RMS is only about 2.2 Hz higher. The largest global decomposition difference is approximately 25 units in grouped-noise Gamma terms. This identifies where the model preference appears; it does not establish that robust noise inference is wrong.

Removing family **53923** reduces error to about 2.1 km but fails the original paired gates. Removing **63901** gives a valid 3.7–3.9 km result. No single-family deletion or declared generic control produces a demonstrated 0.5 km solution. Several pieces of evidence influence the bias; these diagnostics do not prove that a particular satellite identity or graph join is incorrect. No GPS-picked deletion or parameter setting is promoted.

## Inputs, replay and evidence coverage

The regional prior remains a 25 × 25 km box centered at `(37.906,-122.545)`, with normal inference initialized at `(0,0)` east/north. Reference `(37.849061591561885,-122.48574968092912)` is used only for error reporting and explicitly labeled oracle diagnostics. Satellite epoch and collection timestamp both precede cutoff `{causal['cutoff_utc_ns']}`; the existing causal audit checks {causal['latest_elements']} latest, {causal['previous_elements']} previous and {causal['historical_elements']} historical elements for this case. No following TLE, new RF collection or IQ remeasurement enters this analysis.

Both c arms use the same **3,165 original winning GLRT observations**, **2,786 graph-owned points in 88 graph tracks**, and **1,621 curved calibration points plus 211 predictive points**. Linear evidence carries shared calibration covariance and never calibrates nuisance coefficients at a fixed position. Each arm associates **1,832 points (57.88%) in 51 tracks**. Of 1,333 unassociated winners, **954 are graph-owned** and **379 lie outside graph tracks**. Association is not equivalent to position correctness.

![Associated GLRT and tracks](associated_GLRT.png)

![Unassociated GLRT and tracks](unassociated_GLRT.png)

Gray is all winning GLRT context. Red is unassociated. Lines are graph polynomial predictions, never extra observations; unassociated lines are colored by graph track. Exact observation IDs preserve partial masks. Companion [fitted-c associated](associated_GLRT_fitted_c.png) and [unassociated](unassociated_GLRT_fitted_c.png) plots and [track membership CSV](track_membership.csv) retain both arms. Native CFO axes include receiver offsets and alias branches without a display alignment.

![Retained-track residual RMS](track_residuals.png)

[Residual diagnostics](residual_diagnostics.csv) includes profile and conditional mean/slope, quadratic BIC, step and autocorrelation tests, alias changes, visibility and maximum radio-standardized residuals. Passing these screens does not prove identity or location.

## Conditional loss and actual restart paths

![Loss and gradient](loss_gradient_10km.png)

The upper views evaluate **317 points at 1 km spacing inside the 10 km regional disk**. The lower views evaluate **289 points at 0.25 km spacing over ±2 km around the evaluation reference**. No requested pixels are outside the original box. At each pixel the original labels, aliases, curved and predictive observations stay fixed, while nuisance means, robust noise variables and five absolute-prior phase-reference updates are recomputed. This is a conditional profiled loss, not a full acquisition/association rerun or a normalized probability map. Orange arrows indicate normalized descent direction; numerical 50 m central-difference gradients at the reference and endpoint are retained in [audit.json](audit.json).

![Regional restarts](convergence_10km.png)

Every red circle is a labeled start on the 2 km grid inside the disk. Lines show recorded accepted solver steps; crosses are endpoints. Thirteen cold discoveries at 5 km spacing plus original branches provide **{bank['raw_unique_hypotheses']} distinct whole-assignment hypotheses**. All fitted discovery positions, receiver coefficients and phases are discarded. **{len(bank['nodes'])} hypotheses retain the complete current predictive-family set** and enter the full-objective restart contest; **{len(bank['excluded'])} are excluded** because an original predictive satellite is absent from their curved state design. Those branches are not asserted to be physically impossible. Predictive identities remain fixed, curved identities/aliases can switch after each accepted c0 step, and fitted c follows the c0 branch chosen in each phase round. The objective comparison retains branch-dependent normalizations and visibility penalties. This is a finite conditional search, not exhaustive reassociation of every point against every TLE.

All 81 paired results pass the unchanged gates. Final selected branch is the incumbent for every start. The final error ranges are {restart_stats['c0']['error_range_km']} km c0 and {restart_stats['fitted_c']['error_range_km']} km fitted c. [Restart CSV](restart_comparison.csv) stores every start, endpoint, switch count, stop reason, phase change and gate outcome. Tiny differences from the original endpoint are numerical solver-path differences, not an accuracy improvement.

## All single-family and track ablations; generic priors

All **13 active families** and **37 retained curved tracks** are individually removed and refitted in both c arms, from the same regional center with five phase rounds and 48 position steps per round. Original nuisance design and prior support remain fixed. Family deletion also removes that family's predictive tracks. Raw objectives with different observation masks are not ranked as model evidence. Geographic errors are influence diagnostics only; remaining gate failures remain visible.

![Influence and controls](influence_and_controls.png)

The track panel displays the 15 lowest-error diagnostic deletions; [interventions.csv](interventions.csv) contains every result. Red crosses mark failures of paired acceptance gates.

'''+tab(family_rows)+'''
The generic controls double the current phase SD, remove its learned mean, enlarge the fragment-constant SD from 300 to 1000 Hz, reduce receiver mean drift SD from 10 to 1 Hz/s, scale the existing three orbit modes by three, or reduce smooth receiver SD from 200 to 50 Hz. Other data, priors, candidate sets and budgets remain matched. Two initial drift/smooth sensitivity outputs incorrectly changed physical design coordinates; they are preserved with `superseded_design_scaling` suffixes, explicitly excluded from all figures/tables, and rerun with latent-prior scaling. This experimental correction does not affect ALGO02 or any baseline, grid, restart, family or track result.

'''+tab(controls)+'''
## Why the displaced position is preferred

![Objective decomposition](loss_decomposition.png)

The bars compare the fixed reference fit against the saved endpoint with nuisance and phase updates in each. Weighted data fit, all latent nuisance-prior blocks, integrated log-volume, Gamma terms, full normalization and predictive evidence close to the actual objective difference within the recorded numerical tolerance. Phase prior cost is computed about its learned mean, not about zero. This prevents a nonzero learned mean being misreported as a penalty.

[Per-track contributions](track_loss_contributions.json) show that RX1 CH1 T002 (63901) and RX1 CH5 T003 (53923) each contribute about 7–8 units of the Gamma-term preference. These are correlated, jointly fitted residuals; the table is not a calibrated test of which transmitter or receiver is wrong. A modest aggregate RMS change can carry a much larger evidence difference through several long groups.

The strongest supported diagnosis is a conditional model minimum sustained by several influential track/family constraints. The present finite association search does not overturn it. Broader complete-data association alternatives and independent radio evidence remain useful follow-ups; this report does not claim an identity fix, track-join fix, or generalizable localization improvement.

## Reproduction and validation

Use the original on-disk ALGO02 authorities and the new tools with `PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1` and repository `.venv/bin/python`:

```text
tools/report_dbg01_algo02_ds23_0268.py --stage prepare
tools/debug_algo02_ds23_0268.py --stage audit
tools/debug_algo02_ds23_0268.py --stage discover
tools/debug_algo02_ds23_0268.py --stage bank
tools/debug_algo02_ds23_0268.py --stage analyze
tools/report_dbg01_algo02_ds23_0268.py --stage figures
```

Preserve completed outputs; use an isolated replay workspace for reconstruction. [Protocol](protocol.json) pins original inputs and initial tool hashes; [validation](validation.json) records final tool hashes, replay tolerances, counts and causal authority. [Prior correction receipt](prior_control_correction.json) records the sensitivity-only amendment. This adaptation was iteratively developed and is not claimed to be a pre-run seal of every reporting source version. Original frozen ALGO02 sources and all input hashes remain unchanged. Numeric artifacts remain local; no negative experiment is substituted into the published benchmark.
'''
    (OUT/'README.md').write_text(text)
    print(dict(report=str(OUT/'README.md'),validation='passed',coverage=coverage,restarts=restart_stats))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['prepare','figures'],required=True)
    args=parser.parse_args()
    if args.stage=='prepare':prepare()
    else:
        audit=read(OUT/'audit.json');coverage=glrt_figures(audit)
        if (OUT/'analyze_execution.json').exists():
            surfaces(audit);stats=restarts(audit);interventions=influence(audit)
            finish(audit,coverage,stats,interventions)


if __name__=='__main__':main()
