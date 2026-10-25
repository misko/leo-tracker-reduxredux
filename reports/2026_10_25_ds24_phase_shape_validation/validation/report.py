"""Geographic report of an RF-sealed fixed panel; never imports fit code.

Freeze this source before new geographic reads. Run only after coordinator/RF
audit readiness; all terminal, binding and original-gate prerequisites fail shut.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = (37.849061591561885, -122.48574968092912)
ARMS = ('c0', 'fitted_c')
VARIANTS = ('baseline', 'primary_policy', 'matched_cold_baseline', 'raw_candidate')
COLORS = dict(baseline='#222222', primary_policy='#d55e00', matched_cold_baseline='#0072b2', raw_candidate='#009e73')
LABELS = dict(baseline='Fresh reference', primary_policy='Frozen RX1 policy',
    matched_cold_baseline='Matched cold baseline (diagnostic)', raw_candidate='Raw RX1 (diagnostic)')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())


def write_new(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream: json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')


def distance(latlon):
    """Identical 6371km-radius haversine used in the preceding receiver report."""
    if len(latlon) != 2 or not all(math.isfinite(float(x)) for x in latlon): raise ValueError('invalid endpoint')
    p, q = [tuple(map(math.radians, pair)) for pair in (latlon, SITE)]
    a = math.sin((p[0]-q[0])/2)**2 + math.cos(p[0])*math.cos(q[0])*math.sin((p[1]-q[1])/2)**2
    return 12742 * math.asin(math.sqrt(min(1., max(0., a))))


def freeze(root=ROOT):
    files = {str(root / name):sha(root / name) for name in ('report.py', 'test_report.py')}
    write_new(root / 'evaluator_freeze.json', dict(source_sha256=files, evaluation_only_site_latlon=SITE,
        earth_diameter_km=12742, primary='RF-paired adoption else exact qualified fresh baseline',
        variants=VARIANTS, missing='retained in selected denominator; errors null, never zero/imputed/replaced',
        raw_unqualified_outcomes='diagnostic only, never a geographic selection input',
        ECDF_denominator='all selected cases, including unavailable errors',
        error_change_tie_km=1e-6, no_geographic_read_before_RF_seal=True))


def authorize(root, seal_path):
    # Only evaluator sources, terminal metadata and hashes are read here. No
    # endpoint JSON is parsed until every RF prerequisite has been verified.
    frozen = read(root / 'evaluator_freeze.json')
    if frozen['evaluation_only_site_latlon'] != list(SITE): raise ValueError('evaluation site changed')
    for path, digest in frozen['source_sha256'].items():
        if sha(path) != digest: raise ValueError('evaluator changed after freeze: ' + path)
    seal = read(seal_path)
    for key in ('all_selected_terminal', 'protocol_immutable', 'original_gates_replayed', 'bindings_audited'):
        if seal.get(key) is not True: raise ValueError('RF prerequisite absent: ' + key)
    if sha(root / 'protocol.json') != seal['protocol_sha256']: raise ValueError('RF protocol changed')
    files = {str((root / path).resolve()) if not Path(path).is_absolute() else str(Path(path).resolve()):digest
        for path, digest in seal['files'].items()}
    for path, digest in files.items():
        if sha(path) != digest.removeprefix('sha256:'): raise ValueError('RF-sealed artifact changed: ' + path)
    def bound(path):
        if str(path.resolve()) not in files: raise ValueError('required RF artifact is unsealed: ' + str(path))
        return read(path)
    protocol = read(root / 'protocol.json')
    cases = protocol['cases']
    if len(cases) != len(set(cases)): raise ValueError('duplicate selected case')
    execution = bound(root / 'execution.json')
    if not execution.get('all_terminal'): raise ValueError('nonterminal execution')
    if {row['case'] for row in execution['rows']} != set(cases) or len(execution['rows']) != len(cases):
        raise ValueError('terminal denominator changed')
    if set(seal['per_case']) != set(cases): raise ValueError('RF case audit denominator changed')
    for case, audit in seal['per_case'].items():
        for key in ('baseline_available', 'baseline_paired_valid', 'comparison_available'):
            if not isinstance(audit.get(key), bool): raise ValueError('missing case RF audit: ' + case + '/' + key)
    return protocol, seal, files, execution


def maybe_bound(root, files, relative):
    path = (root / relative).resolve()
    return read(path) if str(path) in files else None


def postfit_metrics(coverage, baseline_coverage):
    if coverage is None: return dict(postfit_unique_ids=None, postfit_percent=None,
        lost_baseline_postfit_IDs=None, lost_baseline_postfit_count=None)
    ids = coverage['accepted_observation_ids']
    if len(ids) != len(set(ids)) or len(ids) != coverage['associated']: raise ValueError('postfit count/IDs disagree')
    total = coverage['total_GLRT']
    if not 0 <= len(ids) <= total: raise ValueError('invalid postfit denominator')
    baseline_ids = set(baseline_coverage['accepted_observation_ids']) if baseline_coverage else None
    lost = sorted(baseline_ids - set(ids)) if baseline_ids is not None else None
    return dict(postfit_unique_ids=len(ids), postfit_percent=100 * len(ids)/total if total else None,
        lost_baseline_postfit_IDs=lost, lost_baseline_postfit_count=len(lost) if lost is not None else None)


def case_rows(root, case, audit, files, execution):
    comparison = maybe_bound(root, files, Path(case) / 'comparison.json') if audit['comparison_available'] else None
    if audit['comparison_available'] and (comparison is None or comparison.get('status') != 'complete'):
        raise ValueError('audited comparison unavailable: ' + case)
    reference = maybe_bound(root, files, Path('family_cavity/position') / (case + '.json'))
    base = reference.get('policy_arms', {}) if reference and reference.get('status') == 'complete' else {}
    if comparison:
        if comparison.get('GPS_or_error_used') is not False: raise ValueError('comparison used geography')
        if comparison.get('protocol_sha256') != sha(root / 'protocol.json'): raise ValueError('comparison protocol changed')
        if base and comparison['baseline'] != base: raise ValueError('reference/comparison baseline mismatch')
        base = comparison['baseline']
    if audit['baseline_available'] and not all(arm in base for arm in ARMS): raise ValueError('audited baseline missing')
    usable_base = audit['baseline_available'] and audit['baseline_paired_valid']
    adopted = bool(comparison['adopted']) if comparison else False
    candidate_valid = bool(comparison['results']['rx1_rf50']['paired_valid']) if comparison else False
    if adopted != candidate_valid: raise ValueError('frozen paired adoption mismatch')
    if comparison and comparison['policy_source'] != ('rx1_rf50' if adopted else 'baseline'):
        raise ValueError('frozen policy source mismatch')
    likelihood = comparison['likelihood_membership'] if comparison else audit.get('likelihood_membership')
    if likelihood:
        if likelihood['union_unique'] != likelihood['curved_unique'] + likelihood['predictive_unique']:
            raise ValueError('likelihood counts are not disjoint native ownership')
        if not 0 <= likelihood['union_unique'] <= likelihood['total_GLRT']: raise ValueError('invalid likelihood denominator')
    rows = []
    for arm in ARMS:
        rawbase = base.get(arm)
        baseline = rawbase if usable_base else None
        result_arms = comparison['results'] if comparison else {}
        trial = result_arms.get('rx1_rf50', {}).get('arms', {}).get(arm)
        cold = result_arms.get('matched_cold_baseline', {}).get('arms', {}).get(arm)
        if trial is None: trial = maybe_bound(root, files, Path(case) / ('rx1_rf50_' + arm + '.json'))
        if cold is None: cold = maybe_bound(root, files, Path(case) / ('matched_cold_baseline_' + arm + '.json'))
        policy = trial if adopted else baseline
        if adopted and policy is None: raise ValueError('adopted endpoint missing')
        baseline_error = distance(baseline['endpoint_latlon']) if baseline else None
        coverage = comparison.get('coverage', {}) if comparison else {}
        baseline_cov = coverage.get('baseline', {}).get(arm)
        cold_valid = bool(result_arms.get('matched_cold_baseline', {}).get('paired_valid', False))
        methods = [('baseline', baseline, bool(baseline), 'baseline'),
            ('primary_policy', policy, candidate_valid if adopted else bool(baseline), 'rx1_rf50' if adopted else 'baseline'),
            ('matched_cold_baseline', cold, cold_valid, 'matched_cold_baseline'),
            ('raw_candidate', trial, candidate_valid, 'rx1_rf50')]
        for variant, fit, qualified, source in methods:
            row = dict(case=case, arm=arm, variant=variant, case_status=execution['status'],
                adopted=adopted, policy_source='rx1_rf50' if adopted else 'baseline', source=source,
                diagnostic=variant in ('matched_cold_baseline', 'raw_candidate'), qualified=qualified,
                endpoint_available=fit is not None, baseline_available=usable_base,
                error_km=None, baseline_error_km=baseline_error, error_change_km=None,
                lat=None, lon=None, RMS_hz=None, RMS_change_hz=None, negative_twice_ELBO=None, objective_change=None,
                final_phase_change_s=None, case_execution_seconds=execution.get('seconds'),
                comparison_seconds=comparison.get('seconds') if comparison else None,
                unavailable_reason=None if fit else execution.get('error', execution.get('reason', 'no qualified/sealed endpoint')))
            if fit:
                latlon = fit['endpoint_latlon']; error = distance(latlon)
                row.update(error_km=error, error_change_km=error-baseline_error if baseline_error is not None else None,
                    lat=latlon[0], lon=latlon[1], RMS_hz=fit.get('RMS_hz'), negative_twice_ELBO=fit.get('negative_twice_elbo'),
                    final_phase_change_s=fit.get('final_phase_change_s'))
                if rawbase:
                    if fit.get('RMS_hz') is not None and rawbase.get('RMS_hz') is not None:
                        row['RMS_change_hz'] = fit['RMS_hz'] - rawbase['RMS_hz']
                    if fit.get('negative_twice_elbo') is not None and rawbase.get('negative_twice_elbo') is not None:
                        row['objective_change'] = fit['negative_twice_elbo'] - rawbase['negative_twice_elbo']
                if likelihood and fit.get('active_points') != likelihood['curved_unique']:
                    raise ValueError('reported curved likelihood count mismatch')
            row.update({name:likelihood.get(key) if likelihood else None for name, key in (
                ('likelihood_curved_unique','curved_unique'), ('likelihood_predictive_unique','predictive_unique'),
                ('likelihood_union_unique','union_unique'), ('total_GLRT_unique','total_GLRT'),
                ('likelihood_union_ids_sha256','union_ids_sha256'))})
            row['likelihood_coverage_percent'] = 100*likelihood['union_unique']/likelihood['total_GLRT'] if likelihood and likelihood['total_GLRT'] else None
            cov = coverage.get(source, {}).get(arm) if fit else None
            row.update(postfit_metrics(cov, baseline_cov))
            if comparison and source == 'rx1_rf50' and row['lost_baseline_postfit_IDs'] != comparison['lost_baseline_postfit_IDs'][arm]:
                raise ValueError('saved postfit loss does not replay')
            if variant == 'primary_policy' and not adopted and baseline:
                # Exact fallback, not a refit/reselection from diagnostic arms.
                if fit is not baseline or row['error_change_km'] != 0 or row['objective_change'] != 0 or row['RMS_change_hz'] != 0:
                    raise ValueError('primary fallback differs from the exact baseline')
            rows.append(row)
    return rows


def statistics(values):
    import numpy as np
    values = np.asarray([value for value in values if value is not None], float)
    if not len(values): return dict(n_available=0, mean=None, median=None, p95=None, maximum=None)
    return dict(n_available=len(values), mean=float(values.mean()), median=float(np.median(values)),
        p95=float(np.percentile(values, 95)), maximum=float(values.max()))


def summaries(rows, cases):
    out = []
    for arm in ARMS:
        for variant in VARIANTS:
            chosen = [row for row in rows if row['arm'] == arm and row['variant'] == variant]
            if {row['case'] for row in chosen} != set(cases) or len(chosen) != len(cases): raise ValueError('report denominator changed')
            changes = [row['error_change_km'] for row in chosen if row['error_change_km'] is not None]
            out.append(dict(arm=arm, variant=variant, selected_cases=len(cases),
                qualified_endpoints=sum(row['qualified'] for row in chosen),
                unavailable_endpoints=sum(row['error_km'] is None for row in chosen),
                unqualified_raw_endpoints=sum(row['error_km'] is not None and not row['qualified'] for row in chosen),
                errors_km=statistics([row['error_km'] for row in chosen]),
                paired_error_changes_km=statistics(changes),
                paired_available_cases=[row['case'] for row in chosen if row['error_change_km'] is not None],
                improved=sum(value < -1e-6 for value in changes), worsened=sum(value > 1e-6 for value in changes),
                tied=sum(abs(value) <= 1e-6 for value in changes),
                RMS_changes_hz=statistics([row['RMS_change_hz'] for row in chosen]),
                objective_changes=statistics([row['objective_change'] for row in chosen])))
    return out


def ecdf(values, selected_count):
    ordered = sorted(value for value in values if value is not None)
    return ordered, [100 * (index+1)/selected_count for index in range(len(ordered))]


def plot(rows, cases, out):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), constrained_layout=True)
    for ax, arm in zip(axes, ARMS):
        for variant in VARIANTS:
            chosen = [row for row in rows if row['arm'] == arm and row['variant'] == variant]
            x, y = ecdf([row['error_km'] for row in chosen], len(cases))
            ax.step(x, y, where='post', color=COLORS[variant], ls='--' if variant in ('raw_candidate','matched_cold_baseline') else '-',
                label=f'{LABELS[variant]} ({len(x)}/{len(cases)})')
        ax.set(title=arm, xlabel='Position error (km)', ylabel='Fraction of selected panel (%)', ylim=(0,102)); ax.grid(alpha=.2)
        ax.legend(fontsize=7)
    fig.suptitle('Fixed panel: unavailable cases stay in the ECDF denominator')
    fig.savefig(out / 'error_ecdf.png', dpi=160); plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), constrained_layout=True, sharex=True)
    for ax, arm in zip(axes, ARMS):
        for offset, variant, marker in zip((-.24,-.08,.08,.24), VARIANTS, ('o','s','^','o')):
            chosen = {row['case']:row for row in rows if row['arm'] == arm and row['variant'] == variant}
            for i, case in enumerate(cases):
                row = chosen[case]
                if row['error_km'] is None: continue
                ax.scatter(i+offset, row['error_km'], color=COLORS[variant], marker=marker if row['qualified'] else 'x',
                    s=35, label=LABELS[variant] if i == next((j for j,c in enumerate(cases) if chosen[c]['error_km'] is not None), -1) else None)
            for i, case in enumerate(cases):
                row = chosen[case]
                if variant == 'primary_policy' and row['baseline_error_km'] is not None and row['error_km'] is not None:
                    ax.plot([i-.24,i-.08], [row['baseline_error_km'],row['error_km']], color=COLORS[variant], alpha=.5)
        ax.set(title=arm, ylabel='Position error (km)'); ax.grid(axis='y', alpha=.2); ax.legend(fontsize=8)
    axes[-1].set_xticks(range(len(cases)), cases, rotation=45, ha='right')
    fig.suptitle('Every selected case; × marks unqualified raw diagnostics, absent points are unavailable')
    fig.savefig(out / 'paired_errors.png', dpi=160); plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for j, arm in enumerate(ARMS):
        for k, (key, title) in enumerate((('RMS_change_hz','Curved residual RMS change (Hz)'),('objective_change','Negative twice ELBO change'))):
            ax = axes[k,j]
            for variant, marker in (('raw_candidate','o'),('matched_cold_baseline','^')):
                chosen = [row for row in rows if row['arm'] == arm and row['variant'] == variant
                    and row[key] is not None and row['error_change_km'] is not None]
                for qualified in (True, False):
                    subset = [row for row in chosen if row['qualified'] == qualified]
                    ax.scatter([row[key] for row in subset], [1000*row['error_change_km'] for row in subset],
                        color=COLORS[variant], marker=marker if qualified else 'x',
                        label=LABELS[variant] + ('; unqualified' if not qualified else ''), alpha=.8)
            ax.axhline(0, color='black', lw=.6); ax.axvline(0, color='black', lw=.6)
            ax.set(title=arm, xlabel=title, ylabel='Position-error change (m)'); ax.grid(alpha=.2); ax.legend(fontsize=7)
    fig.suptitle('RF fit and position accuracy are separate; same frozen observations within a case')
    fig.savefig(out / 'RF_vs_position.png', dpi=160); plt.close(fig)


def main(root=ROOT, seal_path=None):
    protocol, seal, files, execution = authorize(root, seal_path or root / 'RF_seal.json')
    cases = protocol['cases']; statuses = {row['case']:row for row in execution['rows']}
    rows = [row for case in cases for row in case_rows(root, case, seal['per_case'][case], files, statuses[case])]
    summary = summaries(rows, cases)
    out = root / 'report'; out.mkdir(exist_ok=False)
    with (out / 'positions.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    adopted = sorted({row['case'] for row in rows if row['adopted']})
    metadata = dict(cases=cases, selected_count=len(cases), arms=ARMS, evaluation_only_site_latlon=SITE,
        summaries=summary, adopted_cases=adopted, adopted_count=len(adopted),
        fresh_baseline_unavailable=[case for case in cases if not (seal['per_case'][case]['baseline_available'] and seal['per_case'][case]['baseline_paired_valid'])],
        case_statuses=statuses, deployment_evidence=seal.get('deployment_evidence'),
        policy='frozen paired original gates only, else exact qualified fresh baseline; no geographic selection',
        denominator='all selected cases, missing errors null; reported means/percentiles conditional on availability',
        raw_diagnostics='raw candidate and matched cold include unqualified endpoints; never select primary policy',
        geographic_scope='later same-deployment panel under stated site assumption; not unseen-site transfer',
        RF_seal_sha256=sha(seal_path or root / 'RF_seal.json'), evaluator_freeze_sha256=sha(root / 'evaluator_freeze.json'),
        protocol_sha256=seal['protocol_sha256'], evaluator_source_sha256=sha(__file__), no_new_position_fit_or_RF=True)
    write_new(out / 'summary.json', metadata)
    plot(rows, cases, out)
    lines = ['# Frozen RX1 later-panel geographic evaluation', '',
        f'{len(cases)} selected cases; {len(adopted)} frozen paired candidate adoptions. Every selected case remains in the table and ECDF denominator.', '',
        'Primary policy uses the original paired RF/phase decision; failed trials fall back to the exact qualified freshly reconstructed baseline. Unavailable baselines have missing errors, never zero error or a replacement case. Raw RX1 and matched cold results are diagnostic and can be unqualified.', '',
        '| Arm | Variant | Available / selected | Qualified | Mean error, km | Median, km | P95, km | Improved / worsened / tied paired |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    fmt = lambda x:'missing' if x is None else f'{x:.6f}'
    for item in summary:
        s = item['errors_km']
        lines.append(f"| {item['arm']} | {item['variant']} | {s['n_available']} / {len(cases)} | {item['qualified_endpoints']} | {fmt(s['mean'])} | {fmt(s['median'])} | {fmt(s['p95'])} | {item['improved']} / {item['worsened']} / {item['tied']} |")
    lines += ['', 'Means and percentiles use available endpoints only; paired changes use only available reference/result pairs. Missing cases remain explicit in the selected denominator. The full table separates true likelihood membership from postfit acceptance and retains lost baseline IDs; postfit losses are reported rather than introduced as a new policy gate.', '',
        'Frequency RMS and objective changes are reported separately from position errors. The known site is an evaluation-only assumption for this deployment; later same-site outcomes do not establish accuracy at new locations. Candidate priors, adoption and panel membership were frozen before this evaluation.', '',
        '![Error ECDF](error_ecdf.png)', '', '![Every case](paired_errors.png)', '', '![RF and position](RF_vs_position.png)', '',
        'See [full table](positions.csv) and [summary/provenance](summary.json).']
    (out / 'FINDINGS.md').write_text('\n'.join(lines) + '\n')
    write_new(out / 'seal.json', dict(files={str(path):sha(path) for path in sorted(out.iterdir()) if path.is_file()},
        RF_seal_sha256=metadata['RF_seal_sha256'], evaluator_freeze_sha256=metadata['evaluator_freeze_sha256']))
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--rf-seal', type=Path)
    args = parser.parse_args()
    freeze() if args.freeze else main(seal_path=args.rf_seal)
