"""Temporal persistence of near-frequency/epoch alternatives, not new coverage."""
import json
from collections import defaultdict
import numpy as np
from benchmark import ROOT, digest


def split_support(times, groups, max_gap=5.):
    """Distinct-probe support only, split at observed gaps; diagnostic not detection."""
    times = np.asarray(times, float)
    groups = np.asarray(groups)
    if times.shape != groups.shape or times.ndim != 1:
        raise ValueError('Mismatched support arrays')
    unique = sorted((float(np.median(times[groups == g])), int(g)) for g in np.unique(groups))
    runs = []
    for t, g in unique:
        if not runs or t - runs[-1][-1][0] > max_gap:
            runs.append([])
        runs[-1].append((t, g))
    return [dict(start_s=r[0][0], end_s=r[-1][0], span_s=r[-1][0]-r[0][0],
                 distinct_groups=len(r), meets_support_gate=len(r)>=10 and r[-1][0]-r[0][0]>=5)
            for r in runs]


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output = ROOT / 'peak-provenance'
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    summary = {}
    for scan, ax in zip('AB', axes):
        path = output / f'{scan}-families.json'
        source = json.loads(path.read_text())
        with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as a:
            times, groups, rx, ch = a['times_s'], a['group'], a['receiver'], a['channel']
        lanes = defaultdict(list)
        for pair in source['pairs']:
            if pair['frequency_distance_hz']<=200 and pair['frame_epoch_distance_samples']<=.5:
                row=pair['row_index']
                lanes[(pair['nearest_assigned_catalog'],int(rx[row]),int(ch[row]))].append(row)
        records=[]
        for (sat, receiver, channel), rows in lanes.items():
            runs=split_support(times[rows],groups[rows])
            records.append(dict(catalog_number=sat, receiver=receiver, channel=channel,
                                rows=rows, runs=runs))
        records.sort(key=lambda x: -max((r['span_s'] for r in x['runs'] if r['meets_support_gate']),default=0))
        qualified=[r for r in records if any(s['meets_support_gate'] for s in r['runs'])]
        for y, record in enumerate(qualified):
            for run in record['runs']:
                if run['meets_support_gate']:
                    ax.plot([run['start_s'],run['end_s']],[y,y],lw=4,color='#8c564b')
        ax.set_yticks(range(len(qualified)),[f"{r['catalog_number']} / RX{r['receiver']} CH{r['channel']}" for r in qualified],fontsize=8)
        ax.invert_yaxis();ax.set_xlim(0,300);ax.grid(axis='x',alpha=.25)
        ax.set_xlabel('Receive time (s)');ax.set_title(f'Scan {scan}: {len(qualified)} persistent alternative lanes')
        summary[scan]=dict(source_sha256=digest(path),near_frequency_epoch_rows=sum(map(len,lanes.values())),
                           lanes_with_coherent_alternatives=len(qualified),lanes=records)
        print(scan,len(qualified),'persistent lanes',sum(map(len,lanes.values())),'alternative rows')
    fig.suptitle('Unassigned hypotheses repeatedly shadow assigned tracks')
    fig.text(.5,.01,'Diagnostic: within 200 Hz and 0.5 frame-epoch sample of an assigned same-probe peak.\nBars require ≥10 distinct probes, ≥5 s span, gaps ≤5 s. Not independent satellites or added coverage.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.065,1,.94));fig.savefig(output/'persistent-alternatives.png',dpi=160);plt.close(fig)
    summary['interpretation']='Thresholds describe provenance proximity, not an additional acceptance gate. Repeated near-frequency/epoch alternatives support investigating detector ambiguity, but do not prove a shared physical source. No frozen protocol, assignments, or denominator changed.'
    with (output/'persistent-alternatives.json').open('x') as stream:
        json.dump(summary,stream,indent=2,allow_nan=False)


if __name__=='__main__':main()
