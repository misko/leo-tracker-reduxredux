"""DBG01 per-family/RX/band fragment corrections at fixed diagnostic locations."""

from concurrent.futures import ProcessPoolExecutor
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from diagnose_ds23_conditioned_relative_loss import CASES,REFERENCE_XY
from ds23_fragment_offset_diagnostics import contrast_summary
from probe_ds23_conditioned_relative_nomination import OUT
from probe_ds23_conditioned_relative_position import OUT as POSITION,context_selected
from probe_ds23_joint_relative_position import make
from run_algo01_ds23_sample import read,write,sha


def one(case):
    d=context_selected(case,'conditioned_best');saved=read(POSITION/(case+'_conditioned_best.json'));snapshots=[]
    for arm in ['c0','fitted_c']:
        for name,x in [('selected_endpoint',np.asarray(saved['arms'][arm]['endpoint_east_north_km'])),('evaluation_reference',REFERENCE_XY)]:
            reference=np.zeros(len(d['all_labels']))
            for _ in range(10):
                p=make(d,arm,reference,True,float(np.sqrt(2)*300));phase=np.clip(p.state(x)['phases'][d['all_labels']],-15,15)
                change=float(np.max(abs(phase-reference)));reference=phase
            c=p.calculate(x);indices=np.arange(p.joint_old_width-len(p.members),p.joint_old_width)
            coefficient=c['coefficient'][indices];cov=np.linalg.inv(c['joint_calibration_precision'])[np.ix_(indices,indices)]*1e6
            bias=1000*coefficient;tracks=[]
            for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
                t=p.scan.tracks[i];active=p.keep[sl];q=t['rf_hz']/11.5e9
                tracks.append(dict(component=t['key'],norad=row['candidate_norad'],candidate_index=row['candidate_index'],
                    receiver=t['receiver'],channel=t['channel'],band='low' if t['channel']<=4 else 'high',rf_hz=t['rf_hz'],
                    points=int(active.sum()),start_s=float(t['times'][active].min()) if active.any() else None,
                    end_s=float(t['times'][active].max()) if active.any() else None,
                    bias_hz=float(bias[k]),bias_reference_RF_hz=float(bias[k]/q),conditional_SD_hz=float(np.sqrt(cov[k,k])),
                    fragment_prior_cost=float((bias[k]/300)**2)))
            snapshots.append(dict(case=case,arm=arm,point=name,position_east_north_km=x,phase_change_s=change,
                loss=c['negative_twice_elbo'],tracks=tracks,fragment_covariance_hz2=cov))
    groups=[]
    for arm in ['c0','fitted_c']:
        selected=next(r for r in snapshots if r['arm']==arm and r['point']=='selected_endpoint')
        truth=next(r for r in snapshots if r['arm']==arm and r['point']=='evaluation_reference')
        tracks=selected['tracks'];q=np.array([t['rf_hz']/11.5e9 for t in tracks]);weights=np.array([t['points'] for t in tracks])
        for norad in sorted({t['norad'] for t in tracks if t['points']}):
            indices=[k for k,t in enumerate(tracks) if t['norad']==norad and t['points']]
            receivers=sorted({tracks[k]['receiver'] for k in indices});bands=sorted({tracks[k]['band'] for k in indices})
            row=dict(case=case,arm=arm,norad=norad,components=len(indices),points=int(weights[indices].sum()),receivers=receivers,bands=bands,
                fragment_prior_cost_change=sum(truth['tracks'][k]['fragment_prior_cost']-tracks[k]['fragment_prior_cost'] for k in indices),
                points_selected_and_reference_identical=True)
            for snap in [selected,truth]:
                mu=np.array([t['bias_reference_RF_hz'] for t in snap['tracks']]);cov=np.asarray(snap['fragment_covariance_hz2'])/q[:,None]/q[None,:]
                row[snap['point']]=dict(mean=contrast_summary(mu,cov,indices,weights=weights),
                    by_receiver={str(rx):contrast_summary(mu,cov,[k for k in indices if tracks[k]['receiver']==rx],weights=weights) for rx in receivers})
                if len(receivers)==2:
                    row[snap['point']]['RX1_minus_RX2']=contrast_summary(mu,cov,[k for k in indices if tracks[k]['receiver']==1],
                        [k for k in indices if tracks[k]['receiver']==2],weights=weights)
            groups.append(row)
    return dict(case=case,snapshots=snapshots,groups=groups,context_sha256=sha(POSITION/(case+'_conditioned_best.json')),
        actual_fragment_penalty_reconstructed_from_native300Hz_prior=True,
        covariance_conditioned_on_model_Gamma_and_labels=True,reference_position_used_only_for_diagnosis=True)


def main():
    with ProcessPoolExecutor(max_workers=3) as pool:cases=list(pool.map(one,CASES))
    write(OUT/'fragment_offsets_by_family_RX_band.json',dict(cases=cases,posterior_descriptive_diagnostics_only=True,
        no_GPS_selected_model_hyperparameter_or_identity=True))
    for case in cases:
        rows=[r for r in case['groups'] if r['arm']=='fitted_c'];order=sorted(rows,key=lambda r:abs(r['fragment_prior_cost_change']),reverse=True)
        fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
        selected=next(s for s in case['snapshots'] if s['arm']=='fitted_c' and s['point']=='selected_endpoint')
        truth=next(s for s in case['snapshots'] if s['arm']=='fitted_c' and s['point']=='evaluation_reference')
        lookup={r['norad']:k for k,r in enumerate(order)}
        colors={(1,'low'):'#1f77b4',(1,'high'):'#17becf',(2,'low'):'#ff7f0e',(2,'high'):'#d62728'}
        shown=set()
        for a,b in zip(selected['tracks'],truth['tracks'],strict=True):
            if not a['points']:continue
            key=a['receiver'],a['band'];label=f'RX{key[0]} {key[1]}'
            axes[0].scatter(lookup[a['norad']],b['bias_reference_RF_hz']-a['bias_reference_RF_hz'],c=colors[key],
                marker='o' if key[1]=='low' else '^',s=30,label=label if key not in shown else None);shown.add(key)
        axes[0].set_xticks(range(len(order)),[r['norad'] for r in order],rotation=80,fontsize=7)
        axes[0].set(xlabel='Original GLRT satellite family',ylabel='Reference minus endpoint fragment correction (reference Hz)')
        axes[0].axhline(0,color='black',lw=.7);axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
        axes[1].barh(range(len(order)),[r['fragment_prior_cost_change'] for r in order],color='#8765b4')
        axes[1].set_yticks(range(len(order)),[r['norad'] for r in order],fontsize=8);axes[1].invert_yaxis();axes[1].axvline(0,c='black',lw=.7)
        axes[1].set(xlabel='Fragment prior cost: reference minus endpoint');axes[1].grid(axis='x',alpha=.2)
        fig.suptitle(case['case']+' · fragment-offset diagnosis by satellite, receiver and band\nSame observations and priors; fixed-location posterior summaries, not measured hardware offsets')
        fig.savefig(OUT/(case['case']+'_fragment_offsets.png'),dpi=160);plt.close(fig)
        print(case['case'],'top_families',[(r['norad'],round(r['fragment_prior_cost_change'],3),r['receivers'],r['bands']) for r in order[:5]],flush=True)
        print('cross_RX',[(r['norad'],r['evaluation_reference'].get('RX1_minus_RX2')) for r in order if len(r['receivers'])==2],flush=True)


if __name__=='__main__':main()
