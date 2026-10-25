"""RF-only receiver witness report; no position-evaluation coordinate input."""
from pathlib import Path
import csv
import json
import numpy as np

HERE=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text())
def stats(values):
    x=np.asarray(values,float)
    return dict(n=len(x),mean=float(x.mean()),median=float(np.median(x)),minimum=float(x.min()),maximum=float(x.max()),improved=int((x<0).sum()))

def main():
    protocol=read(HERE/'protocol.json');selection=read(HERE/'selection.json');outputs=[read(HERE/(c+'.json')) for c in protocol['cases']]
    rows=[];summary={}
    configurations=['baseline/native']+[m+'/'+c for m in protocol['candidates'] for c in ('native','wrong_RX','shift75')]
    for output in outputs:
        for fold in output['folds']:
            for configuration,result in fold['results'].items():
                rows.append(dict(case=output['case'],fold=fold['fold'],configuration=configuration,
                    train_points=fold['train_points'],test_points=fold['test_points'],dimension=result['dimension'],
                    negative_twice_log_density=result['negative_twice_log_density'],gain_vs_baseline=result['gain_vs_baseline'],
                    quadratic=result['quadratic'],logvolume=result['logvolume'],predictive_mean_contrast_RMS_hz=result['predictive_mean_contrast_RMS_hz']))
    for configuration in configurations:
        ss=[r for r in rows if r['configuration']==configuration];n=sum(r['dimension'] for r in ss)
        summary[configuration]=dict(dimension=n,total_negative_twice_log_density=sum(r['negative_twice_log_density'] for r in ss),
            total_gain=sum(r['gain_vs_baseline'] for r in ss),quadratic=sum(r['quadratic'] for r in ss),logvolume=sum(r['logvolume'] for r in ss),
            pooled_predictive_mean_RMS_hz=float(np.sqrt(sum(r['dimension']*r['predictive_mean_contrast_RMS_hz']**2 for r in ss)/n)))
    percase={};family=[]
    for configuration in configurations[1:]:
        case_rows=[]
        for output in outputs:
            def rms(method):
                rr=[f['results'][method] for f in output['folds']]
                return float(np.sqrt(sum(x['dimension']*x['predictive_mean_contrast_RMS_hz']**2 for x in rr)/sum(x['dimension'] for x in rr)))
            case_rows.append(dict(case=output['case'],gain=sum(f['results'][configuration]['gain_vs_baseline'] for f in output['folds']),
                baseline_RMS_hz=rms('baseline/native'),candidate_RMS_hz=rms(configuration),RMS_change_hz=rms(configuration)-rms('baseline/native')))
            for fold in output['folds']:
                for a,b in zip(fold['results'][configuration]['family_predictions'],fold['results']['baseline/native']['family_predictions'],strict=True):
                    assert a['norad']==b['norad']
                    family.append(dict(case=output['case'],fold=fold['fold'],configuration=configuration,norad=a['norad'],points=a['points'],dimension=a['dimension'],
                        marginal_family_density_gain=b['negative_twice_log_density']-a['negative_twice_log_density'],
                        baseline_RMS_hz=b['predictive_mean_contrast_RMS_hz'],candidate_RMS_hz=a['predictive_mean_contrast_RMS_hz'],
                        RMS_change_hz=a['predictive_mean_contrast_RMS_hz']-b['predictive_mean_contrast_RMS_hz']))
        percase[configuration]=case_rows
        summary[configuration]['case_RMS_change_hz']=stats([r['RMS_change_hz'] for r in case_rows])
        summary[configuration]['family_RMS_change_hz']=stats([r['RMS_change_hz'] for r in family if r['configuration']==configuration])
    for name,data in [('fold_scores.csv',rows),('family_scores.csv',family)]:
        with (HERE/name).open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
    data=dict(summary=summary,per_case=percase,total_active_points=sum(r['audit']['active_points'] for r in outputs),
        family_scan_blocks=sum(len(r['families']) for r in outputs),eligible_family_scan_blocks=sum(sum(f['eligible'] for f in r['families']) for r in outputs),
        all_24_retained=True,whole_family_folds=72,selected_method=selection['selected_method'],
        maximum_projected_c_relative_norm=max(r['audit']['projected_c_relative_norm_max'] for r in outputs))
    (HERE/'summary.json').write_text(json.dumps(data,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(15.5,4.5),layout='constrained')
    styles=[('fast_rx1_rf50/native','#1976d2','Native RX1'),('fast_rx1_rf50/wrong_RX','#d88917','Wrong RX training'),('fast_rx1_rf50/shift75','#9c3a9c','Training time +75 s')]
    for i,(configuration,color,label) in enumerate(styles):
        rr=percase[configuration]
        axes[0].scatter(np.arange(len(rr)),[r['gain'] for r in rr],c=color,s=19,label=label,alpha=.8)
        axes[1].boxplot([r['RMS_change_hz'] for r in rr],positions=[i],widths=.4,showfliers=False)
        axes[1].scatter(i+np.random.default_rng(i).uniform(-.12,.12,len(rr)),[r['RMS_change_hz'] for r in rr],c=color,s=19,alpha=.7)
        axes[2].scatter([r['RMS_change_hz'] for r in rr],[r['gain'] for r in rr],c=color,s=19,label=label,alpha=.8)
    axes[0].set(xlabel='Frozen DS24 scan order',ylabel='Held-vector predictive density gain',title='Native timing beats negative predictors')
    axes[1].set(xticks=range(3),xticklabels=['Native RX1','Wrong RX','Time shift'],ylabel='Candidate − baseline mean-prediction RMS (Hz)',title='Actual mean prediction improves modestly')
    axes[2].set(xlabel='Mean-prediction RMS change (Hz)',ylabel='Predictive density gain',title='Covariance can improve density with worse means')
    for ax in axes:ax.grid(alpha=.2);ax.axhline(0,c='.4',lw=.8)
    axes[0].legend(fontsize=8);axes[2].axvline(0,c='.4',lw=.8)
    fig.savefig(HERE/'receiver_witness.png',dpi=170);plt.close(fig)
    print(json.dumps(data['summary'],indent=2))

if __name__=='__main__':main()
