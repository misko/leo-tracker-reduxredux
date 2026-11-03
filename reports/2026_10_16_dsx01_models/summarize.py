"""Render all results, including failed and nonstationary research endpoints."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from common import HERE, DATASET, save_json


METHODS = ['original','continuation','A','B','C']
COLORS = dict(zip(METHODS,['#777777','#8056b3','#0072b2','#d55e00','#009e73']))


def csv_out(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def main():
    paths = sorted((HERE/'results').glob('*.json'))
    records = [json.loads(p.read_text()) for p in paths]
    failures = [r for r in records if r.get('status')=='failed']
    good = [r for r in records if r.get('status')!='failed']
    sources = json.loads((DATASET/'sources.json').read_text())
    baselines = {r['source_id']:r for r in good if r['method']=='original'}
    rows = []
    timing_rows = []
    for r in good:
        m = r['full_scan']
        b = baselines.get(r['source_id'])
        baseline = b['full_scan'] if b else None
        row = dict(source_id=r['source_id'],mode=r['mode'],arm=r['arm'],method=r['method'],
            observations=m['observations'],associated=m['associated'],association_pct=m['association_pct'],
            associated_rms_hz=m['associated_rms_hz'],
            intersection_original_rms_hz=m.get('intersection_original_rms_hz'),
            intersection_variant_rms_hz=m.get('intersection_variant_rms_hz'),
            new_associations=m.get('new_associations'),lost_associations=m.get('lost_associations'),
            retained_identity_changes=m.get('retained_identity_changes'),
            challenge_associated=r['challenge']['associated'],challenge_observations=r['challenge']['observations'],
            outside_new=r['outside_challenge'].get('new_associations'),
            outside_lost=r['outside_challenge'].get('lost_associations'),
            common_timing_s=m['common_timing_s'],relative_timing_rms_s=m['relative_timing_rms_s'],
            relative_timing_max_s=m['relative_timing_max_s'],
            configured_reference_distance_km=m.get('configured_reference_distance_km'),
            position_movement_km=m['position_movement_km'],c=m['c'],
            strict_accepted=r['endpoint_audit']['accepted'],stationarity=r['endpoint_audit'].get('stationarity'),
            inference_evaluations=r['inference_diagnostics'].get('evaluations',0))
        if r['mode']=='full' and baseline:
            row['association_gain_pp'] = m['association_pct']-baseline['association_pct']
            row['common_timing_change_s'] = m['common_timing_s']-baseline['common_timing_s']
            delta = [t-baseline['total_timing_s'][sv] for sv,t in m['total_timing_s'].items()]
            row['total_timing_change_rms_s'] = float(np.sqrt(np.mean(np.square(delta))))
            row['total_timing_change_max_s'] = float(np.max(abs(np.asarray(delta))))
            for sv,value in m['total_timing_s'].items():
                timing_rows.append(dict(source_id=r['source_id'],arm=r['arm'],method=r['method'],satellite=sv,
                    original_total_timing_s=baseline['total_timing_s'][sv],variant_total_timing_s=value,
                    change_s=value-baseline['total_timing_s'][sv]))
        if 'held' in r:
            row.update(held_observations=r['held']['observations'],held_associated=r['held']['associated'],
                held_association_pct=r['held']['association_pct'],held_associated_rms_hz=r['held']['associated_rms_hz'])
        rows.append(row)
    csv_out(HERE/'comparison.csv',rows)
    csv_out(HERE/'satellite-timing.csv',timing_rows)

    # Frozen source order is preserved by public input replay and pinned receipts.
    observations = [json.loads(line) for line in (DATASET/'context-observations.jsonl').read_text().splitlines()]
    original_ids = {s['source_id']:[o['observation_id'] for o in observations if o['source_id']==s['source_id']] for s in sources}
    lookups = {s:{key:i for i,key in enumerate(ids)} for s,ids in original_ids.items()}
    with (DATASET/'membership.csv').open() as stream:
        members = list(csv.DictReader(stream))
    regions = json.loads((DATASET/'dataset.json').read_text())['regions']
    region_rows = []
    for r in good:
        saved = np.load(HERE/'results'/(r['task']+'.npz'))
        assigned = saved['associated']
        for region in regions:
            if region['source_id']!=r['source_id']:
                continue
            ix = [lookups[r['source_id']][m['observation_id']] for m in members if m['region_id']==region['region_id']]
            region_rows.append(dict(source_id=r['source_id'],region_id=region['region_id'],mode=r['mode'],
                arm=r['arm'],method=r['method'],observations=len(ix),associated=int(assigned[ix].sum()),
                associated_pct=100*float(assigned[ix].mean())))
    csv_out(HERE/'regions.csv',region_rows)
    controls = json.loads((DATASET/'auxiliary-controls.json').read_text())
    control_rows = []
    for r in good:
        a = np.load(HERE/'results'/(r['task']+'.npz'))
        for control in controls:
            if control['source_id']!=r['source_id'] or 'observation_ids' not in control:
                continue
            ix = [lookups[r['source_id']][key] for key in control['observation_ids']]
            control_rows.append(dict(source_id=r['source_id'],control_id=control['control_id'],
                method=r['method'],arm=r['arm'],mode=r['mode'],observations=len(ix),
                associated=int(a['associated'][ix].sum())))
    csv_out(HERE/'controls.csv',control_rows)

    selected = [r for r in rows if r['mode']=='full' and r['arm']=='fitted-c']
    fig,axes = plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
    plot_specs = [('association_pct','Satellite association (%)'),('associated_rms_hz','Assigned-point frequency RMS (Hz)'),
                  ('relative_timing_rms_s','Relative satellite timing RMS (s)'),
                  ('configured_reference_distance_km','Distance to configured station (km)')]
    x = np.arange(len(sources))
    for ax,(field,label) in zip(axes.flat,plot_specs):
        for j,method in enumerate(METHODS):
            table = {r['source_id']:r for r in selected if r['method']==method}
            values = [table.get(s['source_id'],{}).get(field,np.nan) for s in sources]
            ax.bar(x+(j-2)*.15,values,width=.14,label=method,color=COLORS[method])
        ax.set_xticks(x,[s['source_id'] for s in sources])
        ax.set_ylabel(label)
        ax.grid(axis='y',alpha=.2)
    axes[0,0].legend(ncol=3,fontsize=9)
    fig.suptitle('DSX01: original vs equal-budget research variants, fitted-c\nUnchanged detections, candidate banks and production classification; station reference is not surveyed truth')
    fig.savefig(HERE/'comparison.png',dpi=170)
    plt.close(fig)

    fig,axes = plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
    for method in METHODS:
        group = [r for r in good if r['mode']=='full' and r['arm']=='fitted-c' and r['method']==method]
        residuals = []
        denominator = sum(s['observation_count'] for s in sources)
        positions = []
        for r in group:
            a = np.load(HERE/'results'/(r['task']+'.npz'))
            residuals.extend(abs(a['residual_hz'][a['associated']]))
            value = r['full_scan'].get('configured_reference_distance_km')
            if value is not None:
                positions.append(value)
        for ax,values,denom in ((axes[0],residuals,denominator),(axes[1],positions,len(sources))):
            ordered = np.sort(values)
            if len(ordered):
                ax.step(ordered,np.arange(1,len(ordered)+1)/denom,where='post',label=method,color=COLORS[method])
            ax.set_xscale('log')
            ax.set_ylim(0,1.02)
            ax.grid(alpha=.2)
    axes[0].set_xlabel('Absolute assigned frequency residual (Hz)')
    axes[0].set_ylabel('Fraction of all 20,084 original observations')
    axes[1].set_xlabel('Distance to configured station reference (km)')
    axes[1].set_ylabel('Fraction of all five recordings')
    axes[0].legend()
    fig.suptitle('DSX01: missing / unassociated outputs stay in denominator\nResearch endpoints include nonstationary fits; reference position is operator configured')
    fig.savefig(HERE/'distributions.png',dpi=170)
    plt.close(fig)

    full_aggregate = []
    for method in METHODS:
        group = [r for r in selected if r['method']==method]
        n = sum(r['observations'] for r in group)
        assigned = sum(r['associated'] for r in group)
        sumsq = sum(r['associated']*r['associated_rms_hz']**2 for r in group if r['associated_rms_hz'] is not None)
        full_aggregate.append(dict(method=method,completed_recordings=len(group),observations=n,
            associated=assigned,association_pct=100*assigned/20084,
            associated_rms_hz=float(np.sqrt(sumsq/assigned)) if assigned else None,
            challenge_associated=sum(r['challenge_associated'] for r in group),challenge_total=693,
            strict_accepted=sum(bool(r['strict_accepted']) for r in group)))
    held_rows = []
    held_denominators = {}
    for direction in ['early_to_late','late_to_early']:
        total = 0
        for source in sources:
            times = np.array([o['time_s'] for o in observations if o['source_id']==source['source_id']])
            train = times<=np.median(times) if direction=='early_to_late' else times>np.median(times)
            total += int((~train).sum())
        held_denominators[direction] = total
    for arm in ['fitted-c','zero-c']:
        for direction in ['early_to_late','late_to_early']:
            for method in METHODS[1:]:
                group = [r for r in good if r['mode']==direction and r['arm']==arm and r['method']==method]
                n = held_denominators[direction]
                k = sum(r['held']['associated'] for r in group)
                ss = sum(r['held']['associated']*r['held']['associated_rms_hz']**2 for r in group if r['held']['associated_rms_hz'] is not None)
                held_rows.append(dict(arm=arm,direction=direction,method=method,completed_recordings=len(group),
                    held_observations=n,held_associated=k,held_association_pct=100*k/n if n else None,
                    held_associated_rms_hz=float(np.sqrt(ss/k)) if k else None))
    csv_out(HERE/'temporal-comparison.csv',held_rows)
    fig,axes = plt.subplots(1,2,figsize=(12,4.5),constrained_layout=True)
    for ax,direction in zip(axes,['early_to_late','late_to_early']):
        group = [r for r in good if r['mode']==direction and r['arm']=='fitted-c']
        denom = held_denominators[direction]
        for method in METHODS[1:]:
            values = []
            for r in group:
                if r['method']!=method:
                    continue
                a = np.load(HERE/'results'/(r['task']+'.npz'))
                take = a['associated'] & ~a['train_mask']
                values.extend(abs(a['residual_hz'][take]))
            ordered = np.sort(values)
            if len(ordered):
                ax.step(ordered,np.arange(1,len(ordered)+1)/denom,where='post',label=method,color=COLORS[method])
        ax.set_xscale('log')
        ax.set_ylim(0,1.02)
        ax.set_title(direction.replace('_',' '))
        ax.set_xlabel('Held absolute assigned residual (Hz)')
        ax.set_ylabel('Fraction of all held observations')
        ax.grid(alpha=.2)
    axes[0].legend()
    fig.suptitle('DSX01 temporal tests: neutral training-only initialization\nFixed candidate bank conditioned on prior full-recording discovery; no strict endpoint passed')
    fig.savefig(HERE/'temporal-distributions.png',dpi=170)
    plt.close(fig)
    save_json(HERE/'summary.json',dict(aggregate_fitted_c=full_aggregate,temporal=held_rows,failures=failures,results=len(good)))
    lines = ['# DSX01: three parallel model implementations and evaluation','',
        'The evaluation was agreed before implementation. [Protocol](EVALUATION.md). '
        'These are bounded research fits, with strict convergence reported separately. '
        'No production settings, recordings, detections or frozen dataset memberships changed.','',
        '![Per-recording comparison](comparison.png)','',
        '| Method | Full-scan associations | Associated RMS (Hz) | Challenge associations | Regional KKT passes |',
        '|---|---:|---:|---:|---:|']
    for r in full_aggregate:
        rms = f"{r['associated_rms_hz']:.2f}" if r['associated_rms_hz'] is not None else 'missing'
        lines.append(f"| {r['method']} | {r['associated']}/20084 ({r['association_pct']:.2f}%) | {rms} | {r['challenge_associated']}/693 | {r['strict_accepted']}/5 |")
    lines += ['','The original endpoints passed their saved production audits. The research KKT audit '
        'uses the common full regional search disk. In particular, S02 was stationary on its original '
        'active 25 km local disk; removing that disk makes its regional KKT fail. This does not '
        'invalidate its published production receipt. Every variant and continuation uses the same '
        'regional domain for this comparison.','',
        '| Source | Recording |','|---|---|']
    lines.extend(f"| {s['source_id']} | {s['recording_id']} |" for s in sources)
    lines += ['','Original → A, fitted-c. Timing differences use the same ordered satellite bank; '
        'RMS Δτ is the change in total satellite timings, not frequency residual RMS.','',
        '| Source | Association (%) | Associated RMS (Hz) | Common τ (s) | RMS Δτ (s) | Configured-reference distance (km) |',
        '|---|---:|---:|---:|---:|---:|']
    for source in sources:
        a = next((r for r in selected if r['source_id']==source['source_id'] and r['method']=='A'),None)
        b = next((r for r in selected if r['source_id']==source['source_id'] and r['method']=='original'),None)
        if a is None or b is None:
            continue
        lines.append(f"| {source['source_id']} | {b['association_pct']:.2f} → {a['association_pct']:.2f} | "
            f"{b['associated_rms_hz']:.2f} → {a['associated_rms_hz']:.2f} | "
            f"{b['common_timing_s']:.3f} → {a['common_timing_s']:.3f} | {a['total_timing_change_rms_s']:.3f} | "
            f"{b['configured_reference_distance_km']:.3f} → {a['configured_reference_distance_km']:.3f} |")
    lines += ['','A uses automatic carrier arcs to propose shared satellite timings, then q and joint refitting. '
        'B combines evidence through a shared latent identity over disjoint carrier segments, with point clutter. '
        'C divides the same allowance across six deterministic geometry/calibration/timing starts. '
        'The original production association rule is used to measure every method.','',
        '![Residual and position-reference distributions](distributions.png)','',
        'The associated-point RMS changes population when new detections are assigned. '
        '[comparison.csv](comparison.csv) includes paired RMS on the intersection, new/lost assignments, '
        'outside-window effects, timing and reference-position distances. '
        '[satellite-timing.csv](satellite-timing.csv) has every satellite timing change; '
        '[regions.csv](regions.csv) retains all 15 frozen windows. '
        '[controls.csv](controls.csv) reports original-observation auxiliary controls C05 and C07 '
        'without adding them to the primary denominator.','',
        'The configured reference is bound by matching radio serial and validity interval to '
        '`gauss-r20-lt3d-004b-20261001-v1`. Coordinates were previously operator supplied; '
        'survey uncertainty and altitude are unknown. They are never optimizer inputs. '
        'Position distance here is distance to that configuration, not independent surveyed error.','',
        'A adds 658 net scan associations and 157 net challenge-window associations. However, '
        'paired intersection RMS worsens slightly on S01 and S05. S01 alone loses 188 previously '
        'assigned observations outside the challenge windows while adding 298 there. These losses '
        'are not hidden by the net gain. All five A endpoints fail the regional stationarity check. '
        'No method has established a material localization improvement or passed promotion gates.','',
        'Full-data warm-start experiments are development diagnostics. Temporal experiments use '
        'neutral seeds and zero frozen band contrast, excluding held CFO from fitting. Their '
        'candidate bank is still conditioned on full-recording discovery. Neither experiment is '
        'an untouched end-to-end test. Failed and nonstationary results remain in the artifacts.','',
        '![Excluded-data residual distributions](temporal-distributions.png)','',
        '| Fitted-c temporal direction | Method | Held associations | Associated held RMS (Hz) |',
        '|---|---|---:|---:|']
    for r in held_rows:
        if r['arm']=='fitted-c' and r['held_association_pct'] is not None:
            lines.append(f"| {r['direction']} | {r['method']} | {r['held_associated']}/{r['held_observations']} ({r['held_association_pct']:.2f}%) | {r['held_associated_rms_hz']:.2f} |")
    lines += ['','The neutral cold starts associate only about 12% of held observations. A modestly '
        'improves both temporal directions relative to the same-start continuation, but none of '
        'these cold training endpoints passes strict convergence. This is evidence of an unresolved '
        'initialization/generalization problem, not validation of the full-data association gains. '
        'The small residual among assigned held points must be read together with this low coverage.','',
        'Fitted-c is the headline. The complete matched c=0 sensitivity appears in '
        '[comparison.csv](comparison.csv) and [temporal-comparison.csv](temporal-comparison.csv). '
        'In the full-data runs, continuation/A associate 46.94%/47.66% with c=0, versus '
        '55.92%/59.15% with fitted-c; these capped c=0 fits are nonstationary, so the comparison '
        'is a budget-matched sensitivity rather than a comparison of converged optima. '
        'Frequency gains do not establish geographic accuracy.','',
        'Detailed next-step diagnoses: [A](model_a_diagnosis.md), [B](model_b_diagnosis.md), '
        '[C](model_c_diagnosis.md).','',
        'The main A regression mechanism is prediction changes: 261 of 271 outside-window losses '
        'persist when the old detection probabilities are restored. In S01, retiming satellite '
        '51117 from −14.55 s to −1.18 s replaces its earlier support. This is not explained by '
        'detection-q suppression alone. The old identities are not truth, so these are losses of '
        'established model support rather than proven new identity errors. B improves its trajectory '
        'surrogate but four of five proposals worsen the exact common objective. C exhausts its '
        '30-evaluation allocation on all 25 alternate starts without convergence. The next iteration '
        'should preserve competing timing branches, rank them with exact predictions, and allocate '
        'refinement to fewer promising basins before changing the physical model.','',
        'Reproduce with the pinned scientific runtime documented in [RUNTIME.md](RUNTIME.md). '
        '[validation.json](validation.json) checks all 125 receipts, bounds, budgets, frozen '
        'denominators, original replay and complementary held masks.','',
        f"Saved results: {len(good)} completed receipts; {len(failures)} failures. "
        "A completed receipt means evaluation finished, not that its endpoint passed strict convergence."]
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(results=len(good),failures=len(failures),aggregate=full_aggregate)),flush=True)


if __name__=='__main__':
    main()
