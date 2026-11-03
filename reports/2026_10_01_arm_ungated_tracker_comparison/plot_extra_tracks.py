"""Measured CFO plots for plausible extras and strict long-reference misses."""
import json
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
BASE = REPORTS/'2026_09_30_arm_fast_tracks/server-baseline/output'
NEW = REPORTS/'2026_10_01_arm_ungated_full_scan/analysis'
sys.path.insert(0, str(REPORTS/'2026_09_30_arm_curvature_tracks/evaluation'))
import compare_membership as m


def save(fig, name):
    fig.savefig(HERE/f'{name}.png', dpi=155)
    fig.savefig(HERE/f'{name}.pdf')
    plt.close(fig)


def main():
    obs = m.read_observations(NEW/'observations.tsv')
    sources = m.read_sources(NEW/'candidate-map.tsv', obs)
    so = m.read_observations(BASE/'server-observations.tsv')
    ss = m.read_sources(BASE/'server-candidate-map.tsv', so)
    tracks = {t.index:t for t in m.read_tracks(HERE/'coarse-seeded/tracks-0.tsv', obs).values}
    refs = {t.index:t for t in m.read_tracks(BASE/'server-tracks.tsv', so).values}
    origin = min(o.start_ns for o in so.values())
    rows = json.loads((HERE/'coarse-seeded/additional-tracks.json').read_text())
    rows = sorted((r for r in rows if r['continuity_screen_pass']), key=lambda r:r['span_s'])
    assert len(rows) == 33
    durations = np.array([r['span_s'] for r in rows])
    bins = np.arange(0, np.ceil(max(durations)/5)*5+5, 5)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout='constrained')
    counts, edges, bars = axes[0].hist(durations, bins=bins, color='#25827d', edgecolor='white')
    for n, bar in zip(counts, bars):
        if n: axes[0].text(bar.get_x()+bar.get_width()/2, n+.1, str(int(n)), ha='center')
    axes[0].set(xlabel='First-to-last measured point (seconds)', ylabel='Number of outputs',
                title=f'5-second duration bins · median {np.median(durations):.1f} s')
    axes[0].set_ylim(0, max(counts)+1)
    axes[1].bar(range(len(rows)), durations, color='#25827d')
    axes[1].set(xticks=range(len(rows)), xticklabels=[str(r['output_index']) for r in rows],
                xlabel='ARM output ID, ordered by duration', ylabel='Duration (seconds)',
                title='All 33 individually')
    axes[1].tick_params(axis='x', labelrotation=90, labelsize=8)
    for ax in axes: ax.grid(axis='y', alpha=.18)
    fig.suptitle('Coarse-seeded: 33 additional outputs passing the continuity screen\n'
                 'Output hypotheses, not confirmed distinct satellite tracks', fontsize=13)
    save(fig, 'extra-duration-distribution')

    selected = [rows[i] for i in np.rint(np.linspace(0, len(rows)-1, 6)).astype(int)]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), layout='constrained')
    for ax, row in zip(axes.flat, selected):
        tr = tracks[row['output_index']]
        points = sorted(tr.points, key=lambda p:obs[p.candidate].center_ns)
        t = [(obs[p.candidate].center_ns-origin)/1e9 for p in points]
        f = [p.dealiased_cfo_hz/1000 for p in points]
        ax.scatter(t, f, s=17, color='#147d76')
        ax.set(title=f'ARM #{tr.index} · {row["span_s"]:.1f} s · {len(points)} points\n'
               f'RX{tr.lane.receiver}, channel {tr.lane.channel}, {tr.lane.edge} · '
               f'{row["reference_support_fraction"]:.0%} server-track support',
               xlabel='Seconds from first projected observation', ylabel='Dealiased CFO (kHz)')
        ax.grid(alpha=.2)
    fig.suptitle('Six extras selected evenly across the sorted duration range\n'
                 'Measured CFO points with tracker alias choices; no fitted curves. Independent axis scales.', fontsize=13)
    save(fig, 'extra-track-examples')

    summary = next(r for r in json.loads((HERE/'science-summary.json').read_text()) if r['method']=='coarse-seeded')
    missing = [i for i in summary['missing'] if (refs[i].end_ns-refs[i].start_ns)/1e9 >= 30]
    assert sorted(missing) == [8, 30, 47]
    best = json.loads((HERE/'coarse-seeded/best-per-reference.json').read_text())
    fig, axes = plt.subplots(len(missing), 2, figsize=(14, 11), layout='constrained')
    for axisrow, index in zip(axes, missing):
        ref = refs[index]
        met = best[str(index)]
        tr = tracks[met['output_index']]
        consistent = set(met['consistent_sources'])
        def supported(p, source_map):
            return ':'.join(map(str, source_map[p.candidate])) in consistent
        refpoints = sorted(ref.points, key=lambda p:so[p.candidate].center_ns)
        t = np.array([(so[p.candidate].center_ns-origin)/1e9 for p in refpoints])
        f = np.array([p.dealiased_cfo_hz for p in refpoints])
        supported_ref = np.array([supported(p, ss) for p in refpoints])
        left, right = axisrow
        left.scatter(t[supported_ref], f[supported_ref]/1000, s=22, color='#326baf', label='Server point recovered')
        left.scatter(t[~supported_ref], f[~supported_ref]/1000, s=35, color='#b93640', marker='x', label='Server point not recovered')
        pp = sorted((p for p in tr.points if ref.start_ns <= obs[p.candidate].center_ns <= ref.end_ns),
                    key=lambda p:obs[p.candidate].center_ns)
        tt = np.array([(obs[p.candidate].center_ns-origin)/1e9 for p in pp])
        ff = np.array([p.dealiased_cfo_hz for p in pp])
        spacing = 11.2e9/ref.lane.rf_hz/4.4e-6
        ff += np.round((np.interp(tt,t,f)-ff)/spacing)*spacing
        yes = np.array([supported(p, sources) for p in pp])
        right.scatter(tt[yes], ff[yes]/1000, s=22, color='#147d76', label='ARM point matching reference')
        right.scatter(tt[~yes], ff[~yes]/1000, s=25, color='#d57b24', marker='x', label='Additional ARM point')
        left.set_title(f'Server ref #{index} · {(ref.end_ns-ref.start_ns)/1e9:.1f} s\n'
                       f'{met["consistent_source_count"]}/{met["reference_source_count"]} sources recovered')
        right.set_title(f'ARM output #{tr.index}, within reference time span\n'
                        f'Coverage {met["reference_source_coverage"]:.1%} · source purity {met["in_span_output_purity"]:.1%}')
        both = np.r_[f,ff]/1000
        pad = max(float(np.ptp(both))*.08, .15)
        for ax in axisrow:
            ax.set(xlim=(min(t)-1,max(t)+1), ylim=(min(both)-pad,max(both)+pad),
                   xlabel='Seconds from first projected observation', ylabel='Alias-aligned CFO (kHz)')
            ax.grid(alpha=.2)
            ax.legend(fontsize=8)
    fig.suptitle('Three long server references failing strict coarse-seeded matching\n'
                 'All exceed 80% coverage; all fail 80% source purity. Orange does not mean noise.', fontsize=13)
    save(fig, 'missed-long-tracks')
    result = dict(count=len(rows), min_s=float(min(durations)), median_s=float(np.median(durations)),
        max_s=float(max(durations)), short_under_15=int(sum(durations<15)),
        medium_15_to_30=int(sum((durations>=15)&(durations<30))), long_at_least_30=int(sum(durations>=30)),
        histogram_edges_s=edges.tolist(), histogram_counts=counts.astype(int).tolist(),
        example_output_ids=[r['output_index'] for r in selected], missed_long_reference_ids=missing)
    (HERE/'plot-summary.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
