"""Compare orbital geometry against a response-only null and plot real data.

This is a post-result diagnostic, not a new model-selection holdout.
No location metadata or additional raw IQ is read.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / '2026_09_27_ds6_shared_phase_response'))
from study import integrate_groups


def main():
    replay = json.loads((HERE / 'replay.json').read_text())
    protocol = json.loads((HERE / 'response-protocol.json').read_text())
    banks = [{k: np.asarray(v) for k, v in b.items()}
             for b in json.loads((HERE / 'response-banks.json').read_text())]
    delay = np.linspace(-10e-6, 10e-6, 401)
    weights = np.ones(len(delay))
    weights[[0, -1]] = .5
    weights /= weights.sum()
    null = [dict(b, geometry=np.zeros_like(b['geometry'])) for b in banks]
    real = integrate_groups(banks, delay, weights)
    response_only = integrate_groups(null, delay, weights)
    result = dict(
        scope='Post-result diagnostic at frozen CFO observer; no geographic search',
        geometry=real, response_only=response_only,
        geometry_minus_response_only={arm: {
            field: real[arm][field] - response_only[arm][field]
            for field in ['held_phase_log_predictive', 'held_cfo_log_predictive']}
            for arm in ['shared_delay', 'independent_offsets']},
        groups=[])
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), layout='constrained')
    colors = ['tab:blue', 'tab:orange']
    for i, g in enumerate(protocol['observations']):
        rr = [r for r in replay['rows'] if r['group'] == g['group']]
        qualified = [r for r in rr if r['original']['both_qualified']]
        obs = g['observations']
        dwells = []
        for o in obs:
            windows = [r for r in qualified if r['visit'] == o['visit']]
            phases = np.array([r['original']['modes'][1]['evaluation']['phase_rad'] -
                               r['original']['modes'][0]['evaluation']['phase_rad']
                               for r in windows])
            coherence = float(abs(np.mean(np.exp(1j * phases))))
            dwells.append(dict(visit=o['visit'],within_dwell_R=coherence,
                               qualified_windows=len(windows)))
        counts = {arm: sum(r[arm]['both_qualified'] for r in rr)
                  for arm in ['original', 'refined']}
        result['groups'].append(dict(group=g['group'],counts=counts,dwells=dwells))
        ax = axes[0, i]
        ax.scatter([r['time_s'] for r in qualified],
                   [np.degrees(np.angle(np.exp(1j * (
                       r['original']['modes'][1]['evaluation']['phase_rad'] -
                       r['original']['modes'][0]['evaluation']['phase_rad']))))
                    for r in qualified], color='0.7', s=14, label='Qualified window')
        for train, marker, label in [(True, 'o', 'Training dwell'), (False, 'x', 'Held dwell')]:
            selected = [o for o in obs if o['train'] == train]
            ax.scatter([o['t'] for o in selected], np.degrees([o['phase'] for o in selected]),
                       marker=marker, color=colors[i], s=65, label=label)
        ax.set(title=f'Pair {i+1}: CH4 lower, wrapped phase',
               xlabel='Seconds since capture start', ylabel='Double difference (degrees)', ylim=(-190,190))
        ax.legend(fontsize=8)
        ax = axes[1, i]
        for train, marker, label in [(True,'o','Training'), (False,'x','Held')]:
            selected = [(o,d) for o,d in zip(obs,dwells) if o['train']==train]
            ax.scatter([o['t'] for o,d in selected], [d['within_dwell_R'] for o,d in selected],
                       marker=marker, color=colors[i], s=65, label=label)
        ax.set(xlabel='Seconds since capture start', ylabel='Across-window circular R',
               ylim=(0,1.05),title='Consistency within each dwell (one window gives R = 1)')
    ax = axes[2, 0]
    ax.plot(delay*1e6, real['shared_delay']['delay_posterior'], label='With candidate geometry')
    ax.plot(delay*1e6, response_only['shared_delay']['delay_posterior'], label='Response only')
    ax.set(xlabel='Shared delay (microseconds)',ylabel='Posterior mass per grid point',title='Training-only shared-delay posterior')
    ax.legend(fontsize=8)
    ax = axes[2, 1]
    names = ['Pair offsets', 'Shared delay']
    x = np.arange(2)
    for offset, label, scores in [(-.18,'With geometry',real),(.18,'Response only',response_only)]:
        ax.bar(x+offset,[scores[a]['held_phase_log_predictive'] for a in ['independent_offsets','shared_delay']],width=.36,label=label)
    ax.set(xticks=x,xticklabels=names,ylabel='Held phase log score relative to uniform',title='Eight held dwells; higher is better')
    ax.legend(fontsize=8)
    fig.suptitle('DS6 scan 4c56320f: two exact position-track pairs, 16 real dwells')
    fig.savefig(HERE/'phase-and-response.png',dpi=160)
    plt.close(fig)
    common_path=HERE/'common-rate-results.json'
    if common_path.exists():
        common=json.loads(common_path.read_text())
        models={}
        fig,axes=plt.subplots(2,2,figsize=(12,7),layout='constrained')
        for arm in ['independent','shared']:
            changed=[]
            for i,(b,g,s) in enumerate(zip(banks,protocol['observations'],common['summary'])):
                assert s['group']==g['group']
                by_visit={d['visit']:d for d in s[arm]['dwells']}
                y=np.array([by_visit[o['visit']]['phase'] for o in g['observations']])
                changed.append(dict(b,y=y))
                for train,marker in [(True,'o'),(False,'x')]:
                    selected=[o for o in g['observations'] if o['train']==train]
                    axes[0,i].scatter([o['t'] for o in selected],
                        np.degrees([by_visit[o['visit']]['phase'] for o in selected]),
                        marker=marker,color='tab:blue' if arm=='independent' else 'tab:orange',
                        label=arm+(' train' if train else ' held'))
            models[arm]=integrate_groups(changed,delay,weights)
        for i,s in enumerate(common['summary']):
            axes[0,i].set(title=f'Pair {i+1}: free source phases, rate fit compared',
                          xlabel='Seconds since capture start',ylabel='Wrapped DD (degrees)',ylim=(-190,190))
            axes[0,i].legend(fontsize=8)
            axes[1,i].bar(['Independent rates','Shared rate'],
                [s[a]['held_frame_rms_deg'] for a in ['independent','shared']],color=['tab:blue','tab:orange'])
            axes[1,i].set(ylabel='Held pilot phasor prediction RMS (degrees)',
                          title='Same unit phasors and qualified windows; lower is better')
        result['common_rate_models']=models
        fig.suptitle('Exploratory common-rate fit: training samples only, independent source intercepts')
        fig.savefig(HERE/'common-rate-comparison.png',dpi=160)
        plt.close(fig)
    (HERE/'diagnostics.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['geometry_minus_response_only'],indent=2))
    if 'common_rate_models' in result:
        print(json.dumps({k:{a:{f:v for f,v in r.items() if f!='delay_posterior'}
                                for a,r in arms.items()}
                          for k,arms in result['common_rate_models'].items()},indent=2))


if __name__ == '__main__':
    main()
