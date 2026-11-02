"""Render the frozen diagnostic artifacts, without running an association fit."""
import csv, json, math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from diagnose import ROOT,INPUT,CASES,ARMS,SITE_X,read,reconstruct
from family_debug import SUSPECT
from leo.analysis.research.retained_track_likelihood import PERIOD

plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.2,'figure.dpi':140})

def save(fig,path):
    fig.savefig(path,dpi=145,bbox_inches='tight');plt.close(fig)

def broken(t,y):
    y=np.array(y,float);y[np.r_[False,abs(np.diff(y))>PERIOD/2]]=np.nan;return y

def wrap(y):return (np.array(y)+PERIOD/2)%PERIOD-PERIOD/2

def contexts(case,z,d,out):
    obs=read(Path(z['native_path'])/'observations.json');owners=z['baseline_owners']['fitted_c'];tracks=d['scan'].tracks
    graph={o for tr in tracks for o in tr['observation_ids']};numbers=sorted(set(owners.values()));colors={n:plt.colormaps['viridis'](.05+.85*k/max(1,len(numbers)-1)) for k,n in enumerate(numbers)}
    for rx in (1,2):
        fig,axes=plt.subplots(4,2,figsize=(15,13),layout='constrained',sharex=True)
        for ch,ax in enumerate(axes.flat,1):
            lane=[o for o in obs if o['receiver']==rx and o['channel']==ch]
            for n in numbers:
                rr=[o for o in lane if owners.get(o['observation_id'])==n]
                ax.scatter([o['time_s'] for o in rr],[o['measured_cfo_hz']/1000 for o in rr],s=8,c=[colors[n]],alpha=.7)
                if len(rr)>=10:
                    mid=rr[len(rr)//2];ax.annotate(str(n),(mid['time_s'],mid['measured_cfo_hz']/1000),fontsize=6,xytext=(2,3),textcoords='offset points')
            for isgraph,col,mark in [(True,'crimson','o'),(False,'darkorange','x')]:
                rr=[o for o in lane if o['observation_id'] not in owners and (o['observation_id'] in graph)==isgraph]
                ax.scatter([o['time_s'] for o in rr],[o['measured_cfo_hz']/1000 for o in rr],s=13,c=col,marker=mark,alpha=.7)
            for tr in tracks:
                if (tr['receiver'],tr['channel'])!=(rx,ch):continue
                use=np.array([i not in owners for i in tr['observation_ids']]);yy=wrap(tr['values']);yy[~use]=np.nan
                if use.any():ax.plot(tr['times'],broken(tr['times'],yy)/1000,color='crimson',lw=.7,alpha=.45)
            ax.set(title=f'RX{rx} CH{ch}',xlabel='Scan time (s)',ylabel='Native GLRT CFO (kHz)')
        fig.suptitle(f'{case}: native observation ownership, RX{rx}\nSatellite-owned points: categorical colors; unassociated graph: red dots/lines; untracked: orange crosses\nLines connect native graph points, not independently accepted satellite predictions. No gray = unassociated convention.',fontsize=12)
        save(fig,out/f'context_RX{rx}.png')
    fig,axes=plt.subplots(2,1,figsize=(14,7),layout='constrained',sharex=True)
    for rx,ax in enumerate(axes,1):
        rr=[o for o in obs if o['receiver']==rx];s=ax.scatter([o['time_s'] for o in rr],[o['measured_cfo_hz']/1000 for o in rr],
            c=[o['fractional_margin'] for o in rr],s=8,cmap='viridis',vmin=0,vmax=1)
        ax.set(title=f'RX{rx}',ylabel='CFO (kHz)',xlabel='Scan time (s)')
    fig.colorbar(s,ax=axes,label='GLRT fractional winner margin (exported score diagnostic)');fig.suptitle(case+' · exported GLRT score context (raw GLRT statistic unavailable in native export)')
    save(fig,out/'glrt_score.png')
    return len(owners),len(obs)

def position(case,out):
    a=read(out/'audit.json');plan=read(out/'fit-plan.json');fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    for arm,ax in zip(ARMS,axes):
        r=a['arms'][arm];g=np.array(r['grid']);v=np.array(r['surface']);delta=v-v.min()
        im=ax.contourf(g,g,delta,levels=[0,2,5,10,20,40,80,160,320,640,1280,5000,50000],cmap='viridis',extend='max')
        ax.scatter(*SITE_X,c='white',edgecolor='black',marker='*',s=180,label='Evaluation site (diagnostic only)')
        ax.scatter(*r['x'],c='red',marker='X',s=90,label='Published endpoint')
        for n in plan['selected']:
            row=read(out/f'omit_{n}.json')[arm];ax.plot([r['x'][0],row['x'][0]],[r['x'][1],row['x'][1]],lw=.8,c='white')
            ax.scatter(*row['x'],s=35,c='white',edgecolor='black');ax.annotate(str(n),row['x'],fontsize=7,xytext=(3,3),textcoords='offset points')
        ax.set(title=arm,xlabel='East of regional center (km)',ylabel='North of regional center (km)',aspect='equal',xlim=(-12.5,12.5),ylim=(-12.5,12.5))
    axes[0].legend(fontsize=8,loc='upper left');fig.colorbar(im,ax=axes,label='Objective above sampled minimum')
    fig.suptitle(case+' · fixed-association, fixed-phase-reference 11 × 11 loss grid\nWhite endpoints: full position/phase refits after named family omission; arrows are endpoint displacements, not optimizer trajectories')
    save(fig,out/'loss_and_influence.png')
    tags=['continue','regional_center','phase_sigma_x2']+[f'omit_{n}' for n in plan['selected']]
    labels=['Published','Continue fit','Restart at regional center','Phase prior SD ×2']+[f'Omit {n}' for n in plan['selected']]
    fig,ax=plt.subplots(figsize=(11,5.5),layout='constrained');y=np.arange(len(labels))
    for arm,shift,col in [('c0',-.15,'#0072b2'),('fitted_c',.15,'#d55e00')]:
        values=[a['arms'][arm]['error_m']/1000]+[read(out/(tag+'.json'))[arm]['error_m']/1000 for tag in tags]
        ax.barh(y+shift,values,height=.28,color=col,label=arm)
    ax.invert_yaxis();ax.set(yticks=y,yticklabels=labels,xlabel='Position error (km)',title=case+' · matched diagnostic fits; omissions remove evidence, not deployable fixes');ax.legend()
    save(fig,out/'ablations.png')

def target_figures(case,out):
    targets=read(out/'targets.json');comparison=[]
    for target in targets:
        t=np.array(target['times_s']);raw=np.array(target['raw_unwrapped_hz']);corrected=np.array(target['corrected_hz']['fitted_c']);cal=raw-corrected
        fig,axes=plt.subplots(2,2,figsize=(14,8),layout='constrained');winners={}
        axes[0,0].scatter(t,wrap(raw)/1000,s=16,c='black',label='Native GLRT')
        axes[0,1].scatter(t,corrected/1000,s=16,c='black',label='GLRT minus frozen hardware')
        for regime,col in [('causal','#0072b2'),('later','#d55e00')]:
            rows=[r for r in target['results'] if r['regime']==regime and r['arm']=='fitted_c' and r['model']=='L3_phase'];rows.sort(key=lambda r:r['score'])
            if not rows:continue
            r=rows[0];winners[regime]=r;label=f"{regime}: {r['norad']}; phase {r['phase_s']:.1f}s; rate {r['rate_hz_s']:.2f}Hz/s"
            adj=np.array(r['prediction_adjusted_hz']);orbit=np.array(r['prediction_orbit_hz'])-r['alias']*PERIOD
            axes[0,0].plot(t,broken(t,wrap(adj+cal))/1000,c=col,label=label)
            axes[0,1].plot(t,orbit/1000,c=col,ls='--',alpha=.6,label=regime+' orbit at fitted phase')
            axes[0,1].plot(t,adj/1000,c=col,label=regime+' + offset/rate')
            axes[1,0].plot(t,r['residual_hz'],'.-',c=col,markersize=3,label=f"{regime}: RMS {r['rms_hz']:.1f}Hz; noise gate {r['noise']['noise_screen_pass']}")
            axes[1,1].hist(r['residual_hz'],bins=18,alpha=.4,color=col,label=regime)
            comparison.append(dict(target=target['index'],role=target['meta']['role'],assigned_norad=target['meta']['assigned_norad'],regime=regime,
                winner=r['norad'],runner_up=rows[1]['norad'] if len(rows)>1 else None,margin=rows[1]['score']-r['score'] if len(rows)>1 else None,
                phase_s=r['phase_s'],rate_hz_s=r['rate_hz_s'],rms_hz=r['rms_hz'],noise_pass=r['noise']['noise_screen_pass'],physical_pass=r['physical_screen_pass']))
        axes[1,0].axhline(0,c='black',lw=.7);axes[1,0].axhspan(-150,150,color='gray',alpha=.12,label='±150Hz diagnostic noise scale')
        for ax in axes.flat:ax.legend(fontsize=7)
        axes[0,0].set(ylabel='Wrapped native CFO (kHz)',xlabel='Scan time (s)');axes[0,1].set(ylabel='Alias-lifted corrected CFO (kHz)',xlabel='Scan time (s)')
        axes[1,0].set(ylabel='Residual (Hz)',xlabel='Scan time (s)');axes[1,1].set(xlabel='Residual (Hz)',ylabel='Points')
        fig.suptitle(f"{case} · target {target['index']}: {target['key']}\n{target['meta']['role']}; assigned {target['meta']['assigned_norad']}; {len(t)} points; no satellite identity accepted by this screen")
        save(fig,out/f"target-{target['index']}-orbit.png")
        poly=target['polynomial'];degree=poly['selected_degree'];r=poly['rows'][degree]
        fig,axes=plt.subplots(1,3,figsize=(15,4),layout='constrained')
        axes[0].plot(range(5),[v['bic'] for v in poly['rows']],'o-');axes[0].set(xlabel='Polynomial degree',ylabel='Descriptive BIC',title='Native points; fixed alias branch')
        axes[1].plot(t,r['residual'],'.-');axes[1].axhline(0,c='black');axes[1].set(xlabel='Time (s)',ylabel='Residual (Hz)',title=f"Degree {degree}; RMS {r['rms_hz']:.1f}Hz; lag1 {r['lag1']:.2f}")
        axes[2].hist(r['residual'],bins=16);axes[2].set(xlabel='Residual (Hz)',ylabel='Points',title=f"Endpoint leverage {r['endpoint_leverage'][0]:.2f}, {r['endpoint_leverage'][1]:.2f}")
        fig.suptitle(f"{case}, target {target['index']}: polynomial/noise audit; {len(target['pieces'])} parent graph piece(s)")
        save(fig,out/f"target-{target['index']}-polynomial.png")
        edges=np.arange(t.min(),t.max()+20,20);count=len(edges)-1
        fig,axes=plt.subplots(count,1,figsize=(11,3*count),squeeze=False,layout='constrained')
        for ax,lo,hi in zip(axes.flat,edges[:-1],edges[1:]):
            use=(t>=lo-1)&(t<=hi+1);ax.scatter(t[use],raw[use]/1000,c='black',s=18,label='All selected native points')
            ax.plot(t[use],np.array(r['prediction'])[use]/1000,c='green',label='Selected polynomial')
            for regime,col in [('causal','#0072b2'),('later','#d55e00')]:
                if regime in winners:ax.plot(t[use],(np.array(winners[regime]['prediction_adjusted_hz'])+cal)[use]/1000,c=col,label=regime+' candidate')
            ax.set(xlim=(lo,hi),xlabel='Scan time (s)',ylabel='Unwrapped CFO (kHz)');ax.legend(fontsize=8)
        fig.suptitle(f"{case} target {target['index']} · consecutive 20-second windows, ±1-second context")
        save(fig,out/f"target-{target['index']}-20s.png")
        fig,axes=plt.subplots(1,2,figsize=(12,6),layout='constrained');models=['L1_offset','L2_small_drift','L3_phase','L4_rate_discrepancy']
        numbers=sorted({r['norad'] for r in target['results']})
        shared_costs=[r['score'] for r in target['results'] if r['arm']=='fitted_c']
        color_norm=LogNorm(vmin=max(1,min(shared_costs)),vmax=max(2,max(shared_costs)))
        for regime,ax in zip(['causal','later'],axes):
            vals=np.full((len(numbers),4),np.nan)
            for r in target['results']:
                if r['regime']==regime and r['arm']=='fitted_c':vals[numbers.index(r['norad']),models.index(r['model'])]=r['score']
            im=ax.imshow(np.ma.masked_invalid(vals),norm=color_norm,aspect='auto',cmap='viridis')
            ax.set(xticks=range(4),xticklabels=['Offset','+ drift','+ phase','Rate SD 2'],yticks=range(len(numbers)),yticklabels=numbers,title=regime)
            fig.colorbar(im,ax=ax,label='Normalized diagnostic cost (lower better)')
        fig.suptitle(f"{case} target {target['index']} · matched candidate/model cells, shared color scale\nBlank = not shortlisted. Compare identities within a column; phase is profiled, not integrated. Per-source corrections are diagnostic.")
        save(fig,out/f"target-{target['index']}-models.png")
    with (out/'association_summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=comparison[0]);w.writeheader();w.writerows(comparison)

def family_figure(case,out):
    z=read(out/'family_diagnostic.json');n=z['suspect'];fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained')
    for col,cal in enumerate(['published','family_omitted']):
        for regime,color in [('causal','#0072b2'),('later','#d55e00')]:
            rr=[r for r in z['results'] if r['regime']==regime and r['calibration']==cal and r['arm']=='fitted_c' and r['split']=='all' and r['level']=='small_rate'];rr.sort(key=lambda r:r['score'])
            for r,style in [(rr[0],'-')]+[(v,':') for v in rr if v['norad']==n and v!=rr[0]]:
                for tr in z['tracks']:
                    use=np.array(r['group'])==tr['index'];axes[0,col].plot(np.array(r['times_s'])[use],np.array(r['residual_hz'])[use],style,alpha=.7,color=color,
                        label=f"{regime} {r['norad']}, rate {r['rate_hz_s']:.1f}Hz/s" if tr['index']==0 else None)
            axes[1,col].plot([str(r['norad']) for r in rr],[r['score'] for r in rr],'o',color=color,label=regime)
        axes[0,col].axhline(0,color='black');axes[0,col].set(title=cal+' position / calibration',ylabel='Family residual (Hz)',xlabel='Time (s)');axes[0,col].legend(fontsize=8)
        axes[1,col].set(xlabel='Candidate NORAD',ylabel='Joint diagnostic cost',yscale='log');axes[1,col].legend()
    fig.suptitle(f'{case}: does family {n} transfer across its {len(z["tracks"])} tracks?\nOne shared phase/rate per family, separate constant priors per track. Original identity dotted when another wins. No independent identity-validation claim.')
    save(fig,out/'family_transfer.png')
    g=read(out/'gate_validation.json');r=next(r for r in g if r['trial']=='published' and r['arm']=='fitted_c');fs=r['family_nuisance']
    fig,ax=plt.subplots(figsize=(13,4),layout='constrained');x=np.arange(len(fs));ax.bar(x-.18,[abs(v['phase_standardized']) for v in fs],width=.35,label='|Phase standardized coefficient|');ax.bar(x+.18,[max(abs(np.array(v['orbital_standardized'])),default=0) for v in fs],width=.35,label='Largest |orbital standardized coefficient|')
    ax.set(xticks=x,xticklabels=[v['norad'] for v in fs],ylabel='Magnitude in original prior units',title=case+' · nuisance pulls (heavy-tail precision changes phase interpretation)');ax.tick_params(axis='x',rotation=60);ax.legend();save(fig,out/'nuisance_pulls.png')

def run(case):
    out=ROOT/case;z=read(INPUT/(case+'.json'));d=reconstruct(z);contexts(case,z,d,out);position(case,out);target_figures(case,out);family_figure(case,out)
    print(case,'rendered',flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('case');run(p.parse_args().case)
