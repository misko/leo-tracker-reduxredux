"""Evaluate sealed shadow decisions; evaluation coordinates enter only here."""

import argparse
import csv
import hashlib
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from algo03_shadow_worker import read, write


def distance_km(position, truth):
    lat, lon, lat0, lon0 = map(math.radians, (*position, *truth))
    a = math.sin((lat-lat0)/2)**2 + math.cos(lat)*math.cos(lat0)*math.sin((lon-lon0)/2)**2
    return 6371.0088 * 2 * math.asin(min(1., math.sqrt(a)))


def run(args):
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    (out / 'figures').mkdir()
    cohort = read(args.study / 'cohort.json')
    rows, targets, hashes, evidence = [], [], {}, []

    def load(path):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return read(path)

    for n, job in enumerate(cohort['selected'], 1):
        folder = args.study / job['job_id']
        terminal = load(folder / 'terminal.json')
        inv = load(folder / 'all-large-track-recovery' / job['job_id'] / 'inventory.json')
        selected = terminal.get('selected')
        evidence.append(dict(job=job, terminal=terminal))
        for arm in ('c0', 'fitted_c'):
            baseline = terminal['baseline']['arms'][arm]
            after = selected['arms'][arm] if selected else baseline
            ids = {o for t in baseline['gates']['tracks'] + baseline.get('linear_gates', [])
                   for o in t['observation_ids']}
            retained = after['associated_ids'] if selected else ids
            count = next(r['total_GLRT'] for r in inv['summary'] if r['arm'] == arm)
            rows.append(dict(case=f'C{n}', recording=job['recording_name'], job_id=job['job_id'],
                arm=arm, decision=terminal['decision'], total_GLRT=count,
                before_associated=len(ids), after_associated=len(retained),
                before_percent=100*len(ids)/count, after_percent=100*len(retained)/count,
                before_error_km=distance_km(baseline['endpoint_latlon'], args.truth),
                after_error_km=distance_km(after['endpoint_latlon'], args.truth),
                baseline_objective=baseline['negative_twice_elbo'],
                selected_objective=after['negative_twice_elbo'],
                elapsed_seconds=terminal['total_seconds'],
                read_audit_verified=terminal['read_audit']['verified'],
                failure=terminal.get('failure')))
        for attempt in terminal.get('attempts', []):
            track = next(r for r in inv['tracks'] if r['track_id'] == attempt['track_id'])
            targets.append(dict(case=f'C{n}', component=track['component'],
                                points=attempt['points'], status=attempt['status'],
                                annotation=attempt.get('annotation'), track_id=attempt['track_id']))
    write(out / 'summary.json', dict(rows=rows, targets=targets,
          evaluation_only_latlon=args.truth, inference_uses_truth=False,
          primary_comparison='production ALGO02 versus bounded automatic shadow decision',
          full_ALGO03_release_evaluated=False))
    write(out / 'evidence.json', evidence)
    write(out / 'cohort.json', cohort)
    write(out / 'sources.json', hashes)
    with (out / 'results.csv').open('x') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
    for ax, arm in zip(axes[0], ('c0', 'fitted_c'), strict=True):
        group = [r for r in rows if r['arm'] == arm]
        x = np.arange(len(group))
        ax.bar(x-.17, [r['before_error_km'] for r in group], .34, label='Production ALGO02')
        ax.bar(x+.17, [r['after_error_km'] for r in group], .34, label='Automatic shadow policy')
        ax.set(xticks=x, xticklabels=[r['case'] for r in group], ylabel='Position error (km)', title=arm)
        ax.legend(fontsize=8)
    group = [r for r in rows if r['arm'] == 'fitted_c']
    x = np.arange(len(group))
    axes[1, 0].bar(x-.17, [r['before_percent'] for r in group], .34, label='ALGO02')
    axes[1, 0].bar(x+.17, [r['after_percent'] for r in group], .34, label='Shadow')
    axes[1, 0].set(xticks=x, xticklabels=[r['case'] for r in group], ylabel='Original GLRT associated (%)', ylim=(0, 100))
    axes[1, 0].legend()
    axes[1, 1].bar(x, [r['elapsed_seconds'] for r in group], color='#666666')
    axes[1, 1].set(xticks=x, xticklabels=[r['case'] for r in group], ylabel='Additional shadow runtime (s)')
    fig.suptitle('Automatic ALGO03 shadow canaries — all selected scans retained')
    fig.savefig(out / 'figures/canary_comparison.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(max(1, math.ceil(len(targets)/2)), 2,
                             figsize=(13, max(4, math.ceil(len(targets)/2)*3.5)), layout='constrained', squeeze=False)
    for ax, target in zip(axes.flat, targets):
        job = cohort['selected'][int(target['case'][1:])-1]
        folder = args.study / job['job_id']
        obs = load(folder / 'snapshot/inference/SCAN/observations.json')
        track = next(t for t in load(folder / 'snapshot/inference/SCAN/tracks.json') if t['key'] == target['component'])
        inv = read(folder / 'all-large-track-recovery' / job['job_id'] / 'inventory.json')
        baseline = evidence[int(target['case'][1:])-1]['terminal']['baseline']['arms']['fitted_c']
        old = {o for t in baseline['gates']['tracks'] + baseline.get('linear_gates', [])
               for o in t['observation_ids']}
        focus = set(track['observation_ids'])
        lo, hi = min(track['times'])-5, max(track['times'])+5
        nearby = [o for o in obs if o['receiver'] == track['receiver'] and o['channel'] == track['channel']
                  and lo <= o['time_s'] <= hi]
        for label, color, points in (
            ('Already associated', '0.75', [o for o in nearby if o['observation_id'] in old]),
            ('Other unassociated', '#e69f00', [o for o in nearby if o['observation_id'] not in old | focus]),
            ('Target before recovery', '#c51b7d', [o for o in nearby if o['observation_id'] in focus])):
            ax.scatter([o['time_s'] for o in points], [o['measured_cfo_hz']/1000 for o in points], s=12, c=color, label=label)
        ax.set(title=f"{target['case']} RX{track['receiver']} CH{track['channel']} · {target['points']} points\n{target['status']}",
               xlabel='Scan time (s)', ylabel='GLRT CFO (kHz)', xlim=(lo, hi))
        focus_y = [o['measured_cfo_hz']/1000 for o in nearby if o['observation_id'] in focus]
        if focus_y:
            pad = max(3, (max(focus_y)-min(focus_y))*.15)
            ax.set_ylim(min(focus_y)-pad, max(focus_y)+pad)
        ax.grid(alpha=.2)
    for ax in list(axes.flat)[len(targets):]:
        ax.set_visible(False)
    if targets:
        fig.legend(*axes.flat[0].get_legend_handles_labels(), loc='outside lower center', ncol=3)
    fig.savefig(out / 'figures/automatic_targets.png', dpi=160)
    plt.close(fig)
    write(out / 'sources_with_figures.json', hashes)
    table = '\n'.join(f"| {r['case']} | {r['decision']} | {r['before_associated']} → {r['after_associated']} | {r['before_percent']:.2f} → {r['after_percent']:.2f}% | {r['before_error_km']:.3f} → {r['after_error_km']:.3f} | {r['elapsed_seconds']:.1f} |" for r in group)
    paired = '\n'.join(f"| {r['case']} | {r['arm']} | {r['before_error_km']:.3f} | {r['after_error_km']:.3f} |" for r in rows)
    target_table = '\n'.join(f"| {t['case']} | {t['component']} | {t['points']} | {t['status']} |" for t in targets)
    mean_before = np.mean([r['before_error_km'] for r in group])
    mean_after = np.mean([r['after_error_km'] for r in group])
    report = f'''# ALGO03 automatic production shadow adapter: bounded canaries

This is an integration qualification of `algo03-shadow-top2-v1`, built on frozen `ALGO03-2026-10-30-r1`. It automatically discovers recovery targets in verified completed production ALGO02 analyses. Production still publishes `algo02-causal-family-v1`; no service default or public position contract changed. These four canaries do not establish full-cohort ALGO03 superiority.

Mean fitted-c error is **{mean_before:.3f} → {mean_after:.3f} km** across all four selected scans. The exact decisions, failures and rejected targets are retained below. Additional associated observations are not evidence of better localization by themselves.

**Accounting correction, October 30:** the first publication (`acba7b65a`) counted 29 unreported post-fit extrapolations in C3's baseline and unchanged shadow output. The corrected published-support count is 3,790 / 5,298 = 71.54%, rather than 3,819 = 72.08%. This correction changes neither position error nor recovery gains (C3 retains ALGO02); C2's 69-point gain is unchanged. The original sealed execution evidence is preserved. Future production comparisons use terminal-qualified IDs plus explicitly scored recovered targets.

| Canary | Shadow decision | Associated GLRT | Associated % | Fitted-c error, km | Added runtime, s |
| --- | --- | --- | --- | --- | --- |
{table}

![Matched canary comparisons](figures/canary_comparison.png)

## Selection and leakage controls

The cohort contains the first four job hashes among 95 completed, digest-verified fast 10 MS/s captures from October 26–29 available at discovery. Selection did not inspect RF trial outcomes or GPS error. Original acquisition manifests establish fast mode: the public tracking compatibility label says `adaptive` for these fast exports and must not be used as acquisition truth. [The frozen cohort](cohort.json) records recording names and provenance.

The existing store exports validated, content-hashed private copies through a new narrow `export_analysis` port. Source GLRT identity and terminal identity must match; symbolic links, changed files and exports into the production namespace are rejected. Downstream inference reads only its isolated copy and its current run artifacts. Every Python process must leave a read receipt; missing receipts or unrelated reads force fallback. Frozen ALGO03 implementation hashes are checked before launch. No future TLE or evaluation-coordinate read is authorized. The copied production catalogue and causal priors are reused rather than refreshed with later elements.

Evaluation coordinates {tuple(args.truth)} enter only this report generator. Inference uses the original 25 × 25 km regional box centered at (37.906, -122.545); position additions and controls cold-start at its center. The saved ALGO02 endpoint is an incumbent for replay and annotation, not a GPS initialization. This assesses downstream recovery conditional on the previously completed production graph and causal catalogue; it does not repeat acquisition or GLRT extraction.

## Automatic decision procedure

1. Replay the completed ALGO02 family solution and inventory all graph observations. A large unused track has at least 20 original IDs spanning 20 seconds.
2. Select at most two wholly unused native tracks, identically unused in both c arms, ranked by point count then stable track ID. Partial tracks remain visible in the inventory but are deferred by this first adapter.
3. Directly nominate up to twelve causal satellite candidates. Use three distinct randomized 12-second physical-block holdouts with 2-second guards and shifted block origins. Targets do not calibrate receiver nuisance variables during annotation. These overlapping folds are not independent replications. This direct-cap-twelve route differs operationally from the research workflow's three-candidate-then-twelve replay.
4. Require predictive identity consensus and existing separation/physical gates. Run the matching existing-family or new-family inclusion with paired c=0/fitted-c controls, then exact orbit and ownership audits. A new family uses 0.025-second phase integration. Do not count unscored incidental extensions.
5. If two distinct new families qualify individually, jointly fit them with shared receiver covariance, both c arms, matched controls and local quadrature/physical audits. Otherwise choose the first qualifying individual in the predetermined ranking. Separate individual solutions are never summed. Same-family or mixed-route combinations are deferred.
6. Retain ALGO02 if no candidate qualifies or the final read audit fails. Every stage is capped at 600 seconds, with a 1,200-second total recovery budget. This first adapter omits numerical retries; research ALGO03 includes bounded matched Powell retries, which still need runtime integration. Original ALGO02 processing time is additional to the reported recovery runtime.

## Matched c ablation

| Canary | Arm | ALGO02 error, km | Shadow error, km |
| --- | --- | --- | --- |
{paired}

All arm observations, candidates, other priors and search budgets are matched. Raw negative twice evidence is retained in [results.csv](results.csv), but objectives with different observation sets are not directly comparable fit improvements. Position accuracy is reported separately.

## Disposition of automatically selected curves

| Canary | Component | Points | Outcome |
| --- | --- | --- | --- |
{target_table}

![Automatically selected native GLRT curves](figures/automatic_targets.png)

Gray means already associated; orange means other unassociated points; magenta highlights the target before recovery. Rejected targets remain unassociated. Plotting a coherent curve is not sufficient evidence for a unique satellite identity.

## Implementation, validation and promotion decision

New files: `tools/algo03_shadow_worker.py` (automatic bounded recovery), `tools/run_algo03_shadow.py` (validated export and guarded execution), and `tools/report_algo03_shadow.py` (evaluation only). The existing storage component gains `export_analysis`; production processing and persisted position contracts are unchanged. Component tests cover snapshot isolation and identity, symbolic links, paired target selection, scoped observation credit, missing/denied read receipts and corrupt-input fallback. Existing production and scientific regression tests remain required.

This adapter is ready for further bounded shadow qualification, not default promotion. Remaining work includes numerical-only retry integration, coverage of partial tracks and mixed/shared-family combinations, fresh positive joint-route integration tests, a larger frozen matched cohort with tail/error/runtime acceptance criteria, and continuous shadow service packaging. Four canaries cannot justify replacing ALGO02. Preserve every regression and failure in subsequent comparisons.

Full sealed decisions and exact per-track evidence references are in [evidence.json](evidence.json); [sources.json](sources.json) and [sources_with_figures.json](sources_with_figures.json) pin local inputs. These are shadow results, not deployed output changes.
'''
    (out / 'README.md').write_text(report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--truth', type=float, nargs=2, required=True)
    run(parser.parse_args())
