"""Compare residual transfer before and after fitted satellite corrections."""

import itertools
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from audit_ds23_learned_residuals import nearest_pairs
from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_causal_phase_mean import forecast_phase_mean
from probe_ds23_history_calibrated_phase import OUT as LEARNED
from probe_ds23_statistical_curvature import replay
from report_ds23_association_evidence import OUT,save_csv
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha,final_scan
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency


def run():
    OUT.mkdir(parents=True,exist_ok=True);cases=sorted(read(WEIGHTS/'protocol.json')['cases']);pairs=[];tracks=[]
    for case in cases:
        scan=final_scan(case);node=read(SOURCE/case/'result.json')['final_node']
        learned=read(LEARNED/(case+'.json'));primary=learned['results']['mean_and_distribution']
        keep=np.array(primary['mask'],bool);powers=np.array(read(WEIGHTS/case/'result.json')['results']['cross_rx_support']['weights'])
        model=learned['hyperparameters_from_pre_RF_TLE_only'];base=problem(scan,node,'c0',keep)
        _,receipt=phase_widths(scan,base.labels);means=forecast_phase_mean(receipt,model['shrinkage'])
        for arm in ('c0','fitted_c'):
            p,x=replay(scan,node,keep,arm,powers,means,model,primary['arms'][arm]);state=p.state(x);c=p.calculate(x)
            nominal,_=paired_phase_frequency(p.sky,p.flat_times,p.flat_labels,np.zeros(len(p.labels)),*latlon(x))
            before=p.values-p.q*nominal
            for i,sl in zip(p.members,p.slices,strict=True):
                t=scan.tracks[i];before[sl]-=scan.hardware(t,state['beta'])+p.q[sl]*(scan.rx_basis[i]@state['smooth'][t['receiver']-1])
            for stage,residual in [('nominal_TLE_fitted_receiver',before),('after_satellite_correction',c['conditional_residual_hz'])]:
                local=[]
                for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                    active=keep[sl]
                    if not active.any():continue
                    track=scan.tracks[i];r=residual[sl][active];r=r-r.mean();t=track['times'][active]
                    entry=dict(case=case,arm=arm,stage=stage,component=row['component'],norad=int(scan.norads[row['candidate_index']]),
                        receiver=track['receiver'],band=int(track['channel']>4),channel=track['channel'],points=len(r),
                        centered_RMS_hz=float(np.sqrt(np.mean(r*r))),time_s=t,residual_hz=r)
                    local.append(entry);tracks.append(entry)
                for a,b in itertools.combinations(local,2):
                    ia,ib=nearest_pairs(a['time_s'],b['time_s'])
                    if len(ia)<6:continue
                    aa,bb=a['residual_hz'][ia],b['residual_hz'][ib]
                    if min(np.std(aa),np.std(bb))<=0:continue
                    pairs.append(dict(case=case,arm=arm,stage=stage,left=a['component'],right=b['component'],
                        same_receiver=a['receiver']==b['receiver'],same_band=a['band']==b['band'],same_family=a['norad']==b['norad'],
                        pairs=len(ia),correlation=float(np.corrcoef(aa,bb)[0,1])))
        print(case,'satellite correction transfer',flush=True)
    summary=[]
    for arm,stage,rx,band,family in itertools.product(('c0','fitted_c'),('nominal_TLE_fitted_receiver','after_satellite_correction'),(True,False),(True,False),(True,False)):
        selected=[r for r in pairs if (r['arm'],r['stage'],r['same_receiver'],r['same_band'],r['same_family'])==(arm,stage,rx,band,family)]
        per_case=[np.median([r['correlation'] for r in selected if r['case']==case]) for case in cases if any(r['case']==case for r in selected)]
        summary.append(dict(arm=arm,stage=stage,same_receiver=rx,same_band=band,same_family=family,track_pairs=len(selected),scans=len(per_case),
            pooled_median_correlation=float(np.median([r['correlation'] for r in selected])) if selected else None,
            median_scan_median_correlation=float(np.median(per_case)) if per_case else None))
    save_csv(OUT/'satellite_correction_transfer_summary.csv',summary);save_csv(OUT/'satellite_correction_transfer_pairs.csv',pairs)
    write(OUT/'satellite_correction_transfer.json',dict(summary=summary,tracks=tracks,
        source_sha256=sha(Path(__file__)),GPS_used=False,both_stages_condition_on_same_jointly_fitted_receiver=True,
        no_claim_of_independent_or_causal_validation=True,stage_difference_is_phase_and_orbit_corrections_and_fragment_means=True))
    groups=[(True,True,False,'Same RX/band\ndifferent family'),(True,False,False,'Same RX\ndifferent band/family'),(False,True,True,'Same family/band\ndifferent RX')]
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),constrained_layout=True)
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        for stage,label in [('nominal_TLE_fitted_receiver','Before satellite correction'),('after_satellite_correction','After satellite correction')]:
            selected=[next(r for r in summary if (r['arm'],r['stage'],r['same_receiver'],r['same_band'],r['same_family'])==(arm,stage,rx,band,fam)) for rx,band,fam,_ in groups]
            ax.plot(range(3),[r['pooled_median_correlation'] for r in selected],'o-',label=label)
        ax.set_xticks(range(3),[g[-1] for g in groups],fontsize=8);ax.axhline(0,c='black',ls=':',lw=.7)
        ax.set(title=arm,ylabel='Median matched-track correlation',ylim=(-.2,1));ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Both satellite-common and receiver-common behavior can coexist\nSame fitted receiver in both stages; dependent post-fit pairs, not independent validation')
    fig.savefig(OUT/'satellite_correction_transfer.png',dpi=160);plt.close(fig)
    for r in summary:
        if r['arm']=='c0' and ((r['same_receiver'],r['same_band'],r['same_family']) in [(True,True,False),(True,False,False),(False,True,True)]):print(r,flush=True)


if __name__=='__main__':run()
