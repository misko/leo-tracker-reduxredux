"""Read-only report generator for the bounded original-winner/peak-mixture pilot."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parents[1]
DATA=REPORTS/'2026_10_16_dsx01_fast_association_losses'
ARMS=['fitted-c','zero-c']
METHODS=['winner-continuation','mixture-continuation']


def digest(path):return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    records=[json.loads(p.read_text()) for p in sorted((HERE/'results').glob('*.json'))]
    if not records:raise ValueError('No pilot results')
    lookup={(r['source_id'],r['arm'],r['method']):r for r in records}
    sources=sorted(set(r['source_id'] for r in records))
    assert all((s,a,m) in lookup for s in sources for a in ARMS for m in METHODS),'Incomplete matched pilot'
    with (DATA/'regions.csv').open() as stream:regions=list(csv.DictReader(stream))
    with (DATA/'membership.csv').open() as stream:members=list(csv.DictReader(stream))
    context=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    full_count=sum(r['group_count'] for r in records if r['arm']=='fitted-c' and r['method']==METHODS[0])
    challenge_count=sum(int(r['observation_count']) for r in regions if r['source_id'] in sources)
    table=[];windows=[]
    for r in records:
        sid,arm,method=r['source_id'],r['arm'],r['method']
        rows=[p for p in context if p['source_id']==sid]
        npz=np.load(HERE/'results'/f'{sid}-{arm}-{method}.npz')
        np.testing.assert_allclose(npz['times_s'],[p['time_s'] for p in rows],atol=1e-9,rtol=0)
        assert len(rows)==r['group_count']==len(npz['associated'])
        assert int(npz['associated'].sum())==r['winner_full_scan']['associated']
        assert int(npz['group_associated'].sum())==r['mixture_group']['associated']
        assert int(npz['permutation_group_associated'].sum())==r['mixture_group']['within_lane_time_permutation']['associated']
        index={p['observation_id']:i for i,p in enumerate(rows)}
        for w in r['windows']:
            ids=[m['observation_id'] for m in members if m['region_id']==w['region_id']]
            assert len(ids)==w['observations']
            assert int(npz['associated'][[index[key] for key in ids]].sum())==w['associated']
            windows.append(dict(source_id=sid,arm=arm,method=method,**w))
        d=r['diagnostics'];assert d['evaluations']<=1000
        # A single noninterruptible objective evaluation can finish just after the deadline.
        assert d['elapsed_seconds']<121
        assert r['budget']==dict(full_objectives=1000,wall_seconds=120,extra_orbit_projection_calls=0)
        assert r['calibration_transport']['seed']['maximum_correction_error_hz']<=1e-6
        assert r['calibration_transport']['endpoint']['maximum_correction_error_hz']<=1e-6
        f=r['winner_full_scan'];s=r['winner_vs_seed'];g=r['mixture_group']
        table.append(dict(source_id=sid,arm=arm,method=method,observations=r['group_count'],
            winner_associated=f['associated'],challenge=r['winner_challenge']['associated'],
            challenge_observations=r['winner_challenge']['observations'],
            new_vs_original=f['new_associations'],lost_vs_original=f['lost_associations'],
            retained_vs_original=f['retained_associations'],
            intersection_original_rms_hz=f['intersection_original_rms_hz'],
            intersection_variant_rms_hz=f['intersection_variant_rms_hz'],
            new_vs_seed=s['new_associations'],lost_vs_seed=s['lost_associations'],
            winner_rms_hz=f['associated_rms_hz'],winner_nll=f['likelihood_nll'],
            configured_reference_km=f.get('configured_reference_distance_km'),
            common_timing_s=f['common_timing_s'],relative_timing_rms_s=f['relative_timing_rms_s'],
            group_associated=g['associated'],permuted_group_associated=g['within_lane_time_permutation']['associated'],
            group_nll=g['likelihood_nll'],optimized_objective=d['objective'],
            objective_evaluations=d['evaluations'],elapsed_seconds=d['elapsed_seconds'],
            strict_accepted=r['audit']['accepted'],stationarity=r['audit'].get('stationarity')))
    paired={}
    for arm in ARMS:
        paired[arm]={}
        for method in METHODS:
            selected=[t for t in table if t['arm']==arm and t['method']==method]
            ww=[w for w in windows if w['arm']==arm and w['method']==method]
            region={r['region_id']:r for r in regions}
            paired[arm][method]=dict(winner_associated=sum(t['winner_associated'] for t in selected),
                challenge_associated=sum(t['challenge'] for t in selected),
                group_associated=sum(t['group_associated'] for t in selected),
                permutation_group_associated=sum(t['permuted_group_associated'] for t in selected),
                original_new=sum(t['new_vs_original'] for t in selected),
                original_lost=sum(t['lost_vs_original'] for t in selected),
                major_windows_net_original_missing_restored=sum(
                    (w['associated']-int(region[w['region_id']]['original_associated_count']))>=
                    .8*int(region[w['region_id']]['original_unassociated_count']) for w in ww))
    summary=dict(protocol='Full-data warm pilot; matched complete endpoint seeds and 1000/120 continuations.',
        sources=sources,tested_winner_observations=full_count,tested_challenge_observations=challenge_count,
        frozen_full_denominator=20084,frozen_challenge_denominator=693,frozen_windows=15,
        results=table,windows=windows,paired_totals=paired,
        qualification='Only original winner assignments are recovery metrics. Normalized group posterior and rotation-null counts are separate. '
        'Original winner NLL and peak-set NLL are different objectives and must not be subtracted from each other. '
        'A fixed-endpoint permutation is not a fitted or calibrated statistical null. Configured position is a reference with uncertainty, not identity truth.')
    (HERE/'pilot-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    fields=['region_id','source_id','observations','original_associated']+[f'{a}_{m}' for a in ARMS for m in METHODS]
    with (HERE/'window-comparison.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for region in regions:
            row=dict(region_id=region['region_id'],source_id=region['source_id'],
                observations=region['observation_count'],original_associated=region['original_associated_count'])
            for arm in ARMS:
                for method in METHODS:
                    w=next((w for w in windows if w['region_id']==region['region_id'] and w['arm']==arm and w['method']==method),None)
                    row[f'{arm}_{method}']='' if w is None else w['associated']
            writer.writerow(row)
    before=paired['fitted-c'][METHODS[0]];after=paired['fitted-c'][METHODS[1]]
    lines=['# Normalized latent-peak pilot','',
        f"The fitted-c mixture changes requested coverage {before['challenge_associated']}→{after['challenge_associated']}/{challenge_count}, "
        f"while full original-winner coverage changes {before['winner_associated']}→{after['winner_associated']}/{full_count}. "
        f"Major windows (at least 80% net restoration of originally missing support) remain {before['major_windows_net_original_missing_restored']}→{after['major_windows_net_original_missing_restored']} "
        f"among {sum(r['source_id'] in sources for r in regions)} tested windows. "
        f"Normalized group rotation-control associations change {before['permutation_group_associated']}→{after['permutation_group_associated']}. "
        'This pilot does not justify expanding the uniform-peak model to all sources.','',
        'One likelihood contribution per probe group: `-log(mean(exp(-row_nll)))`, with uniform weight over all passed GLRT peaks. '
        'The original row density already contains clutter. Posterior peak probabilities weight both frequency and visibility/q normalizer gradients; physical priors appear once. '
        'Singleton groups exactly reproduce the original 125 Hz objective and every gradient. Actual support times and RF values are retained.','',
        f'Tested {len(sources)}/5 sources: {", ".join(sources)}; {full_count}/20,084 original winners and {challenge_count}/693 challenge observations. '
        'The CSV retains all 15 fixed window denominators; blank cells are untested. Nine synthetic tests pass. No production code or frozen report changed.','',
        'Every arm starts at the same sealed fixed-bank fitted-c profile endpoint. The c=0 arm changes only c before fitting. '
        'Both the original-winner continuation and peak-mixture continuation receive the same additional allowance of at most 1,000 complete objective calls and 120 seconds, with no proposal orbit projections. '
        'The reused upstream profile endpoint already had its separate 1,000-call/120-second allowance; it is shared by the paired continuations. '
        'Original band offsets, clock nodes, q budget, priors, candidate order and all existing bounds are preserved. '
        'Public frozen sequential calibration verifies analytic time/RF-center transport within 1e-6 Hz, without changing clock, q or timing coordinates.','',
        '| Source | c arm | Optimized density | Winner full | Challenge | New/lost vs original | New/lost vs seed | Reference km | Strict KKT | Calls |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for t in table:
        lines.append(f"| {t['source_id']} | {t['arm']} | {t['method'].split('-')[0]} | {t['winner_associated']}/{t['observations']} | {t['challenge']}/{t['challenge_observations']} | +{t['new_vs_original']}/−{t['lost_vs_original']} | +{t['new_vs_seed']}/−{t['lost_vs_seed']} | {t['configured_reference_km']:.3f} | {t['stationarity']:.3g}{'' if t['strict_accepted'] else ' FAIL'} | {t['objective_evaluations']} |")
    lines+=['','The configured station is an uncertain external reference used only for measurement. In-sample likelihood gain does not establish improved localization. '
        'All original support losses remain visible in the JSON; the paired-seed columns measure the incremental change from the shared profile endpoint.','',
        '| Source | c arm | Optimized density | Winner RMS Hz | Winner NLL | Peak-set NLL | Group posterior associations | Rotation control |',
        '|---|---|---|---:|---:|---:|---:|---:|']
    for t in table:
        lines.append(f"| {t['source_id']} | {t['arm']} | {t['method'].split('-')[0]} | {t['winner_rms_hz']:.2f} | {t['winner_nll']:.2f} | {t['group_nll']:.2f} | {t['group_associated']} | {t['permuted_group_associated']} |")
    lines+=['','Winner NLL is always evaluated on the original fixed observations; peak-set NLL always uses the same all-peak groups. '
        'Values across these two columns are different observation likelihoods and are not comparable. Group counts use maximum satellite posterior **after summing over latent peaks**, compared with group clutter. '
        'No maximum-over-peaks count is credited as recovery. The fixed within-RX/channel half rotation preserves each lane’s CFO distribution while breaking its time links. '
        'It is one diagnostic negative control, not a calibrated significance test or a null-refitted comparison.','',
        'A possible next model would learn peak reliability from independent training evidence instead of assigning equal weight to every passed alternative. '
        'That would require a separate training-only calibration and new null checks; this pilot supplies no validated weights. More alternative opportunities alone have not restored a new major window.','',
        '![Matched original-winner coverage](pilot-coverage.png)','',
        '![Timing distributions with identical candidate counts](pilot-timing.png)','',
        'Reproduce with the pinned scientific Python environment: `python -m unittest discover -s reports/2026_10_17_dsx01_iteration4/peak_mixture -p "test_*.py" -v`, '
        '`python reports/2026_10_17_dsx01_iteration4/peak_mixture/run_pilot.py --source S03` (then S04), and `python reports/2026_10_17_dsx01_iteration4/peak_mixture/report_pilot.py`.']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')
    plots(records,sources)
    paths=[p for p in HERE.rglob('*') if p.is_file() and p.name!='manifest.json']
    (HERE/'manifest.json').write_text(json.dumps(dict(files=[dict(path=str(p.relative_to(HERE)),sha256=digest(p)) for p in sorted(paths)]),indent=2)+'\n')
    print(json.dumps(dict(records=len(records),sources=sources,observations=full_count,challenge=challenge_count,verified=True)))


def plots(records,sources):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    lookup={(r['source_id'],r['arm'],r['method']):r for r in records}
    fig,axes=plt.subplots(1,2,figsize=(10,3.7),sharey=True)
    for ax,arm in zip(axes,ARMS):
        for offset,method,color in [(-.18,METHODS[0],'#3979b2'),(.18,METHODS[1],'#df8c33')]:
            available=[s for s in sources if (s,arm,method) in lookup]
            ax.bar(np.arange(len(available))+offset,[100*lookup[s,arm,method]['winner_challenge']['associated']/lookup[s,arm,method]['winner_challenge']['observations'] for s in available],width=.35,color=color,label=method.split('-')[0])
        ax.set_xticks(np.arange(len(sources)),sources);ax.set_ylim(0,100);ax.set_title(arm);ax.set_ylabel('Original challenge winners associated (%)');ax.legend()
    fig.tight_layout();fig.savefig(HERE/'pilot-coverage.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(10,6),sharex=True)
    for axis,arm in zip(axes,ARMS):
        for metric,ax in zip(['relative','total'],axis):
            for label,color in [('seed','#777777'),*zip(METHODS,['#3979b2','#df8c33'])]:
                values=[]
                for sid in sources:
                    r=lookup.get((sid,arm,METHODS[0] if label=='seed' else label))
                    if r is None:continue
                    m=r['winner_seed'] if label=='seed' else r['winner_full_scan']
                    tau=np.array(list(m['total_timing_s'].values()))
                    values.extend(tau-m['common_timing_s'] if metric=='relative' else tau)
                ax.hist(values,bins=np.arange(-25,26),histtype='step',linewidth=1.7,color=color,label=f'{label.split("-")[0]} (n={len(values)})')
            ax.set_xlim(-25,25);ax.set_title(f'{arm}: {metric} timing');ax.set_xlabel('Seconds');ax.set_ylabel('Candidates');ax.legend(fontsize=8)
    fig.tight_layout();fig.savefig(HERE/'pilot-timing.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
