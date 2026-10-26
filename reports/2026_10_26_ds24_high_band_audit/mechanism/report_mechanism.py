"""Evaluate sealed diagnostic endpoints, then render their separate outcomes."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
TRUTH = np.array([37.849061591561885, -122.48574968092912])
HALF = Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')


def error(point):
    a, b = np.radians([point, TRUTH]); d = b-a
    h = np.sin(d[0]/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin(d[1]/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(h, 0, 1))))


def read(path):
    return json.loads(path.read_text())


def main():
    originals = list(csv.DictReader((HALF/'tables/positions.csv').open()))
    rows = []
    for case in ('DS24-0015', 'DS24-0019'):
        parent = read(HALF/'ch5_8/family_cavity/position'/f'{case}.json')['policy_arms']
        for arm in ('c0', 'fitted_c'):
            for group in ('ch1_4', 'ch5_8', 'all_channels'):
                old = next(r for r in originals if r['case']==case and r['group']==group
                           and r['method']=='baseline' and r['arm']==arm)
                rows.append(dict(case=case, arm=arm, variant=group,
                                 error_km=float(old['error_km']), RMS_hz=float(old['curved_RMS_hz']),
                                 failed_curved=0, failed_predictive=0, removed_points=0))
        for f in sorted(HERE.glob(f'ablate_{case}_*.json')):
            d = read(f)
            for arm, s in d['arms'].items():
                rows.append(dict(case=case, arm=arm, variant=f"without_{d['removed_norad']}",
                                 error_km=error(s['endpoint_latlon']), RMS_hz=s['RMS_hz'],
                                 failed_curved=sum(not t['compatible'] for t in s['gates']['tracks']),
                                 failed_predictive=sum(not t['compatible'] for t in s['linear_gates']),
                                 removed_points=d['removed_curved_points']+d['removed_predictive_points']))
    restarts = []
    for f in sorted(HERE.glob('restart_DS24*.json')):
        d = read(f)
        for arm, r in d['arms'].items():
            restarts.append(dict(case=d['case'], arm=arm, start=d['start_group'],
                                 displacement_m=r['displacement_from_parent_m'],
                                 objective_change=r['objective_difference_from_parent'],
                                 error_km=error(r['endpoint_latlon']),
                                 failed_curved=sum(not t['compatible'] for t in r['gates']['tracks']),
                                 failed_predictive=sum(not t['compatible'] for t in r['linear_gates'])))
    result = dict(rows=rows, restarts=restarts, evaluation_position_only=TRUTH.tolist(),
                  deletion_scores_not_compared_across_masks=True,
                  deletions_are_influence_diagnostics_not_a_new_policy=True)
    (HERE/'evaluation.json').write_text(json.dumps(result, indent=2)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    for ax, case in zip(axes, ('DS24-0015', 'DS24-0019'), strict=True):
        part = [r for r in rows if r['case']==case]
        variants = list(dict.fromkeys(r['variant'] for r in part))
        labels = {'ch1_4':'CH1–4', 'ch5_8':'CH5–8', 'all_channels':'CH1–8'}
        for offset, arm, color in [(-.19, 'c0', '#477ca8'), (.19, 'fitted_c', '#de8731')]:
            chosen = [next(r for r in part if r['variant']==v and r['arm']==arm) for v in variants]
            bars = ax.bar(np.arange(len(variants))+offset, [r['error_km'] for r in chosen],
                          width=.37, label='c = 0' if arm=='c0' else 'Fitted c', color=color)
            for bar, r in zip(bars, chosen, strict=True):
                fail=r['failed_curved']+r['failed_predictive']
                if fail: bar.set_hatch('///')
                ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+.07,
                        f"{r['error_km']:.2f}"+(' ×' if fail else ''), ha='center', fontsize=9)
        ax.set(xticks=range(len(variants)), xticklabels=[labels.get(v, 'Remove\n'+v.split('_')[1]) for v in variants],
               ylabel='Position error (km)', title=case, ylim=(0, max(r['error_km'] for r in part)+.8))
        ax.axhline(.5, color='gray', ls=':', label='500 m goal')
        ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True); ax.legend(fontsize=8)
    fig.suptitle('Different influence patterns in the two largest band deficits\nFamily deletions diagnose influence; × means a retained curve fails a gate', fontsize=12)
    for suffix in ('png', 'pdf'): fig.savefig(HERE/f'family_influence.{suffix}', dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(14, 4.5), constrained_layout=True)
    fig.get_layout_engine().set(wspace=.15)
    choices = [('current', 'All nuisance terms uncertain'), ('receiver_offsets','Offsets known'),
               ('receiver_all','Receiver terms known'), ('phase','Satellite phases known')]
    for ax, case in zip(axes, ('DS24-0015', 'DS24-0019'), strict=True):
        r = read(HERE/f'ch5_8_{case}.json')['arms']['fitted_c']['curved']
        vals = [r['all']['principal_sigma_km'][0] if k=='current' else r['freeze_controls'][k]['principal_sigma_km'][0] for k, _ in choices]
        bars = ax.barh(np.arange(len(choices)), vals, color=['#de8731','#888888','#888888','#477ca8'])
        ax.set(yticks=range(len(choices)), yticklabels=[label for _,label in choices], xlabel='Conditional weak-direction scale (km)', title=case, xlim=(0, 1.3))
        ax.invert_yaxis()
        for bar,value in zip(bars,vals,strict=True): ax.text(value+.02,bar.get_y()+bar.get_height()/2,f'{value:.3f}',va='center')
    fig.suptitle('Local information diagnostic at each CH5–8 endpoint\nKnown-parameter controls are unavailable-information oracles, not achieved error',fontsize=12)
    for suffix in ('png','pdf'): fig.savefig(HERE/f'nuisance_information.{suffix}',dpi=170)
    plt.close(fig)
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
