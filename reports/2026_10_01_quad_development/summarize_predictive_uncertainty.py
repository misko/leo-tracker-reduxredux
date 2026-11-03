"""Same-density comparisons and explicit missing-control coverage."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_window import prepare_window
from predictive_uncertainty import ARMS
from screen_seed_prefix import sealed,digest
from regression_batch import verify_sources
from check_receiver_curvature import save
HERE=Path(__file__).resolve().parent


def summarize(rows,arm):
    valid=[r for r in rows if all(r['arms'][arm]['scores'][k] is not None for k in ('policy','single','robust'))]
    count=sum(r['held_points'] for r in valid)
    gains={key:sum(r['arms'][arm]['scores']['policy']-r['arms'][arm]['scores'][key] for r in valid)/count if count else None for key in ('single','robust')}
    scan_gains={unit:sum(r['arms'][arm]['scores']['policy']-r['arms'][arm]['scores']['robust'] for r in valid if r['unit']==unit)/sum(r['held_points'] for r in valid if r['unit']==unit) for unit in sorted({r['unit'] for r in valid})}
    return dict(folds=len(rows),valid_folds=len(valid),planned_held_points=sum(r['held_points'] for r in rows),valid_held_points=count,
                policy_vs_single=gains['single'],policy_vs_robust=gains['robust'],per_scan_gain=scan_gains,
                improving_scans=sum(v>0 for v in scan_gains.values()),missing_folds=len(rows)-len(valid),
                gate=len(valid)==len(rows) and gains['robust'] is not None and gains['robust']>0 and sum(v>0 for v in scan_gains.values())>=3)


def main():
    path=HERE/'predictive-uncertainty-v1.json';data=sealed(path);verify_sources(data['sources']);verify_sources(data['inputs']);records=[]
    for ds in ('DS9','DS10','DS11'):
        for sigma in (100.,300.):
            for split in ('alternating','forward'):
                group=[r for r in data['rows'] if r['unit'].split('-')[0]==ds and r['sigma_hz']==sigma and r['split']==split]
                for arm in ARMS:records.append(dict(dataset=ds,sigma_hz=sigma,split=split,arm=arm,**summarize(group,arm)))
    fig,axes=plt.subplots(1,2,figsize=(12,4))
    shown=ARMS[2:]
    for ax,split in zip(axes,('alternating','forward')):
        for i,ds in enumerate(('DS9','DS10','DS11')):
            vals=[next(r['policy_vs_robust'] for r in records if r['dataset']==ds and r['sigma_hz']==100 and r['split']==split and r['arm']==arm) for arm in shown]
            ax.bar(np.arange(len(shown))+(i-1)*.25,vals,width=.25,label=ds)
        ax.set_xticks(np.arange(len(shown)),['t4 matched\nfixed','t4 matched\nleverage','t4 same-scale\nfixed','t4 same-scale\nleverage'])
        ax.axhline(0,color='black',linewidth=.8);ax.set_title(split);ax.set_ylabel('Policy minus same-shape robust mean\n(nats per held observation)');ax.grid(axis='y',alpha=.2);ax.legend()
    fig.suptitle('Frozen-mean tail/uncertainty controls, sigma 100 Hz; missing controls excluded and counted')
    fig.tight_layout();fig.savefig(HERE/'predictive-uncertainty-summary-v1.png',dpi=160);plt.close(fig)
    save(HERE/'predictive-uncertainty-summary-v1.json',dict(rows=records,inputs={str(path):digest(path)},sources={str(Path(__file__).resolve()):digest(__file__)},
        qualification='Reused development predictive controls; no calibrated posterior, localization integration, or geography.'))
    print('summary rows',len(records),'fixed score parity',data['maximum_fixed_gaussian_score_difference'])


if __name__=='__main__':main()
