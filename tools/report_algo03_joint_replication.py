"""Report a terminal ALGO03 joint-family replication without changing its policy."""
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
    def load(path):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        evidence[str(path)] = read(path)
        return evidence[str(path)]
    def verify(record):
        for path, digest in record.get('source_hashes', {}).items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
                raise ValueError('source changed: '+path)
    def csvout(name, rows):
        with (out/name).open('x') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(k for r in rows for k in r)), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
    def save(fig, name):
        fig.savefig(out/'figures'/name, dpi=145)
        plt.close(fig)

    release = load(Path('reports/ALGO03/releases/2026-10-30-r1/manifest.json'))
    for path, digest in release['sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise ValueError('frozen ALGO03 source changed: '+path)
    root = args.study/'two-new-family-replication-v1'
    frozen = load(root/'protocol.json')
    verify(frozen)
    if load(root/'probe-terminal.json')['status'] != 'complete':
        raise ValueError('probe incomplete')
    probe = load(root/'probe/result.json')
    verify(load(root/'probe/protocol.json'))
    if not (probe['all_individual_replays_verified'] and probe['receiver_calibration_unchanged']):
        raise ValueError('unverified probe')
    folder = root/'initial'
    verify(load(folder/'protocol.json'))
    verify(load(folder/'audit-protocol.json'))
    for name in ('execution.json', 'audit-execution.json'):
        rows = load(folder/name)
        if len(rows) != 6 or any(r['status'] != 'complete' for r in rows):
            raise ValueError('matched fit/audit execution incomplete')
    members = []
    for selected in frozen['selected']:
        current = load(Path(selected['current_validation'])/'result.json')
        load(Path(selected['current_validation'])/'protocol.json')
        old = load(Path(selected['trial'])/'protocol.json')
        for entry in old['targets']:
            if entry['norad'] != current['annotation']['norad']:
                raise ValueError('current identity and fitted identity differ')
            members.append(dict(track_id=selected['track_id'], norad=entry['norad'], component=entry['component'],
                points=entry['points'], minimum_identity_margin=current['annotation']['minimum_margin']))
    job = frozen['selected'][0]['job']
    inv = load(args.study/'all-large-track-recovery'/job['job_id']/'inventory.json')
    total = inv['summary'][0]['total_GLRT']
    results, audits, comparisons, checks, residuals = {}, {}, [], [], []
    for method in ('control', 'factorized', 'joint'):
        for arm in ('c0', 'fitted_c'):
            case = folder/(method+'-'+arm)
            verify(load(case/'protocol.json'))
            r = load(case/'result.json')
            a = load(case/('audit-v2.json' if method == 'joint' else 'audit.json'))
            verify(a)
            results[method, arm], audits[method, arm] = r, a
            comparisons.append(dict(method=method, arm=arm, position_error_km=error(r),
                associated_points=len(a['reviewed_ids']), associated_percent=100*len(a['reviewed_ids'])/total,
                RF_qualified_arm=a['RF_qualified_arm'], seconds=r['seconds'],
                incumbent_objective=r['incumbent_objective'], joint_evidence=r['joint_evidence'],
                factorized_evidence=r['factorized_evidence'],
                east_km=r['endpoint_east_north_km'][0], north_km=r['endpoint_east_north_km'][1]))
            checks += [dict(method=method, arm=arm, check=key, passed=value) for key, value in a['checks'].items()]
            if method == 'joint':
                for k, d in enumerate(a['continuous_target']['diagnostics']):
                    residuals.append(dict(arm=arm, norad=d['norad'], component=d['component'],
                        RMS_hz=d['profile_RMS_hz'], bias_hz=d['profile_bias_hz'],
                        phase_s=a['continuous_target']['phases_s'][k], **d['noise']))
    qualified = {m: all(audits[m, a]['RF_qualified_arm'] and audits['control', a]['RF_qualified_arm']
                        for a in ('c0', 'fitted_c')) for m in ('factorized', 'joint')}
    for name, rows in [('members.csv', members), ('position_comparison.csv', comparisons),
                       ('qualification.csv', checks), ('joint_residuals.csv', residuals)]:
        csvout(name, rows)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout='constrained')
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        group = [r for r in comparisons if r['arm'] == arm]
        ax.bar([r['method'] for r in group], [r['position_error_km'] for r in group],
               color=['#999', '#e69f00', '#0072b2'])
        ax.set(title=arm, ylabel='Evaluation position error (km)')
        ax.grid(axis='y', alpha=.2)
    save(fig, 'position_comparison.png')
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), layout='constrained')
    for column, member in enumerate(members):
        for arm in ('c0', 'fitted_c'):
            d = audits['joint', arm]['continuous_target']['diagnostics'][column]
            if arm == 'c0':
                axes[0, column].plot(d['times_s'], np.array(d['CFO_hz'])/1000, '.', color='#777', label='Target GLRT')
            axes[0, column].plot(d['times_s'], (np.array(d['prediction_CFO_hz'])+d['profile_bias_hz'])/1000, label=arm+' prediction')
            axes[1, column].plot(d['times_s'], np.array(d['raw_residual_hz'])-d['profile_bias_hz'], '.-', lw=.7, label=arm)
        axes[0, column].set(title=str(member['norad'])+' / '+member['component'].split('-RF')[0], ylabel='CFO (kHz)')
        axes[1, column].set(ylabel='Residual after constant bias (Hz)')
        axes[1, column].axhline(0, color='k', lw=.5)
        for ax in axes[:, column]:
            ax.set_xlabel('Scan time (s)')
            ax.grid(alpha=.2)
            ax.legend(fontsize=7)
    save(fig, 'joint_curves.png')
    cov = [dict(arm=r['arm'], largest_cross_correlation=r['largest_cross_correlation'],
                joint_minus_factorized=r['joint_minus_factorized']) for r in probe['rows'] if r['offset_km'] == [0., 0.]]
    csvout('shared_covariance.csv', cov)

    ledger_path = args.previous/'annotation_ledger.csv'
    hashes[str(ledger_path)] = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    ledger = list(csv.DictReader(ledger_path.open()))
    tids = {m['track_id'] for m in members}
    if not tids <= {r['track_id'] for r in ledger}:
        raise ValueError('targets missing from full ledger')
    for r in ledger:
        if r['track_id'] in tids:
            r.update(two_family_joint_source=str(folder), two_family_joint_state=(
                'RF_verified_joint_research_candidate' if qualified['joint'] else 'joint_inclusion_withheld'))
    csvout('annotation_ledger.csv', ledger)
    for name in ('remaining_shifted_candidates.json', 'remaining_role_candidates.json'):
        load(args.previous/name)
        shutil.copyfile(args.previous/name, out/name)
    batch = load(args.previous/'summary.json')
    summary = dict(scan=job['label'], release=release['release_id'], paired_qualification=qualified,
                   points=sum(r['points'] for r in members), GLRT_total=total,
                   batch=batch, production_changed=False, goal_complete=False)
    write(out/'summary.json', summary)
    write(out/'sources.json', hashes)
    with gzip.open(out/'evidence.json.gz', 'wt') as stream:
        json.dump(evidence, stream, separators=(',', ':'))
    (out/'README.md').write_text(f'''# ALGO03: a second joint-family inclusion and inventory batch six

The next eligible pair in the frozen ledger, **{job['label']}**, passes the ALGO03 joint-inclusion checks in both c arms: **{qualified['joint']}**. It adds **{sum(m['points'] for m in members)} original points** without dropping incumbent points. This is a replication on a second studied same-site scan, not a full-cohort result. The frozen [ALGO03 release](../ALGO03/README.md), its source hashes and production service are unchanged.

## Selection and causal identities

{table(members, ['norad','component','points','minimum_identity_margin'])}

These two curves were individually qualified in shifted batches one and five. Both retain identity support after candidate-cap-twelve causal competition. Among native new-family trials with current `RF_verified_research_candidate` status and a supported predictive recheck, they form the only additional untested same-scan pair of distinct families in the input ledger after excluding the previous joint-tested scan. This eligibility rule does not exhaust older qualification labels or shared-family routes. Selection used qualification, immutable IDs and common scan ownership, not GPS error. Original graph membership, measurements, aliases and priors remain unchanged. The catalogue shortlist remains bounded and the three randomized physical held sets overlap; identity margins are not correctness probabilities.

The first curve is RX1 CH4 and the second is RX2 CH2, so this case exercises cross-receiver prediction. In contrast, the first joint example used two RX1 channels. Current broader-competition receipts, original individual trials and the source ledger are hashed in the frozen selection protocol.

## Matched position results

{table(comparisons, ['method','arm','position_error_km','associated_points','associated_percent','RF_qualified_arm','seconds'])}

![Position comparison](figures/position_comparison.png)

The denominator is **{total} original GLRT winners**. Association changes from 2,409/3,538 (68.09%) to 2,472/3,538 (69.87%). Joint inclusion improves c=0 error from 1.021 to 0.971 km and fitted-c from 1.053 to 0.974 km. The remaining error is still close to one kilometer. The factorized comparison also qualifies, with slightly different endpoints. No endpoint was chosen using its evaluation error.

All six fits start at the center of the existing 25 × 25 km region centered at 37.906, -122.545. Both c arms use the same observations, causal candidates, priors and budgets. Five phase-refresh rounds use L-BFGS-B, at most 48 iterations and nominal 240 evaluations per round, with a 600-second cap per process. All six optimizers and audits complete; no Powell retry is needed in this replication. GPS 37.849061591561885, -122.48574968092912 is accessed only by reporting.

The joint likelihood retains receiver cross-covariance once, analytically integrates independent physical orbital modes and sums over the two causal phase grids. The factorized comparison sums separate family likelihoods with the same priors. Neither target updates the stored receiver calibration at fixed position. Likelihood scores and incumbent fit effects are archived separately from position error; better in-sample fit is not used as a localization claim.

## Shared uncertainty and residual checks

{table(cov, ['arm','largest_cross_correlation','joint_minus_factorized'])}

The whitened cross-family correlation is about 0.075–0.087, larger than 0.006–0.016 in the first pair. This is a measured property of these two conditional covariance matrices, not a universal receiver correction. Joint and factorized fits remain close in this case. The observed recovery benefit is primarily the additional evidence, not a large correction caused by covariance coupling.

{table(residuals, ['arm','norad','RMS_hz','bias_hz','phase_s','mean_z','slope_z','quadratic_bic_gain','maximum_step_z','lag1_acf'])}

![Recovered curves and residuals](figures/joint_curves.png)

Both targets pass the unchanged residual structure, RMS, constant bias, alias and horizon checks at grid and continuously refined joint phases. Every incumbent family's physical orbit is replayed. Old ownership, numerical convergence, phase refresh, boundary mass and local integration agreement must pass in both arms. The 0.0625 s grid is checked against 0.03125 and 0.015625 s at the endpoint and four 25 m offsets. All individual family likelihoods replay in the joint geometry probe, and target evaluation leaves the receiver coefficients unchanged. [Check results](qualification.csv), exact diagnostics, source hashes and terminal receipts are retained.

## Inventory progress and limits

[Shifted batch six](../2026_10_30_shifted_annotation_batch6/README.md) assesses **{batch['annotations']}** more curves. Its initial annotation outcomes are **{batch['annotation_states']}**. Every initially supported identity receives broader causal competition before inclusion. It produces **{batch['qualified_curves']} qualified curves / {batch['qualified_points']} points** in separate matched trials; these gains cannot be summed into simultaneous scan accuracy. The batch contains {batch['capture_modes']} acquisitions, established from capture provenance rather than compatibility labels. The batch report preserves every accepted and rejected trial, both c arms and figures.

The two jointly tested scans are selected development/replication examples, not a representative error distribution. The 63 points here overlap earlier individual recoveries and must not be added again to inventory totals. The complete all-large-track objective remains unfinished: **{batch['remaining_shifted']} shifted-origin assessments and {batch['remaining_older_role']} older-role reassessments remain**, with overlapping queues. The updated ledger preserves the first joint result and all previous ambiguity, native-IQ and competition withholdings.

Next, return to the largest pending older-role curves (about 65 points at the current queue head), apply predictive-only annotation and broader competition, and test additional mutually consistent recoveries together. Keep ALGO03's frozen settings while collecting cohort evidence; do not tune to these two evaluation positions. Production remains ALGO02.
''')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('study', 'previous', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
