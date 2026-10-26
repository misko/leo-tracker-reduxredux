"""Offline figures and descriptive summaries; no selection or predictor changes."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import study

HERE=Path(__file__).resolve().parent


def save(fig,name):
    for ext in ['png','pdf']:fig.savefig(HERE/f'{name}.{ext}',dpi=180,bbox_inches='tight')
    plt.close(fig)


def main():
    s=study.read(HERE/'summary.json');d=study.read(HERE/'timing_diagnosis.json')
    fig,ax=plt.subplots(figsize=(10,4.6),layout='constrained');x=np.arange(6)
    for i,(key,label)in enumerate([('latest_visit_gatepassing','Latest visit donor'),('forecast_available','Sparse forecast'),
                                  ('target_original_gatepass','Original target gatepass'),('top1_joint_T16_F500','Primary compatible ±16 samples /500Hz')]):
        ax.bar(x+(i-1.5)*.2,[s['by_channel'][str(ch)][key]for ch in study.CHANNELS],width=.19,label=label)
    ax.set(xticks=x,xticklabels=[f'CH{ch}'for ch in study.CHANNELS],ylim=(0,102),ylabel='Receiver cells /96 per channel',
           title='Frozen development panel: sparse histories bridge missed visits')
    ax.legend(fontsize=8);save(fig,'opportunity')
    fig,ax=plt.subplots(figsize=(8.5,4.5),layout='constrained')
    for order in [1,2,4,8]:
        ax.plot([2,16,64,256],[s['overall'][f'top{order}_joint_T{tw}_F500']for tw in [2,16,64,256]],'o-',label=f'First {order} retained modes')
    ax.set(xscale='log',xticks=[2,16,64,256],xticklabels=['2','16','64','256'],ylim=(0,170),
           xlabel='Archived timing compatibility half width (native samples)',ylabel='Joint timing/CFO-compatible cells /576',
           title='Archived target compatibility at ±500Hz; best-case matching only')
    ax.axhline(165,color='.5',ls='--',label='165 original target gatepassing cells');ax.legend(fontsize=8)
    save(fig,'timing_compatibility')
    fig,axes=plt.subplots(1,2,figsize=(11,4.6),layout='constrained')
    rows=d['rows']
    for field,label in [('fitted_error_samples','Fitted timing'),('carry_error_samples','Latest-donor zero-rate carry')]:
        values=np.sort(abs(np.array([r[field]for r in rows])))
        axes[0].plot(np.maximum(values,.01),np.arange(1,len(values)+1)/len(values),label=label)
    axes[0].set(xscale='log',xlabel='Absolute signed-timing-error magnitude (samples)',ylabel='Fraction of 144 CFO-compatible primary cells',ylim=(0,1.02))
    axes[0].axvline(2,c='.5',ls='--');axes[0].axvline(16,c='.5',ls=':');axes[0].legend(fontsize=8)
    groups=[(0,.5),(.5,1),(1,2),(2,4.51)]
    for i,(lo,hi)in enumerate(groups):
        values=np.array([r['fitted_error_samples']for r in rows if lo<=r['elapsed_s']<hi])
        if len(values):
            q=np.quantile(values,[.25,.5,.75]);axes[1].errorbar(i,q[1],yerr=np.array([[q[1]-q[0]],[q[2]-q[1]]]),fmt='o',capsize=5)
            axes[1].text(i,q[2]+1,f'n={len(values)}',ha='center',fontsize=8)
    axes[1].axhline(0,c='.5',ls='--');axes[1].set(xticks=range(4),xticklabels=['<0.5','0.5–1','1–2','2–4.5'],
        xlabel='Latest donor gap (seconds)',ylabel='Signed fitted timing error: target−prediction (samples)',ylim=(-30,5))
    fig.suptitle('Fixed CFO-only target match: fitted timing improves carry but retains negative bias')
    save(fig,'signed_timing_diagnosis')
    modes=study.read(HERE/'mode_evaluation.json')['rows']
    widths=np.array([m['timing_half_width_samples']for m in modes if m['mode_order']==1])
    cfo=np.array([m['CFO_half_width_hz']for m in modes if m['mode_order']==1])
    study.write(HERE/'report_stats.json',dict(primary_timing_half_width_quantiles=dict(zip(['p05','median','p95'],[float(v)for v in np.quantile(widths,[.05,.5,.95])])),
        primary_CFO_half_width_quantiles=dict(zip(['p05','median','p95'],[float(v)for v in np.quantile(cfo,[.05,.5,.95])])),
        signed_error_cohort=144,signed_bias_diagnostic_posthoc=True,external_identity_truth=False))


if __name__=='__main__':main()
