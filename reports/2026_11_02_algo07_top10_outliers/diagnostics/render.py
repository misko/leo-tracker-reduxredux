"""Render saved numerical diagnostics; no fitting or identity selection."""
import csv, hashlib, subprocess
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.colors import hsv_to_rgb
from diagnose import ROOT,INPUT,CASES,ARMS,SITE_X,read,write,inventory,frozen_published_owners

plt.rcParams.update({'font.size':9,'axes.grid':True,'grid.alpha':.2})
def save(fig,path):fig.savefig(path,dpi=140,bbox_inches='tight');plt.close(fig)

def contexts(case,z,out):
    obs=read(Path(z['native_path'])/'observations.json');tracks=read(Path(z['native_path'])/'tracks.json')
    graph={o for t in tracks for o in t['observation_ids']};owners=z['baseline_owners']['fitted_c']
    ns=sorted(set(owners.values()))
    # Reserve red and gray exclusively for unassociated and untracked points.
    cols={n:hsv_to_rgb((.075+.70*k/max(1,len(ns)-1),.72,.76)) for k,n in enumerate(ns)}
    fig,axes=plt.subplots(2,8,figsize=(26,7),sharex=True,sharey=True,layout='constrained')
    score,sax=plt.subplots(2,8,figsize=(26,6),sharex=True,sharey=True,layout='constrained')
    for rx in (1,2):
        for ch in range(1,9):
            ax=axes[rx-1,ch-1];sx=sax[rx-1,ch-1];lane=[o for o in obs if (o['receiver'],o['channel'])==(rx,ch)]
            for n in ns:
                rr=[o for o in lane if owners.get(o['observation_id'])==n]
                ax.scatter([o['time_s'] for o in rr],[o['measured_cfo_hz']/1000 for o in rr],s=5,color=cols[n],alpha=.7)
                if len(rr)>10:
                    mid=rr[len(rr)//2];ax.annotate(str(n),(mid['time_s'],mid['measured_cfo_hz']/1000),fontsize=5)
            for isgraph,col,mark in [(True,'crimson','o'),(False,'gray','x')]:
                rr=[o for o in lane if o['observation_id'] not in owners and (o['observation_id'] in graph)==isgraph]
                ax.scatter([o['time_s'] for o in rr],[o['measured_cfo_hz']/1000 for o in rr],s=7,color=col,marker=mark,alpha=.65)
            im=sx.scatter([o['time_s'] for o in lane],[o['measured_cfo_hz']/1000 for o in lane],c=[o['fractional_margin'] for o in lane],vmin=0,vmax=1,cmap='viridis',s=7)
            for axis in (ax,sx):axis.set(title=f'RX{rx} CH{ch}',xlabel='Scan time (s)',ylabel='CFO (kHz)')
    legend=[Line2D([],[],marker='o',ls='',color=cols[n],label=str(n),markersize=4) for n in ns]
    legend += [Line2D([],[],marker='o',ls='',color='crimson',label='Native graph unassociated',markersize=4),Line2D([],[],marker='x',ls='',color='gray',label='Native untracked',markersize=4)]
    fig.legend(handles=legend,loc='outside lower center',ncol=10,fontsize=7)
    fig.suptitle(case+' · composed ALGO06 published native ownership (ALGO07 guarded fallback)\nGray × = native untracked; red = graph unassociated; categorical colors = satellite owners')
    score.colorbar(im,ax=sax,label='GLRT fractional winner margin (raw GLRT statistic absent from export)')
    score.suptitle(case+' · native GLRT score context; same point universe as ownership figure')
    save(fig,out/'native_context.png');save(score,out/'glrt_score.png')

def render(case):
    out=ROOT/case
    if not (out/'audit.json').exists():return []
    a=read(out/'audit.json');z=read(INPUT/'inputs'/(case+'.json'))
    # The memberships helper screens extra extensions; they are not adopted.
    z['baseline_owners']=frozen_published_owners(case,z)
    write(out/'published_owners.json',z['baseline_owners'])
    write(out/'inventory.json',inventory(None,z));contexts(case,z,out)
    plan=read(out/'fit-plan.json');tags=['continue','regional_center','phase_sigma_x2']+[f'omit_{n}' for n in plan['selected']]
    trials=[('published',a['arms'])]+[(tag,read(out/(tag+'.json'))) for tag in tags if (out/(tag+'.json')).exists()]
    fig,axes=plt.subplots(1,2,figsize=(15,6),layout='constrained');y=np.arange(len(trials))
    for arm,off,col in [('c0',-.15,'#0072b2'),('fitted_c',.15,'#d55e00')]:
        axes[0].barh(y+off,[pair[arm]['error_m']/1000 for tag,pair in trials],height=.28,color=col,label=arm)
        axes[1].barh(y+off,[pair[arm]['rms_hz'] for tag,pair in trials],height=.28,color=col,label=arm)
        for k,(tag,pair) in enumerate(trials):
            r=pair[arm];g=read(out/('published_gates_'+arm+'.json')) if tag=='published' else r
            phase=r.get('phase_closed',r.get('phase_reference_check',{}).get('phase_change_s',1e9)<=.01)
            opt='?' if tag=='published' else str(int(r['optimizer_success']))
            axes[0].text(r['error_m']/1000+.03,k+off,f"P{int(phase)} O{opt} G{int(g['all_gates_pass'])}",va='center',fontsize=7)
    axes[0].set_xlim(right=max(pair[arm]['error_m']/1000 for tag,pair in trials for arm in ARMS)*1.23)
    for ax in axes:ax.set(yticks=y,yticklabels=[t for t,p in trials]);ax.invert_yaxis();ax.legend()
    axes[0].set(xlabel='Evaluation position error (km)',title='Position accuracy: GPS after RF fit')
    axes[1].set(xlabel='Retained curved conditional RMS (Hz)',title='Frequency fit; omission changes observation set')
    fig.suptitle(case+' · matched c arms, RF-ranked diagnostic omissions\nP/O/G: phase closure / optimizer / surviving gates (1=pass, 0=fail, ?=saved solver metadata); omissions are not approved removals')
    save(fig,out/'ablations.png')
    fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    for arm,ax in zip(ARMS,axes):
        r=a['arms'][arm];surface=np.array(r['surface']);im=ax.contourf(r['grid_east'],r['grid_north'],surface-surface.min(),levels=15,cmap='viridis')
        ax.scatter(*SITE_X,c='white',edgecolor='black',marker='*',s=160,label='Evaluation site (oracle)');ax.scatter(*r['x'],c='red',marker='X',s=70,label='Published endpoint')
        ax.set(title=arm,xlabel='East of regional prior center (km)',ylabel='North of regional prior center (km)',aspect='equal');ax.legend(fontsize=7);fig.colorbar(im,ax=ax,label='Objective above sampled minimum')
    fig.suptitle(case+' · oracle-position diagnostic: 10 km square, 7×7 grid\nFixed associations and saved phase references; no localization estimate chosen from this grid')
    save(fig,out/'oracle_loss_grid.png')
    residuals=read(out/'track_residuals.json');fig,axes=plt.subplots(2,2,figsize=(15,10),layout='constrained')
    for col,arm in enumerate(ARMS):
        rr=[r for r in residuals if r['arm']==arm]
        labels=sorted(set((r['receiver'],r['channel']) for r in rr))
        ax=axes[0,col];ax.boxplot([np.concatenate([r['residual_hz'] for r in rr if (r['receiver'],r['channel'])==key]) for key in labels],tick_labels=[f'R{x} C{y}' for x,y in labels],showfliers=False)
        ax.axhline(0,c='black',lw=.7);ax.set(title=arm+' · by receiver/band',ylabel='Residual (Hz)');ax.tick_params(axis='x',rotation=60)
        ns=sorted({r['norad'] for r in rr});ax=axes[1,col]
        ax.boxplot([np.concatenate([r['residual_hz'] for r in rr if r['norad']==n]) for n in ns],tick_labels=ns,showfliers=False);ax.axhline(0,c='black',lw=.7)
        ax.set(title=arm+' · by family',ylabel='Residual (Hz)');ax.tick_params(axis='x',rotation=60)
    fig.suptitle(case+' · all retained curved/linear/new-family residuals\nDifferent residual scopes remain explicitly labeled in track_residuals.json; outliers retained in saved data')
    save(fig,out/'residual_by_receiver_family.png')
    fig,axes=plt.subplots(2,1,figsize=(15,7),layout='constrained')
    for arm,ax in zip(ARMS,axes):
        pars=a['arms'][arm]['parameters'];x=np.arange(len(pars));ax.bar(x-.17,[abs(r['phase_standardized']) for r in pars],width=.34,label='|Phase standardized coefficient|')
        ax.bar(x+.17,[max(abs(np.asarray(r['orbital_standardized'])),default=0) for r in pars],width=.34,label='Largest |orbit standardized coefficient|')
        ax.set(title=arm,xticks=x,xticklabels=[r['norad'] for r in pars],ylabel='Original prior units');ax.tick_params(axis='x',rotation=60);ax.legend()
    fig.suptitle(case+' · nuisance pulls; phase heavy-tail precision also saved')
    save(fig,out/'nuisance_pulls.png')
    result=[]
    for tag,pair in trials:
        for arm in ARMS:
            r=pair[arm];g=read(out/('published_gates_'+arm+'.json')) if tag=='published' else r
            result.append(dict(case=case,trial=tag,arm=arm,error_m=r['error_m'],objective=r['objective'],rms_hz=r['rms_hz'],
                phase_closed=r.get('phase_closed',r.get('phase_reference_check',{}).get('phase_change_s',1e9)<=.01),optimizer_success=r.get('optimizer_success'),
                all_gates_pass=g['all_gates_pass'],minimum_gate_slack=g['minimum_gate_slack'],lost_native=len(g['lost_ids']),added_native=len(g['added_ids']),reassigned_native=len(g['reassigned_ids']),
                fixed_fitted_native_count=r.get('fixed_fitted_native_count',g.get('published_owners_count')),intentional_omitted_native_count=r.get('intentional_omitted_native_count',0),
                screen_unrelated_lost_native=len(r.get('proposed_unrelated_lost_ids',g['lost_ids'])),screen_reassigned_non_omitted_native=len(r.get('proposed_reassigned_non_omitted_ids',g['reassigned_ids'])),
                ownership_screen_adopted=False))
    return result

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('cases',nargs='*');args=ap.parse_args();rows=[]
    for case in args.cases or CASES:rows+=render(case);print(case,'rendered',flush=True)
    if rows:
        target=ROOT/('localization_trials.csv' if not args.cases else 'localization_trials_partial.csv')
        with target.open('w') as f:w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
        write(target.with_suffix('.json'),rows)
