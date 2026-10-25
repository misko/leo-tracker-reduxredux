"""Source-bound saved-result summaries and affine CFO overlays; no new inference."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
OUT=HERE/'report'
ARMS=('c0','fitted_c')
NAMES=('whole_control','cut14_prefix','cut14_suffix','cut21_prefix','cut21_suffix','cut29_prefix','cut29_suffix')
read=lambda path:json.loads(Path(path).read_bytes())
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()


def table(name,rows):
    with (OUT/name).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    seal=read(HERE/'RF_seal.json')
    for path,digest in seal['files'].items():
        if sha(path)!=digest:raise ValueError('scientific file changed: '+path)
    OUT.mkdir(exist_ok=False)
    screens={};proposals=[];contexts=[];full=[];overlays=[]
    for arm in ARMS:
        for name in NAMES:
            d=read(HERE/arm/(name+'_screen.json'));screens[(arm,name)]=d
            ranks={index:rank for rank,index in enumerate(d['ranked_visible_indices'],1)}
            norads=d['catalogue_norads'];top=d['candidate_indices'];eligible=d['original_eligibility']
            with np.load(HERE/arm/(name+'_overlay.npz')) as a:
                rms=np.sqrt(np.mean(a['residual_Hz']**2,axis=1))
                for rank,j in enumerate(top,1):
                    proposals.append(dict(arm=arm,source=name,rank=rank,candidate_index=j,norad=norads[j],
                        coarse_objective=d['coarse_scores'][j],causal_phase_mean_s=float(np.load(HERE/'inputs/catalogue.npz')['phase_means_s'][j]),
                        affine_phase_mean_s=d['linear_phase_mean_s'][j],affine_phase_SD_s=d['linear_phase_SD_s'][j],
                        phase_z=d['phase_z'][j],nearest_integer_alias=d['coarse_aliases'][j][0],
                        phase_in_operational_domain=d['phase_mean_in_operational_domain'][j],alias_in_finite_exact_support=d['nearest_alias_in_finite_exact_support'][j],
                        retained_parent_active=j in d['existing_parent_active_candidate_indices'],
                        legacy_supported_mode_slot=j in d['existing_parent_supported_candidate_indices'],
                        affine_overlay_RMS_Hz=float(rms[rank-1]),exact_evidence=False,accepted=False))
                    for i,oid in enumerate(a['native_ids']):
                        overlays.append(dict(arm=arm,source=name,rank=rank,norad=norads[j],native_id=str(oid),
                            time_s=float(a['times_s'][i]),observed_native_CFO_Hz=float(a['observed_native_CFO_Hz'][i]),
                            affine_native_CFO_Hz=float(a['predicted_affine_native_CFO_Hz'][rank-1,i]),residual_Hz=float(a['residual_Hz'][rank-1,i])))
            contexts.append(dict(arm=arm,source=name,points=len(d['native_IDs']),**eligible,
                winner=norads[top[0]],winner_coarse_objective=d['coarse_scores'][top[0]],
                winner_affine_phase_s=d['linear_phase_mean_s'][top[0]],winner_alias=d['coarse_aliases'][top[0]][0],
                coarse_score_gap_to_rank2=d['coarse_scores'][top[1]]-d['coarse_scores'][top[0]],
                rank57450=ranks.get(norads.index(57450)),rank65871=ranks.get(norads.index(65871)),
                complete_catalogue_count=d['catalogue_count'],visible_catalogue_count=len(ranks)))
            for j,norad in enumerate(norads):
                full.append(dict(arm=arm,source=name,candidate_index=j,norad=norad,visible_rank=ranks.get(j),
                    mean_LOS_eligible=j in ranks,coarse_objective=d['coarse_scores'][j],alias=d['coarse_aliases'][j][0],
                    affine_phase_s=d['linear_phase_mean_s'][j],phase_in_domain=d['phase_mean_in_operational_domain'][j],
                    alias_in_finite_support=d['nearest_alias_in_finite_exact_support'][j]))
    table('contexts.csv',contexts);table('top8_proposals.csv',proposals);table('catalogue_scores.csv',full);table('native_CFO_overlays.csv',overlays)

    fig,axes=plt.subplots(1,2,figsize=(12,5.5),layout='constrained',sharey=True)
    for ax,arm in zip(axes,ARMS):
        rows=[row for row in contexts if row['arm']==arm]
        y=np.arange(7)
        ax.plot([row['rank57450'] for row in rows],y,'o-',color='#00796b',label='57450')
        ax.plot([row['rank65871'] for row in rows],y,'s--',color='#c05922',label='65871')
        ax.set_yticks(y,[name.replace('_',' ') for name in NAMES]);ax.set_ylim(6.5,-.5)
        ax.set_xticks(range(1,8));ax.set_xlim(.7,7.5);ax.set_xlabel('Ordinary full-catalogue visible rank (lower is better)')
        ax.set_title('c = 0' if arm=='c0' else 'Fitted c');ax.grid(axis='x',alpha=.2);ax.legend()
    fig.suptitle('Every frozen portion and whole-source control\nTwo labels highlighted after nomination; all1487 scores saved. Overlapping portions are not independent evidence.',fontsize=11)
    fig.savefig(OUT/'ordinary_ranks.png',dpi=180);plt.close(fig)

    for arm in ARMS:
        fig,axes=plt.subplots(4,2,figsize=(13,14),layout='constrained')
        for ax,name in zip(axes.ravel(),NAMES):
            with np.load(HERE/arm/(name+'_overlay.npz')) as a:
                ax.scatter(a['times_s'],a['observed_native_CFO_Hz']/1000,s=12,color='black',label='Original native CFO',zorder=3)
                for index,color in enumerate(['#00796b','#c05922','#5267ae']):
                    ax.plot(a['times_s'],a['predicted_affine_native_CFO_Hz'][index]/1000,color=color,lw=1.1,
                        label=f"Rank{index+1}: {a['norads'][index]}, phase {a['phase_means_s'][index]:+.3f}s, alias {a['aliases'][index]}")
                row=next(row for row in contexts if row['arm']==arm and row['source']==name)
                ax.set_title(f"{name.replace('_',' ')} · {row['points']} IDs · {row['duration_s']:.3f}s",fontsize=10)
                ax.set_xlabel('Scan time (s)');ax.set_ylabel('Native CFO (kHz)');ax.grid(alpha=.2);ax.legend(fontsize=7)
        axes.ravel()[-1].axis('off')
        axes.ravel()[-1].text(0,.9,'Top3 nominees shown; all8 overlays are saved.\n\nCurves are the Gaussian-affine phase proposal,\nplus fixed background radio mean.\nNo exact propagation at the proposed phase,\nnew physical-mode fit or owner-constant fit.\n\nNative CFO = graph CFO + 2 × PERIOD.\nNo accepted source, gate waiver or position fit.',va='top',fontsize=11)
        fig.suptitle(('c = 0' if arm=='c0' else 'Fitted c')+' · conditional-mean affine nomination overlays',fontsize=13)
        fig.savefig(OUT/('native_CFO_'+arm+'.png'),dpi=150);plt.close(fig)

    summary=dict(contexts=contexts,completed_screens=14,full_catalogue_rows=len(full),top8_rows=len(proposals),native_overlay_rows=len(overlays),
        top8_identical_between_arms=all(screens[('c0',name)]['candidate_norads']==screens[('fitted_c',name)]['candidate_norads'] for name in NAMES),
        portion_original_duration_curvature_passes=sum(row['original_duration_and_curvature_eligible'] for row in contexts if row['source']!='whole_control'),
        execution=read(HERE/'execution.json'),new_scores=0,new_propagation=0,new_fits=0,GPS_used=False)
    with (OUT/'summary.json').open('x') as stream:json.dump(summary,stream,indent=2,allow_nan=False);stream.write('\n')
    files={str(path):sha(path) for path in sorted(OUT.iterdir()) if path.is_file()};files[str(Path(__file__))]=sha(__file__)
    with (OUT/'report_seal.json').open('x') as stream:json.dump(dict(files=files,RF_seal_sha256=sha(HERE/'RF_seal.json'),terminal_audit_sha256=sha(HERE.parent/'audit/portions_terminal.json')),stream,indent=2);stream.write('\n')
    print(json.dumps({key:summary[key] for key in ['completed_screens','full_catalogue_rows','top8_rows','native_overlay_rows','top8_identical_between_arms']}))


if __name__=='__main__':main()
