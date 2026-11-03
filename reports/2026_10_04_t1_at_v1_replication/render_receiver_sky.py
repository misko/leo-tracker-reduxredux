"""Reproducible static sky maps, support and sensitivity; no localization fit."""
import csv
import hashlib
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import numpy as np

from receiver_sky_model import prepare, kernel, fit_softmax, softmax_map, disk_grid, sky_xy, directions
from run_receiver_sky import HERE, OUT, SCANS


def serial(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    raise TypeError(type(value))


def hash_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def setup(ax,title):
    circle=Circle((0,0),1,facecolor='#eeeeee',edgecolor='.45',lw=.8,zorder=0)
    ax.add_patch(circle)
    for elevation in (30,60):
        r=1-elevation/90
        ax.add_patch(Circle((0,0),r,fill=False,edgecolor='.45',lw=.5,ls=':',zorder=5))
        ax.text(.025,r,f'{elevation}°',ha='left',va='bottom',fontsize=8,zorder=6,
                bbox=dict(facecolor='white',alpha=.65,edgecolor='none',pad=.3))
    ax.plot([0,0],[-1,1],color='.45',ls=':',lw=.5,zorder=5)
    ax.plot([-1,1],[0,0],color='.45',ls=':',lw=.5,zorder=5)
    for label,xy in [('N',(0,1.07)),('E',(1.07,0)),('S',(0,-1.07)),('W',(-1.07,0))]:
        ax.text(*xy,label,ha='center',va='center',fontsize=11,fontweight='bold')
    axes=sky_xy(directions([270,90],[70,70]))
    for i,(x,y) in enumerate(axes):
        ax.scatter([x],[y],s=110,marker='*',c=['white'],edgecolor='black',linewidth=1,zorder=7)
        ax.annotate(f'RX{i}',(x,y),xytext=(0,-17),textcoords='offset points',ha='center',fontsize=8,zorder=7,
                    bbox=dict(facecolor='white',alpha=.7,edgecolor='none',pad=.4))
    ax.set(xlim=(-1.15,1.15),ylim=(-1.13,1.13),aspect='equal',title=title)
    ax.axis('off')
    return circle


def panel(ax,values,inside,title,mask=None,cmap='viridis',vmin=0,vmax=1):
    circle=setup(ax,title)
    z=np.full(inside.shape,np.nan);z[inside]=values
    if mask is not None:
        compact=z[inside];compact[~mask]=np.nan;z[inside]=compact
    cm=plt.get_cmap(cmap).copy();cm.set_bad((0,0,0,0))
    im=ax.imshow(np.ma.masked_invalid(z),extent=(-1,1,-1,1),origin='lower',cmap=cm,vmin=vmin,vmax=vmax,zorder=1)
    im.set_clip_path(circle)
    plt.colorbar(im,ax=ax,fraction=.036,pad=.012,shrink=.78)
    return im


def save(fig,name,footer):
    fig.text(.5,.025,footer,ha='center',va='center',fontsize=10)
    fig.subplots_adjust(left=.035,right=.965,top=.91,bottom=.095,hspace=.18,wspace=.12)
    fig.savefig(OUT/name,dpi=170)
    plt.close(fig)


def tables(rows,keys):
    def val(x):return f'{x:.4f}' if isinstance(x,float) else str(x)
    return '<table><tr>'+''.join(f'<th>{k}</th>' for k in keys)+'</tr>'+''.join('<tr>'+''.join(f'<td>{html.escape(val(r[k]))}</td>' for k in keys)+'</tr>' for r in rows)+'</table>'


def run():
    records=[json.loads((OUT/'paired'/f'{s}.json').read_text()) for s in SCANS]
    assert [r['scan'] for r in records]==SCANS
    all_events=[e for r in records for e in r['events']]
    keys=[(e['scan'],e['arm'],e['gate_hz'],e['visit'],e['probe'],e['satellite']) for e in all_events]
    assert len(set(keys))==len(keys)
    assert all(r['reconstruction_max_hz']<1e-5 for r in records)
    _,_,inside,grid=disk_grid(101)
    cases={};summaries=[]
    for arm in ('fitted-c','zero-c'):
        for gate in (300,600):
            selected=[e for e in all_events if e['arm']==arm and e['gate_hz']==gate]
            data=prepare(selected);k=kernel(data,grid,bootstrap=250)
            fit=fit_softmax(data);parametric=softmax_map(fit,grid,len(data['scan_names']))
            assert fit['converged'],fit['status']
            cases[arm,gate]=dict(events=selected,data=data,kernel=k,fit=fit,parametric=parametric)
            row=dict(arm=arm,gate_hz=gate,events=len(selected),
                rx0_only=sum(e['outcome']==0 for e in selected),rx1_only=sum(e['outcome']==1 for e in selected),
                both=sum(e['outcome']==2 for e in selected),
                top_only_both=sum(e['top_candidate_outcome']==2 for e in selected),
                scans=len(data['scan_names']),encounter_time_blocks=len(set(data['block'])),
                softmax_converged=fit['converged'],gradient_inf=fit['gradient_inf'],
                **{q:fit[q] for q in ('in_sample_log_loss','null_log_loss','in_sample_brier','null_brier')})
            summaries.append(row)
            np.savez_compressed(OUT/f'{arm}-{gate}-map.npz',directions=grid,inside=inside,
                probability=k['probability'],intervals=k['intervals'],support=k['supported'],
                scan_count=k['scans'],block_count=k['blocks'],softmax_probability=parametric)
            (OUT/f'{arm}-{gate}-fit.json').write_text(json.dumps(fit,default=serial,indent=2))
            print('MAP',row,flush=True)
    main=cases['fitted-c',600];k=main['kernel'];p=k['probability'];mask=k['supported']
    fig,axs=plt.subplots(2,2,figsize=(13,12))
    for ax,values,title in zip(axs.flat,[p[:,0]+p[:,2],p[:,1]+p[:,2],p[:,2],k['scans']],
            ['RX0 reception · includes shared detections','RX1 reception · includes shared detections',
             'RX0 + RX1 · simultaneous shared reception','Evidence support · scans within 15°']):
        support=title.startswith('Evidence')
        panel(ax,values,inside,title,None if support else mask,cmap='cividis' if support else 'viridis',vmax=18 if support else 1)
    fig.suptitle('A + B + N01–N16 · empirical receiver sky maps',fontsize=19)
    save(fig,'sky-maps.png','Conditional on at least one receiver matching a selected satellite in the same channel / 20 ms probe.\n'
         'Zenith at center; horizon at rim. Stars = nominal axes, not measured boresights. Gray = insufficient evidence.\n'
         '10° angular smoothing; map shown only with ≥5 scans and ≥20 encounter-time blocks within 15°. Fitted c; ±600 Hz matching.')
    fig,axs=plt.subplots(2,2,figsize=(13,12))
    for c,title in enumerate(['RX0 only','RX1 only','Both receivers']):
        panel(axs.flat[c],p[:,c],inside,title,mask)
    width=k['intervals'][1,:,2]-k['intervals'][0,:,2]
    panel(axs.flat[3],width,inside,'Shared reception · 95% scan-bootstrap interval width',mask,cmap='magma',vmax=1)
    fig.suptitle('Mutually exclusive reception outcomes and sampling uncertainty',fontsize=18)
    save(fig,'exclusive-outcomes.png','The three outcome probabilities sum to one; “neither” is not estimated. 250 whole-scan bootstrap replicates.\n'
         'Uncertainty is scan-sampling stability, not a confidence guarantee about satellite identity or antenna gain.')
    fig,axs=plt.subplots(2,2,figsize=(13,12))
    for ax,((arm,gate),case) in zip(axs.flat,cases.items()):
        panel(ax,case['kernel']['probability'][:,2],inside,f'{arm} · ±{gate} Hz · shared reception',case['kernel']['supported'])
    fig.suptitle('Sensitivity to frequency matching and RF calibration',fontsize=18)
    save(fig,'calibration-sensitivity.png','Same refined candidate inputs, selected satellite roster and frozen timing across RF arms; no localization refit.\n'
         'Detection outcomes and retained opportunities can change with calibration or matching tolerance; these are not identical outcome samples.')
    # All models train on the complete eligible opportunity set; no held-out rows.
    variants={'Kernel 6°':kernel(main['data'],grid,6,bootstrap=0),
              'Kernel 10°':k,'Kernel 14°':kernel(main['data'],grid,14,bootstrap=0)}
    no_a=prepare([e for e in main['events'] if e['scan']!='A'])
    variants['Exclude A (10 MS/s)']=kernel(no_a,grid,10,bootstrap=0)
    top=[dict(e,outcome=e['top_candidate_outcome']) for e in main['events'] if e['top_candidate_outcome']>=0]
    variants['Top candidate only']=kernel(prepare(top),grid,10,bootstrap=0)
    fig,axs=plt.subplots(2,3,figsize=(17,11))
    for ax,(name,result) in zip(axs.flat,variants.items()):
        panel(ax,result['probability'][:,2],inside,name,result['supported'])
    panel(axs.flat[5],main['parametric'][:,2],inside,'Smooth quadratic softmax',mask)
    fig.suptitle('Shared-reception map · model and selection sensitivity',fontsize=18)
    save(fig,'model-sensitivity.png','Same fixed identities/timing. Kernel estimates retain observed channel mix; softmax averages equally over 4 channels × 18 scan effects.\n'
         'Top-only diagnostic censors alternative detections; exclusion of A checks the one 10 MS/s reference scan. Other scans are 2.5 MS/s.')
    fig,axs=plt.subplots(1,3,figsize=(17,6.5))
    xy=sky_xy(main['data']['unit']);col=['#0072B2','#D55E00','#009E73']
    for c,ax in enumerate(axs):
        setup(ax,['RX0-only matched opportunities','RX1-only matched opportunities','Simultaneous two-receiver matches'][c])
        m=main['data']['outcome']==c
        ax.scatter(xy[m,0],xy[m,1],s=2,alpha=.13,color=col[c],rasterized=True)
    fig.suptitle('Observed sky support · before smoothing',fontsize=18)
    save(fig,'observed-sky.png','Each dot is one satellite / channel / paired-probe outcome, not one independent pass. Multiple satellites can share a probe.\n'
         'Directions depend on frozen associations and timing. Empty regions are untested, not proven invisible.')
    # Channel-controlled views expose differing channel mixes without claiming
    # GLRT scores are calibrated received powers.
    fig,axs=plt.subplots(2,2,figsize=(13,12))
    for ch,ax in enumerate(axs.flat,1):
        subset=[e for e in main['events'] if e['channel']==ch]
        result=kernel(prepare(subset),grid,10,bootstrap=0)
        panel(ax,result['probability'][:,2],inside,f'CH{ch} · shared reception',result['supported'])
    fig.suptitle('Shared reception by channel · fitted c, ±600 Hz',fontsize=18)
    save(fig,'channel-sensitivity.png','All 18 scans; same spatial support rule applied per channel. Conditional detection frequency, not antenna gain.')
    # Illustrative numeric summaries on the supported map only.
    valid=np.isfinite(width)&mask
    summary=dict(scope='Empirical paired detection support; not absolute antenna gain or blind validation.',
        summaries=summaries,source_candidates=sum(r['candidate_count'] for r in records),
        scheduled_receiver_probes=sum(r['all_scheduled_probes'] for r in records),
        main_events=len(main['events']),main_outcomes=np.bincount(main['data']['outcome'],minlength=3),
        both_promoted_from_alternatives=sum(e['outcome']==2 and e['top_candidate_outcome']!=2 for e in main['events']),
        same_opportunity_pair_checks={s:next(r for r in records if r['scan']==s)['counts']['fitted-c-600'] for s in SCANS},
        maximum_reconstruction_error_hz=max(r['reconstruction_max_hz'] for r in records),
        median_shared_interval_width=float(np.median(width[valid])),
        p90_shared_interval_width=float(np.percentile(width[valid],90)),
        sensitivity_mean_abs_shared_change={name:float(np.nanmean(abs(result['probability'][mask&result['supported'],2]-p[mask&result['supported'],2]))) for name,result in variants.items()},
        protocol=dict(primary_gate_hz=600,sensitivity_gate_hz=300,bandwidth_deg=10,
            support_radius_deg=15,minimum_scans=5,minimum_blocks=20,block_s=5,bootstrap_scans=250,
            spatial_ridge=2,channel_ridge=5,scan_ridge=10,
            conditioning='At least one unique candidate-to-selected-satellite match in a valid paired probe.',
            ambiguous_candidates='If a candidate matches >1 selected satellite, it is ambiguous. Ambiguous or failed-only peer is excluded, not labeled nondetected.',
            time_support='First-to-last historical assigned time for the satellite, padded by 2 s.',
            weighting='Equal total scan weights; each satellite/5-second block has equal weight within its scan; channels pooled.',
            unknown='Unobserved directions and insufficiently sampled directions are masked, not estimated invisible.',
            training='All retained paired opportunities across all 18 scans; no new train/test folds. Saved legacy calibrations are reused.',
            interpretation='Frozen selected identities/timing; all refined candidates tested, exact aliases collapse by satellite/probe. No new physical association certification.'),
        sources={str(OUT/'paired'/f'{s}.json'):hash_file(OUT/'paired'/f'{s}.json') for s in SCANS},
        implementation={str(HERE/n):hash_file(HERE/n) for n in ['collect_receiver_sky.py','export_receiver_sky_probes.py','receiver_sky_model.py','render_receiver_sky.py']})
    (OUT/'summary.json').write_text(json.dumps(summary,default=serial,indent=2,allow_nan=False))
    with (OUT/'metrics.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
    with (OUT/'paired-opportunities.csv').open('w',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=list(main['events'][0]));w.writeheader();w.writerows(main['events'])
    body='<h1>Receiver sky maps: A + B + N01–N16</h1>'
    body+='<p>Empirical relative reception, conditional on at least one receiver matching a selected satellite. This is not an absolute field-of-view or antenna gain measurement. Known capture-bound roof coordinates determine directions; no position optimization or new RF collection is performed.</p>'
    body+=f'<p>{summary["source_candidates"]:,} refined candidate records inspected; {summary["scheduled_receiver_probes"]:,} scheduled receiver probes verified. Primary map: {summary["main_events"]:,} distinct satellite/channel/paired-probe outcomes. Candidates and exact alias alternatives cannot multiply a satellite’s count within one probe. Multiple different satellites may be present in a probe.</p>'
    body+='<p><strong>Main finding:</strong> RX0 preferentially detects the western upper sky, RX1 the eastern upper sky, and simultaneous reception clusters around the overhead dividing region. This is relative reception conditional on the selected identities—not a measured beam edge. The broad pattern persists across both RF settings, matching tolerances, smoothing widths and exclusion of scan A.</p>'
    primary=next(r for r in summaries if r['arm']=='fitted-c' and r['gate_hz']==600)
    body+=f'<p>Checking all refined candidates gives {primary["both"]:,} simultaneous matches, versus {primary["top_only_both"]:,} from the top candidates alone. This is recovery of peer detection evidence, not a new count of verified satellites.</p>'
    body+='<img src="sky-maps.png"><h2>Observed evidence and exclusive outcomes</h2><img src="observed-sky.png"><img src="exclusive-outcomes.png">'
    body+='<h2>Method</h2><ol><li>Reuse the 18 frozen T1-AT v1 selected satellite rosters and absolute timing; reconstruct their calibrated predictions at each candidate’s own support epoch. All saved refined passing candidate alternatives are tested. Failed refinements or nonpositive refined margins are not evidence of absence.</li><li>Require the same visit, probe, RF/channel/edge and physical sample counter on both receivers. A detection requires a candidate within ±600 Hz of exactly one selected orbit (±300 Hz sensitivity). If the peer is ambiguous or has failed refinement without a valid match, omit that uncertain opportunity.</li><li>Restrict each satellite to its historical first-to-last assigned span plus 2 s. This avoids treating chance matches anywhere in a scan as continuous established tracks. It also means these maps cannot discover the entire unobserved beam.</li><li>Collapse each satellite/probe/receiver to a binary detection; retain all resulting paired opportunities. No new data folds. Weight each satellite/5-second block equally within a scan, then equalize scan totals.</li><li>Fit angular Gaussian smoothers and a regularized quadratic-direction multinomial model with channel and scan intercepts. The latter map averages over all 4 channels and 18 scan effects. These are different descriptive estimates, not calibrated absolute probabilities.</li><li>Mask regions supported by fewer than 5 scans or 20 encounter-time blocks within 15°. Resample whole scans 250 times for kernel-map stability bands.</li></ol>'
    body+='<h2>Sensitivity and fit metrics</h2><img src="calibration-sensitivity.png"><img src="model-sensitivity.png"><img src="channel-sensitivity.png">'
    body+=tables(summaries,list(summaries[0]))
    body+='<p>Log loss and Brier score are in-sample multinomial scores (lower is better), compared with a direction-independent category-frequency null. They are not held-out performance or position errors. No improvement in localization is claimed. RF arms retain exactly the same candidate inventory, roster and timing, but calibration-dependent matches change the eligible outcome set.</p>'
    body+='<h2>Limitations</h2><p>All satellite identities remain conditional on Doppler associations. Non-detections confound sensitivity, transmitter activity, polarization, channel and processing thresholds. The “neither receiver” outcome is not identifiable here. Original A/B Doppler fits used the earlier reference site; sky directions are reprojected at the capture-bound roof, not reidentified. Nominal RX0 az/el 270°/70° and RX1 90°/70° assume a level fixture; actual beamwidths, installed boresights and connector mapping are not measured. Broad gradients and overlap are more defensible than sharp edges.</p>'
    body+='<p>The sky fit uses all 18 scans and no new folds. Existing frequency calibrations contain the historical five-fold fits; they were frozen, not regenerated or presented as full-data calibration. One scan (A) is 10 MS/s; the other 17 are 2.5 MS/s, with an explicit exclude-A sensitivity.</p>'
    body+='<h2>Artifacts</h2><ul>'+''.join(f'<li><a href="{f}">{f}</a></li>' for f in ['summary.json','metrics.csv','paired-opportunities.csv','fitted-c-600-map.npz'])+'</ul>'
    (OUT/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Receiver sky maps</title><style>body{max-width:1500px;margin:30px auto;font:16px system-ui;line-height:1.5;padding:20px}img{width:100%}table{border-collapse:collapse;font-size:11px}td,th{padding:5px;border:1px solid #ddd}</style>'+body)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('sources','implementation','same_opportunity_pair_checks','protocol')},default=serial,indent=2))


if __name__=='__main__':run()
