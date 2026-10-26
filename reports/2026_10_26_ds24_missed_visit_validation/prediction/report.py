"""Offline descriptive plots; no IQ scoring or predictor modification."""
from collections import Counter
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import study

HERE=Path(__file__).resolve().parent


def main():
    rows=study.read(HERE/'predictions.json')['rows'];d=study.read(HERE/'archived_diagnostic.json')
    reasons=Counter(reason for r in rows if r.get('model')for reason in r['model']['fallback_reasons'])
    shifts=[r['legacy_adapter_minus_consistent_linear_epoch_samples']for r in rows if r['methods']]
    study.write(HERE/'report_summary.json',dict(forecast_statuses=dict(Counter(r['status']for r in rows)),
        fallback_reasons=dict(reasons),legacy_adapter_minus_consistent_linear_samples=dict(
            minimum=float(min(shifts)),median=float(np.median(shifts)),maximum=float(max(shifts))),
        archived_diagnostic=d['overall'],source_timing_reference_nominal_not_measured=True,
        raw_measurement_recovery_established=False,position_improvement_established=False))
    fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout='constrained')
    for method,label in [('linear','Consistent constant-epoch linear'),('quadratic_or_fallback','Quadratic / unchanged fallback'),
                         ('legacy_adapter_linear','Round1 legacy adapter linear')]:
        values=np.sort(abs(np.array([r['errors_samples'][method]for r in d['rows']])))
        axes[0].plot(np.maximum(values,.001),np.arange(1,len(values)+1)/len(values),label=label)
    axes[0].set(xscale='log',xlabel='Absolute archived timing error (native samples)',
        ylabel='Fraction of 144 fixed CFO-compatible primary cells',ylim=(0,1.01))
    axes[0].axvline(2,color='.5',ls='--');axes[0].legend(fontsize=8)
    support_counts={key:Counter(len(r['donors'])for r in rows if r['status']==key)for key in ['quadratic','linear_fallback']}
    for i,(status,label)in enumerate([('quadratic','Quadratic used'),('linear_fallback','Linear fallback')]):
        axes[1].bar(np.arange(1,13)+(i-.5)*.35,[support_counts[status][n]for n in range(1,13)],width=.34,label=label)
    axes[1].set(xticks=range(1,13),xlabel='Original primary history donor count',ylabel='Development receiver cells',
        title='123 no-donor cells also retained')
    axes[1].legend(fontsize=8)
    fig.suptitle('Sealed primary quadratic corrects central archived timing; RF recovery is a separate test')
    for ext in ['png','pdf']:fig.savefig(HERE/f'primary_timing_diagnostic.{ext}',dpi=180,bbox_inches='tight')


if __name__=='__main__':main()
