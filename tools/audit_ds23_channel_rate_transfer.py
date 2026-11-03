"""Replay channel-rate predictions and separate mean from covariance effects."""

import numpy as np
from ds23_channel_rate_transfer import designs,fit,baseline_prediction,transfer
from ds23_channel_clock_screen import predictive_score
from probe_ds23_channel_rate_transfer import OUT
from run_algo01_ds23_sample import read,write,sha


def main():
    path=OUT/'evaluation.json';d=read(path)
    if d['failures']:raise ValueError('all channel-rate screens must finish')
    result=[]
    for row in d['rows']:
        all_times=np.r_[row['data']['1']['times'],row['data']['2']['times']];center=float(np.mean(all_times));scale=max(1.,float(np.ptp(all_times)/2))
        data={}
        for rx in [1,2]:
            r=row['data'][str(rx)];b,c=designs(r['times'],r['channels'],r['fragments'],row['channels'],sorted(set(r['fragments'])),center_s=center,scale_s=scale)
            data[rx]=dict(times=np.array(r['times']),values=np.array(r['values']),sigma=np.array(r['sigma']),slots=np.array(r['slots']),base=b,clock=c)
        predictions=[]
        for fold in row['folds']:
            fitted={}
            for rx,r in data.items():
                test=r['slots']%3==fold['fold'];train=~test
                fitted[rx]=dict(test=test,train=train,
                    null=fit(r['base'][train],np.zeros((train.sum(),0)),r['values'][train],r['sigma'][train]),
                    model=fit(r['base'][train],r['clock'][train],r['values'][train],r['sigma'][train]))
            for original in fold['transfers']:
                source,target=original['source_RX'],original['target_RX'];r=data[target];train,test=fitted[target]['train'],fitted[target]['test']
                model=fitted[source]['model'];width=model['base_width']
                np.testing.assert_allclose(model['coefficient'][width:],original['source_clock_contrast_mean'],rtol=0,atol=1e-7)
                a,c=transfer(model,fitted[target]['null'],r['base'][train],r['clock'][train],r['sigma'][train],r['base'][test],r['clock'][test],r['sigma'][test])
                b,e=baseline_prediction(fitted[target]['null'],r['base'][test],r['sigma'][test]);values=r['values'][test]
                score=predictive_score(b,e,values);gain=score-predictive_score(a,c,values)
                if abs(gain-original['held_score_gain'])>1e-6:raise ValueError('channel-rate held prediction changed')
                predictions.append(dict(source_RX=source,fold=fold['fold'],score_replay_difference=gain-original['held_score_gain'],
                    full_gain=gain,mean_only_gain=score-predictive_score(a,e,values),
                    covariance_only_gain=score-predictive_score(b,c,values),
                    baseline_squared_error=float(np.sum((values-b)**2)),transferred_squared_error=float(np.sum((values-a)**2))))
        result.append(dict(case=row['case'],cohort=row['cohort'],norad=row['norad'],channels=row['channels'],qualified=row['qualified'],
            checks=row['checks'],predictions=predictions,full_gain=sum(r['full_gain'] for r in predictions),
            mean_only_gain=sum(r['mean_only_gain'] for r in predictions),covariance_only_gain=sum(r['covariance_only_gain'] for r in predictions)))
    write(OUT/'independent_replay_audit.json',dict(rows=result,replayed_predictions=sum(len(r['predictions']) for r in result),
        qualified_families=sum(r['qualified'] for r in result),native_input_evaluation_sha256=sha(path),
        no_clock_or_position_correction_adopted=True,RF_predictive_density_not_position_accuracy=True,
        mean_and_covariance_gains_are_counterfactuals_not_additive_components=True))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=sorted(result,key=lambda r:r['full_gain'],reverse=True);x=np.arange(len(rows))
    fig,axes=plt.subplots(1,2,figsize=(13,4.8),constrained_layout=True)
    for cohort,color in [('development','#3e7e9e'),('scan_disjoint_confirmation','#c96e4b')]:
        indices=[k for k,r in enumerate(rows) if r['cohort']==cohort]
        axes[0].scatter(indices,[rows[k]['full_gain'] for k in indices],s=24,c=color,label=cohort.replace('_',' '))
    axes[0].axhline(0,color='black',lw=.8);axes[0].set(xlabel='Family ranked by total held prediction gain',ylabel='Cross-RX channel-rate predictive gain')
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    largest=rows[:6];xx=np.arange(len(largest));width=.25
    for field,offset,color,label in [('full_gain',-width,'#4477aa','Full'),('mean_only_gain',0.,'#66aa99','Mean only'),('covariance_only_gain',width,'#cc6677','Covariance only')]:
        axes[1].bar(xx+offset,[r[field] for r in largest],width,color=color,label=label)
    axes[1].set(xticks=xx,xticklabels=[r['case'][-4:]+f"\n{r['norad']}" for r in largest],ylabel='Counterfactual predictive gain',xlabel='Six highest-scoring families')
    axes[1].axhline(0,color='black',lw=.8);axes[1].legend(fontsize=8)
    fig.suptitle('Channel-relative clock rates: 0 qualified out of50 supported families\nOther-family radio calibration; other-RX held-slot prediction; no position update')
    fig.savefig(OUT/'channel_rate_prediction_controls.png',dpi=160);plt.close(fig)
    print('CHANNEL_RATE_REPLAY',sum(len(r['predictions']) for r in result),'predictions; zero qualified',flush=True)


if __name__=='__main__':main()
