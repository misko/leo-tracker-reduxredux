"""Report every variant, selecting hypotheses by paired RF score, never GPS."""
import csv,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from experiment import OUT,PREVIOUS,PRIOR,INPUT,CASES,ARMS,METHODS,read,write

def csvfile(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
    flat=[];chosen=[];selections={};status={}
    for case in CASES:
        for method in METHODS:
            candidates=[];attempts=[]
            for path in sorted((OUT/case/method).glob('*.json')):
                z=read(path)
                if 'rows' not in z:continue
                for r in z['rows']:
                    attempts.append(r)
                    flat.append(dict(case=case,method=method,hypothesis=path.stem,arm=r['arm'],start=r['start'],status=r['status'],qualified=r['qualified'],
                        error_km=r.get('error_m',0)/1000 if 'error_m' in r else None,rf_score=r.get('objective'),ranking_score=r.get('ranking_score'),
                        phase_closed=r.get('phase_closed'),optimizer_success=r.get('optimizer_success'),all_gates_pass=r.get('all_gates_pass'),
                        minimum_gate_slack=r.get('minimum_gate_slack'),lost=len(r['lost_ids']) if 'lost_ids' in r else None,
                        reassigned=len(r['reassigned_ids']) if 'reassigned_ids' in r else None,seconds=r.get('seconds'),exception=r.get('exception'),reason=r.get('reason')))
                pair={a:min((r for r in z['rows'] if r['arm']==a and r['qualified']),key=lambda r:r['ranking_score'],default=None) for a in ARMS}
                if all(pair.values()):candidates.append((sum(r['ranking_score'] for r in pair.values()),path.stem,pair))
            selection=min(candidates,key=lambda r:r[0]) if candidates else None
            status[case+'/'+method]=dict(attempts=len(attempts),complete=sum(r['status']=='complete' for r in attempts),screened=sum(r['qualified'] for r in attempts))
            for arm in ARMS:
                r=selection[2][arm] if selection else None
                chosen.append(dict(case=case,method=method,arm=arm,hypothesis=selection[1] if selection else None,
                    error_km=r['error_m']/1000 if r else None,rf_score=r['objective'] if r else None,ranking_score=r['ranking_score'] if r else None,
                    rms_hz=r['rms_hz'] if r else None,phase_change_s=r['history'][-1]['phase_change_s'] if r else None,
                    lost=len(r['lost_ids']) if r else None,reassigned=len(r['reassigned_ids']) if r else None,
                    seconds=r['seconds'] if r else None,association_pct=100*len(read(INPUT/(case+'.json'))['baseline_owners'][arm])/len(read(__import__('pathlib').Path(read(INPUT/(case+'.json'))['native_path'])/'observations.json')) if r else None))
                if r:selections[(case,method,arm)]=r
    csvfile(OUT/'all_trials.csv',flat);csvfile(OUT/'selected_variants.csv',chosen)
    previous=read(PREVIOUS/'summary.json')['selected'];baselines={c:read(PRIOR/c/'audit.json')['arms'] for c in CASES}
    labels=['Published ALGO06','Previous constrained control','01 Phase damping','02 Inner phase solve','03 Regional multistart','04 Receiver smoothness shrinkage','05 Orbital prior shrinkage','06 Age-dependent uncertainty','07 Shared satellite rate','08 Track-family partition','09 Joint-family replacement','10 Interior gate margin']
    fig,axs=plt.subplots(1,2,figsize=(15,9),sharey=True,layout='constrained')
    for ax,arm in zip(axs,ARMS):
        matrix=np.full((12,4),np.nan)
        for j,c in enumerate(CASES):
            matrix[0,j]=baselines[c][arm]['error_m']/1000
            matrix[1,j]=next(r['error_km'] for r in previous if r['case']==c and r['arm']==arm and r['constrained'] and r['policy']=='none')
            for i,m in enumerate(METHODS,2):matrix[i,j]=next(r['error_km'] for r in chosen if r['case']==c and r['arm']==arm and r['method']==m) or np.nan
        cmap=plt.colormaps['viridis_r'].copy();cmap.set_bad('#dddddd');im=ax.imshow(matrix,cmap=cmap,vmin=0,vmax=8,aspect='auto')
        for (i,j),v in np.ndenumerate(matrix):ax.text(j,i,f'{v:.2f}' if np.isfinite(v) else 'rejected',ha='center',va='center',fontsize=9,color='white' if np.isfinite(v) and v>4 else 'black')
        ax.set_xticks(range(4),[c[-4:] for c in CASES]);ax.set_yticks(range(12),labels,fontsize=9);ax.set_title('c = 0' if arm=='c0' else 'Fitted c');ax.set_xlabel('DS26 scan')
    fig.colorbar(im,ax=axs,label='Position error (km; color capped at 8)',shrink=.7)
    fig.suptitle('Ten development prototypes: best paired-screened hypothesis by RF score\nGray = no hypothesis passes both c arms; no silent fallback. No held-out validation implied.')
    fig.savefig(OUT/'ten_methods.png',dpi=165);plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,5));colors=plt.colormaps['tab10']
    for j,c in enumerate(CASES):
        control=next(r for r in previous if r['case']==c and r['arm']=='fitted_c' and r['constrained'] and r['policy']=='none')
        base_score=baselines[c]['fitted_c']['objective']-control['rf_gain']
        for r in chosen:
            if r['case']!=c or r['arm']!='fitted_c' or r['error_km'] is None:continue
            xx=base_score-r['ranking_score'];yy=control['error_km']-r['error_km']
            ax.scatter(xx,yy,c=[colors(j)],s=40);ax.annotate(r['method'][:2],(xx,yy),fontsize=8,xytext=(3,3),textcoords='offset points')
        ax.scatter([],[],c=[colors(j)],label=c)
    ax.axhline(0,c='k',lw=.8);ax.axvline(0,c='k',lw=.8);ax.set_xscale('symlog',linthresh=1)
    ax.set(xlabel='RF ranking-score improvement over previous control',ylabel='Position-error improvement over control (km)',title='Better RF score does not guarantee better position\nNumbers identify the ten methods');ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(OUT/'score_vs_accuracy.png',dpi=165);plt.close(fig)
    pred=read(OUT/'predictive_results.json');fig,axs=plt.subplots(1,2,figsize=(11,4),sharey=True)
    for ax,a in zip(axs,ARMS):
        rows=[r for r in pred['results'] if r['arm']==a];g=np.array([r['held_gain_over_training_best_single'] for r in rows])
        ax.bar(np.arange(10),g,color=np.where(g>=0,'tab:green','tab:red'));ax.axhline(0,c='black',lw=.8)
        ax.axhline(g.mean(),ls='--',c='tab:blue',label=f'Mean {g.mean():.2f}')
        ax.set(title=f'{a}: {sum(g>0)}/10 predictive wins',xlabel='Random held-block partition');ax.legend();ax.grid(axis='y',alpha=.2)
    axs[0].set_ylabel('Held-out score gain from learned partition\nPositive = partition better')
    fig.suptitle('0070 conditional predictive check: 5 s blocks + 5 s guard; aliases and labels trained without held points')
    fig.tight_layout();fig.savefig(OUT/'predictive_check.png',dpi=165);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(10,6),sharey=True)
    nums=[62320,63571,67047]
    for ax,a in zip(axs,ARMS):
        rows=[r for r in pred['results'] if r['arm']==a];counts=np.array([[sum(r['learned_mapping'][str(k)]==n for r in rows) for n in nums] for k in range(len(pred['track_keys']))])
        im=ax.imshow(counts,vmin=0,vmax=10,cmap='Blues',aspect='auto')
        for (i,j),v in np.ndenumerate(counts):ax.text(j,i,str(v),ha='center',va='center',color='white' if v>5 else 'black')
        ax.set_xticks(range(3),list(map(str,nums)));ax.set_yticks(range(9),[k.split('-RF')[0].removeprefix('SCAN-') for k in pred['track_keys']]);ax.set_title(a);ax.set_xlabel('Learned satellite identity')
    fig.suptitle('0070 identity stability across ten randomized training subsets\nCounts are not calibrated satellite probabilities');fig.tight_layout();fig.savefig(OUT/'partition_stability.png',dpi=165);plt.close(fig)
    # Native CFO colored by the proposed partition, without interpolated samples.
    r=selections.get(('DS26-0070','08_fragment_partition','fitted_c'))
    if r:
        from pathlib import Path
        z=read(INPUT/'DS26-0070.json');obs={o['observation_id']:o for o in read(Path(z['native_path'])/'observations.json')}
        fig,axs=plt.subplots(2,4,figsize=(14,7),sharex=True,layout='constrained')
        for ax,ch in zip(axs.flat,[1,5,6,7,8,2,3,4]):
            for t in r['tracks']:
                if t['channel']!=ch:continue
                os=[obs[o] for o in t['observation_ids']];n=t['norad'];color='tab:blue' if n==63571 else 'tab:orange'
                ax.scatter([o['time_s'] for o in os],[o['measured_cfo_hz']/1000 for o in os],s=12,c=color,marker='o' if t['receiver']==1 else 'x')
            ax.set(title=f'CH{ch}',xlabel='Time (s)',ylabel='Native CFO (kHz)');ax.grid(alpha=.2)
        fig.suptitle('DS26-0070: the 366-point family previously labeled 62320\nBlue 63571; orange 67047; circles RX1, crosses RX2. Proposed identities, not proven truth.')
        fig.savefig(OUT/'partition_native_cfo.png',dpi=165);plt.close(fig)
        fig,axs=plt.subplots(2,1,figsize=(10,6),sharex=True)
        for ax,n in zip(axs,[63571,67047]):
            for t in r['tracks']:
                if t['norad']==n:ax.plot(t['times_s'],t['residual_hz'],'.-',ms=3,label=t['component'].split('-RF')[0].removeprefix('SCAN-'))
            ax.axhline(0,c='black',lw=.8);ax.set(title=f'Proposed {n}',ylabel='Residual (Hz)');ax.legend(fontsize=7,ncol=2);ax.grid(alpha=.2)
        axs[-1].set_xlabel('Time (s)');fig.tight_layout();fig.savefig(OUT/'partition_residuals.png',dpi=165);plt.close(fig)
    write(OUT/'summary.json',dict(selected=chosen,status=status,total_trials=len(flat),complete=sum(r['status']=='complete' for r in flat),incomplete=sum(r['status']!='complete' for r in flat),
        selection='RF-ranked among hypotheses passing both c arms; no automatic cross-method winner; no fallback hidden in gray cells',
        predictive_summary={a:dict(wins=sum(r['held_gain_over_training_best_single']>0 for r in pred['results'] if r['arm']==a),
            mean_gain=float(np.mean([r['held_gain_over_training_best_single'] for r in pred['results'] if r['arm']==a])),
            median_gain=float(np.median([r['held_gain_over_training_best_single'] for r in pred['results'] if r['arm']==a])),
            training_selects_partition=sum(r['training_selects_partition'] for r in pred['results'] if r['arm']==a)) for a in ARMS}))
    print('Trials',len(flat),'completed',sum(r['status']=='complete' for r in flat))

if __name__=='__main__':main()
