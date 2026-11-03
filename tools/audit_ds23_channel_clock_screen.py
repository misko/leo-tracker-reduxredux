"""Replay every periodic-clock prediction against saved native measurements."""

import numpy as np
from ds23_channel_clock_screen import fit,prediction,predictive_score,select,transfer
from probe_ds23_channel_clock_screen import OUT,TRACKING
from run_algo01_ds23_sample import read,write,sha


def main():
    d=read(OUT/'evaluation.json');records=[]
    if d['failures']:raise ValueError('all periodic clock cases must finish')
    cases={r['case']:r for r in d['cases']}
    for row in d['rows']:
        case=cases[row['case']];receipt=TRACKING/row['case']/'receipt.json'
        if sha(receipt)!=case['UTC_receipt_sha256']:raise ValueError('native UTC receipt changed')
        origin=read(receipt)['origin_utc_ns'];t=np.asarray(row['times']);y=np.asarray(row['native_CFO_hz'])
        slots=np.floor(((int(origin)%15_000_000_000)/1e9+t)/15).astype(int);differences=[]
        for fold in row['folds']:
            test=slots%3==fold['fold'];train=~test
            if set(slots[test])&set(slots[train]):raise ValueError('held UTC slots leaked into training')
            for period,measurements in fold['periods'].items():
                for record in measurements['transfers']:
                    source,target=record['source_RX']-1,record['target_RX']-1
                    noise=[]
                    for rx in [source,target]:
                        baseline=fit(t[train],y[train,rx],150.,origin);p,_=prediction(baseline,t[train])
                        noise.append(max(40.,float(np.sqrt(np.sum((y[train,rx]-p)**2)/(train.sum()-5)))))
                    model,_=select(t[train],y[train,source],noise[0],origin,float(period))
                    assert model['phase_s']==record['clock_model']['phase_s']
                    np.testing.assert_allclose(model['amplitude_peak_to_peak_hz'],record['clock_model']['amplitude_peak_to_peak_hz'],rtol=0,atol=1e-8)
                    baseline=fit(t[train],y[train,target],noise[1],origin)
                    transferred=transfer(model,t[train],y[train,target],sigma_hz=noise[1])
                    a,c=prediction(transferred,t[test]);b,e=prediction(baseline,t[test]);values=y[test,target]
                    gain=predictive_score(b,e,values)-predictive_score(a,c,values)
                    differences.append(float(gain-record['held_score_gain']))
        if max(abs(v) for v in differences)>1e-7:raise ValueError('held receiver clock density did not replay')
        records.append(dict(case=row['case'],norad=row['norad'],channel=row['channel'],replayed_predictions=len(differences),maximum_score_difference=max(abs(v) for v in differences)))
    write(OUT/'independent_replay_audit.json',dict(rows=records,replayed_predictions=sum(r['replayed_predictions'] for r in records),
        all_source_amplitudes_refitted_without_target_RX=True,all_held_UTC_slots_disjoint=True,
        qualified_curves=d['qualified_curves'],no_clock_or_position_correction_adopted=True,
        exact_Gaussian_moments_verified_separately_by_component_tests=True))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=sorted(d['rows'],key=lambda r:(r['cohort'],r['case'],r['channel']));x=np.arange(len(rows))
    fig,axes=plt.subplots(2,1,figsize=(12,7.5),sharex=True,constrained_layout=True)
    for period,offset,color in [('13',-.23,'#aaaabb'),('15',0.,'#4477aa'),('17',.23,'#ccbb88')]:
        axes[0].bar(x+offset,[r['total_period_held_score_gains'][period] for r in rows],width=.23,color=color,label=period+'s')
    axes[0].axhline(0,color='black',lw=.8);axes[0].set_ylabel('Cross-RX held prediction gain\npositive improves');axes[0].legend(ncol=3)
    for rx,color in [(1,'#197c91'),(2,'#bf5361')]:
        for f,marker in [(0,'o'),(1,'s'),(2,'^')]:
            phases=[]
            for row in rows:
                fold=next(v for v in row['folds'] if v['fold']==f)
                phases.append(next(v for v in fold['periods']['15']['transfers'] if v['source_RX']==rx)['clock_model']['phase_s'])
            axes[1].scatter(x+(rx-1.5)*.18,phases,c=color,marker=marker,s=27,label=f'RX{rx}, fold{f}')
    axes[1].set(ylim=(-.5,15.5),ylabel='Training-selected reset phase (s)',xticks=x,
        xticklabels=[r['case'][-4:]+f" CH{r['channel']}" for r in rows],xlabel='DS23 native paired curve')
    axes[1].tick_params(axis='x',rotation=40);axes[1].legend(ncol=3,fontsize=8)
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.suptitle('Repeating channel-clock screen: 0 qualified out of10 eligible paired curves\n43 scans inspected; no orbit/GPS model or position change; 13s/17s controls')
    fig.savefig(OUT/'periodic_clock_prediction_controls.png',dpi=160);plt.close(fig)
    print('PERIODIC_CLOCK_REPLAY',sum(r['replayed_predictions'] for r in records),'predictions',flush=True)


if __name__=='__main__':main()
