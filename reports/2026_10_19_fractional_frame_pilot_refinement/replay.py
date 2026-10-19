"""Rebuild all tables and figures from the packaged numeric RF evidence."""

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent


def main():
    data=json.loads((HERE/'evidence.json').read_text());rows=data['rows'];summary=[]
    assert len(rows)==len({r['observation_id'] for r in rows})==126
    for case in ['DS23-0202','DS23-0274','DS23-0007','DS23-0257','DS23-0217']:
        rr=[r for r in rows if r['case']==case]
        gain=np.array([r['fractional']['score']/r['legacy']['score'] for r in rr])
        shift=np.array([r['fractional']['CFO_hz']-r['legacy']['CFO_hz'] for r in rr])
        assert max(abs(r['legacy_replay_difference']) for r in rr)<1e-10
        summary.append(dict(case=case,probes=len(rr),sample_rate_hz=rr[0]['sample_rate_hz'],
            improved=int((gain>1).sum()),median_RF_gain_percent=float(100*(np.median(gain)-1)),
            minimum_RF_gain_percent=float(100*(min(gain)-1)),
            median_absolute_CFO_change_hz=float(np.median(abs(shift))),
            maximum_absolute_CFO_change_hz=float(max(abs(shift)))))
    ablation=data['padding_ablation']
    output=dict(cases=summary,total_probes=126,improved_probes=sum(r['improved'] for r in summary),
        median_padding_only_gain_percent=float(100*(np.median([r['padding_only_score_ratio'] for r in ablation])-1)),
        median_fractional_over_isolated_rounded_gain_percent=float(100*(np.median([r['fractional_over_isolated_rounded_score_ratio'] for r in ablation])-1)),
        no_localization_gain_or_ALGO03_qualification_claim=True,
        evidence_sha256=hashlib.sha256((HERE/'evidence.json').read_bytes()).hexdigest())
    (HERE/'summary.json').write_text(json.dumps(output,indent=2)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),constrained_layout=True)
    for case,color in zip([r['case'] for r in summary],plt.cm.tab10.colors):
        rr=[r for r in rows if r['case']==case]
        gains=np.sort([100*(r['fractional']['score']/r['legacy']['score']-1) for r in rr])
        axes[0].plot(gains,np.arange(1,len(gains)+1)/len(gains),label=case,color=color)
        axes[1].scatter([case[-4:]]*len(rr),[r['fractional']['CFO_hz']-r['legacy']['CFO_hz'] for r in rr],
            s=14,alpha=.6,color=color)
    axes[0].axvline(0,color='k',lw=.7);axes[0].set(xlabel='Relative explained-pilot-energy gain (%)',ylabel='Probe fraction')
    axes[0].legend(fontsize=8);axes[0].grid(alpha=.2)
    axes[1].axhline(0,color='k',lw=.7);axes[1].set(xlabel='DS23 scan',ylabel='CFO change (Hz)');axes[1].grid(alpha=.2)
    fig.suptitle('Fractional frame placement: positive RF fit result, small carrier changes\n126 unique probes; five scans; same three fit parameters')
    fig.savefig(HERE/'rf_fit_and_carrier.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4),constrained_layout=True)
    for key,label in [('padding_only_score_ratio','Isolated template, rounded starts'),
                      ('fractional_over_isolated_rounded_score_ratio','Fractional starts versus isolated rounded')]:
        values=np.sort([100*(r[key]-1) for r in ablation])
        ax.plot(values,np.arange(1,len(values)+1)/len(values),label=label)
    ax.axvline(0,color='k',lw=.7);ax.set(xlabel='RF fit gain (%)',ylabel='Probe fraction',
        title='96-probe ablation isolates the fractional-frame timing effect');ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.savefig(HERE/'padding_ablation.png',dpi=160);plt.close(fig)
    print(json.dumps(output,indent=2))


if __name__=='__main__':main()
