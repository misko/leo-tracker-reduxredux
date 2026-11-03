"""Render saved native-track evidence without rerunning candidate search."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from investigate import INVENTORY, MODELS, PERIOD, read, write, published


def ranked(d,reg='causal',model='phase_small_rate',arm='fitted_c'):
    return sorted([r for r in d['fits'] if r['regime']==reg and r['model']==model and r['arm']==arm],key=lambda r:r['cost'])


def fails(r,n):
    g=r['noise'];failed=[]
    for key,limit,label in [('mean_z',3,'mean'),('slope_z',3,'slope'),('quadratic_bic_gain',10,'curvature'),('maximum_step_z',4,'step'),('lag1_acf',4/np.sqrt(n),'correlation')]:
        if (abs(g[key]) if key=='lag1_acf' else g[key])>limit:failed.append(label)
    if r['rms_hz']>450:failed.append('RMS')
    if abs(r['offset_hz'])>3000:failed.append('offset')
    if abs(r['rate_hz_s'])>2:failed.append('rate>2Hz/s')
    if r['phase_at_bound']:failed.append('phase bound')
    return ', '.join(failed) or 'none in diagnostic screen'


def line(ax,t,y,**kwargs):
    # All callers supply displayed CFO in kHz.
    y=np.asarray(y,float).copy();j=np.flatnonzero((np.diff(t)>5)|(abs(np.diff(y))>PERIOD/2000))+1;y[j]=np.nan
    return ax.plot(t,y,**kwargs)


def main(out):
    figs=out/'figures';figs.mkdir(exist_ok=True)
    summaries=[];allfits=[];sections=[];items=[]
    packets={ds:json.loads(gzip.open(INVENTORY/ds/'plot-inputs.json.gz','rt').read()) for ds in ['DS26','DS27']}
    for row in read(out/'targets.json'):
        d=read(out/'cases'/row['case']/(row['fragment_id']+'.json'));items.append(d)
        t=np.asarray(d['times_s']);y=np.asarray(d['values_hz']);ca=ranked(d);best=ca[0];other=ca[1];post=ranked(d,'later');pb=post[0] if post else None
        same=next((r for r in post if r['norad']==best['norad']),None)
        old=(d.get('previous_evidence') or {}).get('identity') or {}
        identity=old.get('status','new nomination; independent joint validation pending')
        if old.get('norad') and old['norad']!=best['norad']:identity='changed nominee; unresolved'
        if old.get('status')=='conditionally_supported_identity' and best['rms_hz']>450:identity='old nomination contradicted by model fit'
        validation=d['grouped_validation'];wins=[]
        for seed in sorted({r['seed'] for r in validation}):
            v=[r for r in validation if r['seed']==seed and r['regime']=='causal' and r['arm']=='fitted_c' and r['model']=='phase_small_rate']
            if v:wins.append(min(v,key=lambda r:r['held_rms_hz'])['norad'])
        poly=d['polynomial']['robust_orders'][0]
        summary=dict(case=row['case'],track=row['key'].split('-RF')[0].replace('SCAN-',''),points=row['points'],span_s=row['duration_s'],causal_norad=best['norad'],runner_up=other['norad'],causal_rms_hz=best['rms_hz'],score_margin=other['cost']-best['cost'],rate_hz_s=best['rate_hz_s'],phase_s=best['phase_s'],failed_checks=fails(best,len(t)),same_satellite_later_rms_hz=same['rms_hz'] if same else None,later_best_norad=pb['norad'] if pb else None,later_best_rms_hz=pb['rms_hz'] if pb else None,polynomial_degree=poly['degree'],polynomial_full_rms_hz=poly['full_rms_hz'],identity_evidence=identity,conditional_group_winners=','.join(map(str,wins)),fragment_id=row['fragment_id'])
        summaries.append(summary)
        for r in d['fits']:
            allfits.append(dict(case=row['case'],track=summary['track'],**{k:v for k,v in r.items() if k not in ['orbit_hz','correction_hz','residual_hz','noise','parameter_prior_pulls']},**r['noise']))
        ctx=packets[row['case'][:4]]['cases'][row['case']]
        # Load native observations from the sealed source; ownership is the published inventory.
        inv=read(row['inventory_path']);native=Path(inv['job']['root'])/inv['job']['case'];obs=read(native/'observations.json');tracks=read(native/'tracks.json')
        associated=set(ctx['associated_ids']);graph={oid for tr in tracks for oid in tr['observation_ids']};target=set(row['observation_ids'])
        lane=[o for o in obs if o['receiver']==row['receiver'] and o['channel']==row['channel'] and t.min()-10<=o['time_s']<=t.max()+10]
        lookup={o['observation_id']:o for o in obs};native_y=np.array([lookup[oid]['measured_cfo_hz'] for oid in row['observation_ids']]);lift=native_y-y
        fig,axes=plt.subplots(3,2,figsize=(15,12),layout='constrained');ax=axes[0,0]
        for label,color,marker,selected in [
            ('Published associated (gray)','.65','.',[o for o in lane if o['observation_id'] in associated]),
            ('Other unassociated graph','#d489bd','.',[o for o in lane if o['observation_id'] in graph-associated-target]),
            ('Untracked GLRT','#e89420','x',[o for o in lane if o['observation_id'] not in graph|associated]),
            ('Target unassociated','#b40040','o',[o for o in lane if o['observation_id'] in target])]:
            ax.scatter([o['time_s'] for o in selected],[o['measured_cfo_hz']/1000 for o in selected],s=13,marker=marker,c=color,label=label)
        line(ax,t,(y-np.array(best['residual_hz'])+lift)/1000,color='#176bbb',lw=1.1,label=f"Causal {best['norad']} adjusted")
        ax.set(title='Native GLRT and diagnostic orbit prediction',xlabel='Scan time (s)',ylabel='Native CFO (kHz)');ax.legend(fontsize=7)
        ax=axes[0,1];scores=[lookup[oid].get('fractional_margin',np.nan) for oid in row['observation_ids']]
        sc=ax.scatter(t,y/1000,c=scores,cmap='viridis',s=19,label='Target GLRT');fig.colorbar(sc,ax=ax,label='GLRT fractional margin')
        ax.plot(t,np.array(poly['prediction_hz'])/1000,color='#333',ls=':',label=f"Polynomial degree {poly['degree']}")
        hw=y-np.array(d['corrected_hz']['fitted_c']);orbit=np.array(best['orbit_hz'])+hw-best['alias']*PERIOD
        ax.plot(t,orbit/1000,color='#176bbb',ls='--',lw=1,label='Orbit + frozen hardware, before extra correction')
        ax.plot(t,(y-np.array(best['residual_hz']))/1000,color='#176bbb',label=f"Causal {best['norad']} + offset/rate")
        if pb:ax.plot(t,(y-np.array(pb['residual_hz']))/1000,color='#ed8a1c',label=f"Later best {pb['norad']} (may differ)")
        ax.set(title='Alias-lifted curves; no point duplication',xlabel='Scan time (s)',ylabel='Lifted CFO (kHz)');ax.legend(fontsize=7)
        ax=axes[1,0];ax.axhspan(-150,150,color='.95');ax.axhline(0,color='k',lw=.6)
        ax.plot(t,best['residual_hz'],'.-',ms=3,lw=.6,color='#176bbb',label=f"Causal {best['norad']} {best['rms_hz']:.1f} Hz")
        if same:ax.plot(t,same['residual_hz'],'.-',ms=3,lw=.6,color='#ed8a1c',label=f"Same ID, later {same['rms_hz']:.1f} Hz")
        elif pb:ax.plot(t,pb['residual_hz'],'.-',ms=3,lw=.6,color='#ed8a1c',label=f"Different ID later {pb['norad']} {pb['rms_hz']:.1f} Hz")
        ax.plot(t,poly['residual_hz'],'.',ms=3,c='.4',label='Polynomial residual')
        ax.set(title='Native residuals; shaded ±150 Hz is diagnostic noise',xlabel='Scan time (s)',ylabel='Residual (Hz)');ax.legend(fontsize=7)
        ax=axes[1,1];numbers=[r['norad'] for r in ca[:5]];models=list(MODELS)
        matrix=np.array([[next(r['cost'] for r in d['fits'] if r['regime']=='causal' and r['arm']=='fitted_c' and r['model']==m and r['norad']==n) for m in models] for n in numbers]);matrix-=matrix.min(axis=0)
        im=ax.imshow(np.minimum(matrix,200),aspect='auto',cmap='magma_r',vmin=0,vmax=200);fig.colorbar(im,ax=ax,label='Score above best per column (clipped at 200)')
        ax.set_yticks(range(len(numbers)),list(map(str,numbers)));ax.set_xticks(range(4),['Phase +\noffset','+ 0.5 Hz/s\nprior','+ 2 Hz/s\nprior','Affine\ncontrol'])
        for i,n in enumerate(numbers):
            for j,m in enumerate(models):
                r=next(r for r in d['fits'] if r['regime']=='causal' and r['arm']=='fitted_c' and r['model']==m and r['norad']==n)
                ax.text(j,i,f"{r['rms_hz']:.0f} Hz",ha='center',va='center',fontsize=8,color='white' if matrix[i,j]>90 else 'black')
        ax.set(title='Causal competitors: labels are RMS, color is score',ylabel='NORAD')
        ax=axes[2,0];ax.hist(best['residual_hz'],bins=15,color='#176bbb',alpha=.7,label='Orbit residual');ax.hist(poly['residual_hz'],bins=15,histtype='step',color='.25',label='Polynomial residual')
        ax.axvline(0,color='k',lw=.7);ax.set(xlabel='Residual (Hz)',ylabel='Native points',title=f"Failed checks: {summary['failed_checks']}");ax.legend(fontsize=8)
        ax=axes[2,1];ax.axis('off')
        transfer=[r for r in d['family_transfer'] if r['regime']=='causal' and r['arm']=='fitted_c' and r['model']=='phase_small_rate'][0]
        text=[f"{summary['identity_evidence']}",f"Causal nominee {best['norad']}; runner-up {other['norad']}",f"Score margin {summary['score_margin']:.1f} (not a probability)",f"Phase {best['phase_s']:+.3f} s; offset {best['offset_hz']:+.1f} Hz",f"Additional rate {best['rate_hz_s']:+.3f} Hz/s",f"Random whole-group winners: {summary['conditional_group_winners']}",f"Independent family support: {transfer.get('support_points',0)} points"]
        if 'target_rms_hz' in transfer:text.append(f"Support-only phase/rate → target RMS {transfer['target_rms_hz']:.1f} Hz")
        if not same:text.append('No eligible post-epoch TLE for causal nominee yet')
        text+=['Frozen inherited radio model at published position.','Single-track controls do not establish shared hardware correction.','No new point ownership or position acceptance.']
        ax.text(0,.98,'\n'.join(text),va='top',fontsize=9,linespacing=1.7)
        fig.suptitle(f"{row['case']} · {summary['track']} · {row['points']} points / {row['duration_s']:.1f} s",fontsize=15)
        stem=f"{row['case']}-{summary['track']}";fig.savefig(figs/(stem+'.png'),dpi=140);plt.close(fig)
        # Consecutive 20-second native-curve zooms and matching residual panels.
        starts=np.arange(t.min(),t.max(),20);fig,axs=plt.subplots(len(starts),2,figsize=(13,3*len(starts)),squeeze=False,layout='constrained')
        for z,start in enumerate(starts):
            use=(t>=start-1)&(t<=start+21);tt=t[use]
            ax=axs[z,0];ax.scatter(tt,native_y[use]/1000,s=18,c='#b40040');line(ax,tt,(y-np.array(best['residual_hz'])+lift)[use]/1000,c='#176bbb',label=f"Causal {best['norad']}")
            line(ax,tt,(np.array(poly['prediction_hz'])+lift)[use]/1000,ls=':',c='.35',label='Polynomial')
            ax.set(title=f'{start:.1f}–{min(start+20,t.max()):.1f} s',ylabel='Native CFO (kHz)',xlabel='Scan time (s)');ax.legend(fontsize=7)
            ax=axs[z,1];ax.axhline(0,c='k',lw=.6);ax.plot(tt,np.array(best['residual_hz'])[use],'.-',c='#176bbb',label='Causal residual');ax.plot(tt,np.array(poly['residual_hz'])[use],'.:',c='.4',label='Polynomial residual');ax.set(xlabel='Scan time (s)',ylabel='Residual (Hz)');ax.legend(fontsize=7)
        fig.suptitle(stem+' — consecutive 20 s segments');fig.savefig(figs/(stem+'-zoom.png'),dpi=130);plt.close(fig)
        sections.append(f"### {row['case']} · {summary['track']}\n\n{row['points']} points over {row['duration_s']:.1f} s. Causal nominee **{best['norad']}**, runner-up {other['norad']}; RMS **{best['rms_hz']:.1f} Hz**. Failed checks: **{summary['failed_checks']}**. Identity evidence: {identity}.\n\nLater catalogue best: **{pb['norad']}**, {pb['rms_hz']:.1f} Hz. Same-candidate paired later RMS: {f'{same["rms_hz"]:.1f} Hz' if same else 'unavailable'}. Polynomial: degree {poly['degree']}, full-point RMS {poly['full_rms_hz']:.1f} Hz. Conditional random-group winners: {summary['conditional_group_winners']}. Independent family support: {transfer.get('support_points',0)} points.\n\n![Diagnostic](figures/{stem}.png)\n\n[20-second zooms](figures/{stem}-zoom.png) · [Numerical evidence](cases/{row['case']}/{row['fragment_id']}.json)\n")
    for name,rows in [('association_summary.csv',summaries),('candidate_fits.csv',allfits)]:
        with (out/name).open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write(out/'association_summary.json',summaries)
    (out/'track_atlas.md').write_text('# Long residual GLRT track atlas\n\nAll values below use fitted-c; the linked data include matched c=0 comparisons. Target-only fits are diagnostic; historical independent evidence is labeled separately.\n\n'+'\n'.join(sections))
    for ds in ['DS26','DS27']:
        local=[s for s in summaries if s['case'].startswith(ds)];labels=[s['case'].replace(ds+'-','')+' '+s['track'].replace('RX1-','').replace('RX2-','R2 ') for s in local]
        fig,axes=plt.subplots(1,2,figsize=(15,7),layout='constrained');yy=np.arange(len(local))
        for ax in axes:ax.set_yticks(yy,labels);ax.invert_yaxis();ax.grid(axis='x',alpha=.2)
        axes[0].scatter([s['causal_rms_hz'] for s in local],yy,c='#176bbb',label='Best causal, phase + small rate')
        axes[0].scatter([s['later_best_rms_hz'] for s in local],yy,marker='x',c='#ed8a1c',label='Best later (may be another satellite)')
        axes[0].scatter([s['polynomial_full_rms_hz'] for s in local],yy,marker='|',s=150,c='.3',label='Polynomial full-point RMS')
        axes[0].set(xscale='log',xlabel='RMS (Hz; logarithmic scale)',title='Model fit versus empirical curve');axes[0].legend(fontsize=8)
        for k,s in enumerate(local):
            if s['same_satellite_later_rms_hz'] is not None:axes[1].plot([s['causal_rms_hz'],s['same_satellite_later_rms_hz']],[k,k],c='.65')
            else:axes[1].text(15,k,'Later TLE unavailable',fontsize=7,va='center',color='.4')
        axes[1].scatter([s['causal_rms_hz'] for s in local],yy,c='#176bbb',label='Causal nominee')
        selected=[(i,s) for i,s in enumerate(local) if s['same_satellite_later_rms_hz'] is not None]
        axes[1].scatter([s['same_satellite_later_rms_hz'] for i,s in selected],[i for i,s in selected],c='#ed8a1c',marker='x',label='Same satellite, later elements')
        axes[1].set(xscale='log',xlabel='RMS (Hz; logarithmic scale)',title='Paired TLE test: same identity, same model');axes[1].legend(fontsize=8)
        fig.suptitle(ds+' — 10 longest ALGO05 residual fragments');fig.savefig(figs/(ds+'-overview.png'),dpi=160);plt.close(fig)
    print('Rendered',len(summaries),'track dashboards, zoom sheets, and two overviews.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);main(p.parse_args().output)
