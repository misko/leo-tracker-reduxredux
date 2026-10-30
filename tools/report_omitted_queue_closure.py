"""Reconcile every frozen omitted-curve candidate across published batch reports."""
import argparse
import csv
import hashlib
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from debug_fast_graph_unassociated import read, write
from report_predictive_track_annotation import table
from report_omitted_recovery_batch import reviewed_points


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    sources = {}; rows = {}; annotations = {}
    def csvread(path):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return list(csv.DictReader(path.open()))
    for report in args.reports:
        for r in csvread(report/'final_positions.csv'):
            if r['track_id'] in rows:
                raise ValueError('duplicate candidate across batches')
            rows[r['track_id']] = dict(r, batch_report=str(report))
        for r in csvread(report/'annotations.csv'):
            annotations[r['track_id']] = r
    expected = {r['track_id'] for r in read(args.registry/'pending_candidates.json')}
    if set(rows) != expected or set(annotations) != expected:
        raise ValueError('batch reports do not exactly cover frozen pending registry')
    series_path = args.reports[-1]/'series_qualified_trials.json'
    series = read(series_path); reviewed = {r['track_id']:r for r in series}
    for path in (series_path, args.registry/'pending_candidates.json'):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    for tid, r in rows.items():
        r['annotation_status'] = annotations[tid]['status']
        review = reviewed.get(tid)
        if review is not None:
            r['review_status'] = 'RF_candidate' if review['reviewed_candidate'] else 'common_residual_withheld'
        elif r['annotation_status'] != 'conditionally_supported_identity':
            r['review_status'] = r['annotation_status']
        else:
            r['review_status'] = 'inclusion_checks_failed'
    counts = Counter(r['review_status'] for r in rows.values())
    points = Counter()
    for r in rows.values():
        points[r['review_status']] += int(r['points'])
    states = [dict(state=k, tracks=n, points=points[k]) for k,n in counts.items()]
    qualified = [r for r in rows.values() if r['review_status']=='RF_candidate']
    direction = {arm:dict(improved=sum(float(r[arm+'_after_km']) < float(r[arm+'_before_km']) for r in qualified),
        worsened=sum(float(r[arm+'_after_km']) > float(r[arm+'_before_km']) for r in qualified)) for arm in ('c0','fitted_c')}
    fig, axes = plt.subplots(1,2,figsize=(13,5),layout='constrained')
    labels = [r['state'].replace('_',' ') for r in states]
    for ax, key in zip(axes, ('tracks','points'), strict=True):
        values = [r[key] for r in states]; bars = ax.barh(labels, values)
        ax.bar_label(bars); ax.set(xlabel=key.capitalize(), title='Final review state'); ax.invert_yaxis()
    fig.savefig(args.output/'queue_outcomes.png',dpi=140); plt.close(fig)
    records = list(rows.values()); keys = list(dict.fromkeys(k for r in records for k in r))
    with (args.output/'all_candidates.csv').open('x') as f:
        w = csv.DictWriter(f,fieldnames=keys,lineterminator='\n'); w.writeheader(); w.writerows(records)
    write(args.output/'summary.json',dict(total=len(rows),states=states,reviewed_points=len(reviewed_points(series)),
        capture_modes=dict(Counter(r['capture_mode'] for r in rows.values())),
        individual_candidate_error_direction=direction,full_goal_complete=False,production_changed=False))
    write(args.output/'sources.json',sources)
    links = '\n'.join(f'- [{p.name}](../{p.name}/README.md)' for p in args.reports)
    (args.output/'README.md').write_text(f'''# Closing the 53-curve omitted-inclusion queue

All **{len(rows)}** frozen candidates now have terminal assessments and a linked review outcome. The original selector excluded these curves because they were absent from the calibration engine. The predictive route now assesses them without allowing them to calibrate receiver offsets or drift. This closes this particular queue; the full 1,630-curve annotation and inclusion objective remains incomplete.

{table(states,['state','tracks','points'])}

![Queue outcomes](queue_outcomes.png)

The reviewed series contains **{len(reviewed_points(series))} distinct candidate GLRT points**. These are separate per-curve research inclusions, not one simultaneous solution or a dataset-wide association percentage. Capture modes verified from source metadata are **{dict(Counter(r['capture_mode'] for r in rows.values()))}**. Do not describe this research inventory as a DS24-fast benchmark. The fourth batch explicitly maps its legacy DS24 aliases to their adaptive DS25 source cases.

Every retained candidate passes the same causal, predictive-role, randomized grouped holdout and paired c=0/fitted-c checks. Two earlier individual passes remain withheld because their joint residual has common structure. Insufficient partitions means insufficient independent validation evidence, not proof that a curve is noise or has no satellite source. Inclusion failures retain residual, ownership, phase and numerical evidence in the batch reports.

Among individual reviewed candidates, position error improves/worsens in **{direction['c0']['improved']}/{direction['c0']['worsened']}** c=0 comparisons and **{direction['fitted_c']['improved']}/{direction['fitted_c']['worsened']}** fitted-c comparisons. These paired trials reuse some scans and are not independent scan-level samples. Their controls can differ after numerical retries; no dataset median, combined recovery gain, or promotion claim is inferred. In particular, the 60342 addition worsens fitted-c error from 0.090 to 0.937 km despite passing RF checks.

## What remains

The [60342 influence audit](../2026_10_30_omitted_predictive_third_batch/README.md) shows weak position constraints and a target preference that persists under a uniform-phase diagnostic. The [residual-scale audit](../2026_10_30_predictive_residual_scale/README.md) identifies uneven residual scatter not represented by the radio uncertainty proxy. Both require further discrimination between measurement error, receiver effects and satellite-model discrepancy.

Next, test independently measured uncertainty and shared receiver discrepancies across satellite families, and combine recovered families using a single shared receiver-uncertainty model. Short curves lacking independent holdouts need genuinely independent supporting evidence; shortening guards or counting repeated target holds would not supply it. Reconcile older calibration-participating annotations into the predictive-only role before claiming inventory-wide completion. Ambiguous identities and physical failures remain explicit unresolved records.

## Evidence and reports

[all_candidates.csv](all_candidates.csv) has exactly one row per frozen candidate, with original batch results and final review state separately preserved. [sources.json](sources.json) hashes the inputs; the reporter rejects missing or duplicate coverage. Each batch contains native GLRT plots, residual plots, position comparisons, receipts, holdout assignments and exact-orbit replay evidence.

{links}

No GPS selects candidates or relaxes gates. No post-observation TLE or new RF acquisition is introduced. Production is unchanged.
''')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--registry',type=Path,required=True)
    p.add_argument('--reports',type=Path,nargs='+',required=True)
    p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
