"""Publish the joint receiver-covariance experiment and its bounded position fits."""
import argparse
import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from debug_fast_graph_unassociated import read, write
from report_inventory_experiments import error
from report_predictive_track_annotation import table


def run(args):
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    (out/'figures').mkdir()
    hashes, evidence = {}, {}
    def load(p):
        hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
        evidence[str(p)] = read(p)
        return evidence[str(p)]
    def verify(record):
        for name, digest in record.get('source_hashes', {}).items():
            if hashlib.sha256(Path(name).read_bytes()).hexdigest() != digest:
                raise ValueError('source changed: '+name)
    def csvout(name, rows):
        with (out/name).open('x') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
    def save(fig, name):
        fig.savefig(out/'figures'/name, dpi=145)
        plt.close(fig)

    root = args.study/'two-new-family-likelihood-v2'
    protocol = load(root/'protocol.json')
    verify(protocol)
    executions = load(root/'execution.json')
    if len(executions) != 4 or any(r['status'] != 'complete' for r in executions):
        raise ValueError('likelihood probes incomplete')
    old = load(args.study/'two-new-family-likelihood-v1/terminal.json')
    if old['status'] != 'failed':
        raise ValueError('missing historical failed probe')
    shutil.copyfile(args.study/'two-new-family-likelihood-v1/probe.log', out/'failed-probe.log')
    steps = [.25, .125, .0625, .03125]
    probes, gradients, centers = {}, [], []
    for step in steps:
        p = load(root/str(step)/'protocol.json')
        verify(p)
        r = load(root/str(step)/'result.json')
        if not (r['all_individual_replays_verified'] and r['receiver_calibration_unchanged']):
            raise ValueError('unverified likelihood geometry')
        probes[step] = r
        for arm in ('c0', 'fitted_c'):
            z = next(v for v in r['rows'] if v['arm'] == arm and v['offset_km'] == [0., 0.])
            centers.append(dict(step_s=step, arm=arm, difference=z['joint_minus_factorized'],
                largest_cross_correlation=z['largest_cross_correlation'], seconds=z['seconds'],
                phase_pairs=z['phase_pair_count']))
            for method, g in r['gradients_per_km'][arm].items():
                gradients.append(dict(step_s=step, arm=arm, method=method, east=g[0], north=g[1]))
    csvout('likelihood_centers.csv', centers)
    csvout('likelihood_gradients.csv', gradients)
    targets = p['targets']
    inventory = load(args.study/'all-large-track-recovery'/p['job']['job_id']/'inventory.json')
    total_glrt = inventory['summary'][0]['total_GLRT']
    members = [dict(norad=g[0]['norad'], component=e['component'], points=e['points'])
               for g in targets for e in g]
    position = args.study/'two-new-family-position-v1'
    verify(load(position/'protocol.json'))
    fits = load(position/'execution.json')
    if len(fits) != 6 or any(r['status'] != 'complete' for r in fits):
        raise ValueError('position fits incomplete')
    original_audit = load(position/'audit-protocol.json')
    archive = position/'audit-source-v1.py'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != original_audit['source_hashes']['tools/audit_two_predictive_families.py']:
        raise ValueError('failed audit source not preserved')
    shutil.copyfile(archive, out/'audit-source-v1.py')
    first_audits = load(position/'audit-execution.json')
    final_audits = load(position/'audit-execution-v2.json')
    verify(load(position/'audit-protocol-v2.json'))
    if len(final_audits) != 2 or any(v['status'] != 'complete' for v in final_audits):
        raise ValueError('joint audits incomplete')
    if any(v['status'] != 'complete' for v in first_audits if not v['name'].startswith('joint-')):
        raise ValueError('control/factorized audits incomplete')
    for arm in ('c0', 'fitted_c'):
        shutil.copyfile(position/('joint-'+arm+'-audit.log'), out/('failed-joint-'+arm+'-audit.log'))
    retry = args.study/'two-new-family-position-v2'
    verify(load(retry/'protocol.json'))
    for file in ('execution.json', 'audit-execution.json'):
        terminal = load(retry/file)
        if len(terminal) != 6 or any(v['status'] != 'complete' for v in terminal):
            raise ValueError('matched numerical retries incomplete')
    verify(load(retry/'audit-protocol.json'))
    rows, results, audits, initial = [], {}, {}, []
    for variant, directory in (('initial_lbfgsb', position), ('matched_powell', retry)):
        for method in ('control', 'factorized', 'joint'):
            for arm in ('c0', 'fitted_c'):
                name = method+'-'+arm
                folder = directory/name
                verify(load(folder/'protocol.json'))
                r = load(folder/'result.json')
                a = load(folder/('audit-v2.json' if method == 'joint' and directory == position else 'audit.json'))
                verify(a)
                row = dict(variant=variant, method=method, arm=arm, error_km=error(r),
                    east_km=r['endpoint_east_north_km'][0], north_km=r['endpoint_east_north_km'][1],
                    reviewed_points=len(a['reviewed_ids']), RF_qualified_arm=a['RF_qualified_arm'],
                    associated_percent=100*len(a['reviewed_ids'])/total_glrt,
                    optimizer_completed=r['history'][-1]['success'], phase_change_s=r['history'][-1]['phase_change_s'],
                    incumbent_objective=r['incumbent_objective'], joint_evidence=r['joint_evidence'],
                    factorized_evidence=r['factorized_evidence'], seconds=r['seconds'])
                if directory == position:
                    initial.append(row)
                else:
                    rows.append(row)
                    results[method, arm], audits[method, arm] = r, a
    paired = {method: all(audits[method, arm]['RF_qualified_arm'] and audits['control', arm]['RF_qualified_arm']
                         for arm in ('c0', 'fitted_c')) for method in ('factorized', 'joint')}
    csvout('position_comparison.csv', initial+rows)
    gate_rows = [dict(method=method, arm=arm, gate=key, passed=value)
                 for (method, arm), a in audits.items() for key, value in a['checks'].items()]
    csvout('qualification.csv', gate_rows)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout='constrained')
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        for coordinate, style in (('east', '-'), ('north', '--')):
            for method, marker in (('joint_score', 'o'), ('factorized_score', 'x')):
                g = [z for z in gradients if z['arm'] == arm and z['method'] == method]
                ax.plot(steps, [z[coordinate] for z in g], style+marker,
                        label=coordinate+' / '+method.replace('_score', ''))
        ax.set(xlabel='Phase grid spacing (s)', ylabel='New-evidence loss gradient / km', title=arm)
        ax.set_xscale('log', base=2)
        ax.grid(alpha=.2)
        ax.legend(fontsize=7)
    save(fig, 'phase_gradient.png')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout='constrained')
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        group = [r for r in rows if r['arm'] == arm]
        ax.bar([r['method'] for r in group], [r['error_km'] for r in group], color=['#999', '#e69f00', '#0072b2'])
        ax.set(ylabel='Evaluation position error (km)', title=arm)
        ax.grid(axis='y', alpha=.2)
    save(fig, 'position_comparison.png')
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout='constrained')
    for column, member in enumerate(members):
        for arm in ('c0', 'fitted_c'):
            d = audits['joint', arm]['continuous_target']['diagnostics'][column]
            prediction = np.array(d['prediction_CFO_hz'])+d['profile_bias_hz']
            if arm == 'c0':
                axes[0, column].plot(d['times_s'], np.array(d['CFO_hz'])/1000, '.', color='#777', label='Target GLRT')
            axes[0, column].plot(d['times_s'], prediction/1000, label=arm+' joint prediction')
            axes[1, column].plot(d['times_s'], np.array(d['raw_residual_hz'])-d['profile_bias_hz'], '.-', lw=.7, label=arm)
        axes[0, column].set(title=str(member['norad'])+' / '+member['component'].split('-RF')[0], ylabel='CFO (kHz)')
        axes[1, column].set(ylabel='Residual after constant bias (Hz)')
        axes[1, column].axhline(0, color='k', lw=.5)
        for ax in axes[:, column]:
            ax.set_xlabel('Scan time (s)')
            ax.grid(alpha=.2)
            ax.legend(fontsize=7)
    save(fig, 'joint_curves.png')

    # Carry forward the comprehensive inventory without changing individual outcomes.
    previous = args.previous/'annotation_ledger.csv'
    hashes[str(previous)] = hashlib.sha256(previous.read_bytes()).hexdigest()
    ledger = list(csv.DictReader(previous.open()))
    target_ids = ['173a919a922143a8bd56', 'e48e3d30781aaf4e482c']
    if set(target_ids) - {r['track_id'] for r in ledger}:
        raise ValueError('joint target absent from ledger')
    for row in ledger:
        if row['track_id'] in target_ids:
            row.update(two_family_joint_source=str(retry),
                       two_family_joint_state='RF_verified_joint_research_candidate' if paired['joint'] else 'joint_inclusion_withheld')
    with (out/'annotation_ledger.csv').open('x') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for r in ledger for k in r)), lineterminator='\n')
        writer.writeheader()
        writer.writerows(ledger)
    for name in ('remaining_shifted_candidates.json', 'remaining_role_candidates.json'):
        hashes[str(args.previous/name)] = hashlib.sha256((args.previous/name).read_bytes()).hexdigest()
        shutil.copyfile(args.previous/name, out/name)
    write(out/'summary.json', dict(scan=p['job']['label'], members=members, paired_qualification=paired,
          joint_points=sum(r['points'] for r in members), production_changed=False, goal_complete=False))
    write(out/'sources.json', hashes)
    with gzip.open(out/'evidence.json.gz', 'wt') as stream:
        json.dump(evidence, stream, separators=(',', ':'))
    finest = [r for r in centers if r['step_s'] == min(steps)]
    (out/'README.md').write_text(f'''# Two recovered satellite families in one position fit

Two independently qualified curves in **AUTO-20cb1fdb**, containing **58 original GLRT points**, have now been fitted together from the regional-box center. Both joint-fit arms pass all recorded RF and numerical checks: **{paired['joint']}**. The factorized comparison passes both arms: **{paired['factorized']}**. Qualification is conditional on the existing graph, causal candidate shortlist and incumbent associations; it is not a calibrated probability that the identities are correct or a production promotion.

{table(members, ['norad','component','points'])}

## Why a joint likelihood is necessary

The two curves were tested individually in shifted batches three and four. Their individual point gains cannot be added to infer a combined position improvement. Both predictions depend on the same uncertain receiver calibration. The new likelihood stacks the observations and uses

`B = blockdiag(N1, N2) + H Sigma H.T`,

where `Sigma` is the receiver/coefficient posterior conditioned on incumbent evidence, `H` stacks each curve's receiver design, and each `N` contains measurement noise and the existing 300 Hz track-bias prior. Independent physical orbital modes add `blockdiag(U1 U1.T, U2 U2.T)`. The implementation integrates over the Cartesian product of the two causal phase priors, with six Gaussian orbital-mode coefficients integrated analytically. It retains the off-diagonal receiver covariance once. The factorized comparison discards that cross-family covariance by summing the two marginal likelihoods. Neither target updates the stored receiver calibration coefficients.

The numerical kernel is checked against a direct full Gaussian covariance oracle, including posterior orbital coefficients, phase marginals, family-order invariance, visibility mass and the independent-family limit. A further regression test verifies that single-phase physical replay preserves exactly three orbital modes and reproduces the corresponding full-grid geometry.

## Local phase-grid probe

At the saved RF incumbent in each c arm, the probe evaluates the center and four offsets of 100 m. These are gradients of the **new evidence contribution**, not the total localization loss. The original phase reference stays fixed. No GPS enters the stencil, candidate selection or fitting.

{table(finest, ['arm','largest_cross_correlation','difference','seconds','phase_pairs'])}

`difference` is joint minus factorized negative-twice-log density. The largest whitened cross-family correlation is approximately 0.006 for c=0 and 0.016 for fitted-c. Coupling is small for this pair; this does not prove it is small for other pairs. A 0.25 s phase grid distorts the local gradient. The 0.0625 and 0.03125 s results agree much more closely.

![Phase-grid gradients](figures/phase_gradient.png)

## Matched position experiment

All fits start at `[0,0]` in the existing 25 by 25 km regional box centered at 37.906, -122.545. Control, factorized addition and joint addition use the same incumbent observations, causal TLEs, physical priors, bounds and five phase-refresh rounds. The initial L-BFGS-B budget is 48 iterations / nominal 240 function evaluations per round. Both additions report abnormal optimizer termination in fitted-c while passing the physical, ownership and phase checks; their original results remain withheld. A numerical-only selector therefore reruns all six fits, including both controls, with Powell (48 iterations / 240 evaluations per round). It does not select using GPS error. Both c arms use both added curves. Every worker has a 600-second wall-clock cap. The phase-integration spacing is 0.0625 s; endpoint local audits compare it with 0.03125 and 0.015625 s. All twelve fits and final audits completed. The table shows the matched Powell experiment; the CSV retains both experiments.

{table(rows, ['method','arm','error_km','reviewed_points','associated_percent','RF_qualified_arm','seconds'])}

The denominator is {total_glrt} original GLRT winners. Joint inclusion raises reviewed association from 3,632/5,348 (67.91%) to 3,690/5,348 (69.00%), with no lost incumbent points. In the matched Powell comparison, error decreases from 0.493 to 0.413 km for c=0 and from 0.477 to 0.398 km for fitted-c. The joint and factorized endpoints differ by less than 0.1 m here. Joint fitting takes about 125–132 seconds versus 53–54 seconds for the factorized fits in this execution; these are single-case process timings, not an embedded performance benchmark.

![Matched position errors](figures/position_comparison.png)

Position error uses 37.849061591561885, -122.48574968092912 **only in report generation**. Raw control and addition objectives use different observations and cannot establish better localization. The same-evidence joint and factorized contributions are recorded separately in [position_comparison.csv](position_comparison.csv). The likelihood definitions differ, so their normalization difference is not a position-quality score.

Audits rebuild each endpoint, replay every incumbent family's physical orbit, preserve incumbent observation ownership, and test target RMS, constant bias, alias, elevation and residual mean/slope/curvature/step/correlation. The joint target is checked at both its discrete joint MAP and a local continuously refined phase pair. Receiver coefficients remain unchanged by target evaluation. Grid boundary mass, optimizer completion, phase refresh and local score/gradient resolution must also pass. Unscored post-fit extensions are excluded from the reviewed membership and must not enter the fitted observations. Both c arms and both matched controls must qualify. [All check results](qualification.csv) and full residual diagnostics are archived.

![Joint target curves and residuals](figures/joint_curves.png)

## Failures, provenance and remaining scope

The first likelihood-probe attempt failed because an exclusive-write helper was asked to overwrite its progress file; the successful attempt uses separate point receipts. The first joint residual audit failed because the single-phase view retained the entire phase-grid mode bank. Its source and failed terminal receipts are preserved; the corrected view keeps exactly three modes and has a physical-geometry regression test. Neither failure is counted as scientific rejection or silently overwritten. The final audit reuses the completed position fits without changing their observations, endpoint or objective.

This pair was selected because it was the only scan with two distinct, individually qualified, broader-competition-checked new families in shifted batches three and four. It was not selected for GPS improvement. The scan remains a studied same-site case. This experiment establishes one checked joint-inclusion result, not cohort performance, exhaustive candidate search, transfer to another location, or recovery of all unassociated tracks.

[Shifted batch five](../2026_10_30_shifted_annotation_batch5/README.md) adds 32 complete annotations and 19 inclusion trials, with 15 individually qualified curves / 399 points (14 fast curves / 372 points; one adaptive curve / 27 points). Ten qualified trials improve fitted-c error and five worsen it. Six numerical-only retries preserve their original failures and use matched controls. These individual trials are not summed into joint scan accuracy. The two-family points here overlap earlier qualified recoveries and are not 58 additional inventory points.

The carried-forward ledger retains all previous ambiguity, native-IQ rejections and candidate-competition withholdings, adding this pair's joint status. **274 shifted-origin assessments and 821 older-role reassessments remain; the queues overlap.** Production is unchanged. Next, assess additional same-scan qualified families with the same joint checks, continue the inventory, and evaluate a frozen combined policy on a matched cohort before production promotion.
''')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('study', 'previous', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
