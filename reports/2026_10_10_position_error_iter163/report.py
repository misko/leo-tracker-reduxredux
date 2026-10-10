"""Postseal geography and incremental-cost reporting for symmetric starts."""
import json
from pathlib import Path
import importlib.util

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


OLD=module('report162_for163',HERE.parent/'2026_10_10_position_error_iter162/report.py')
PREFERENCE=module('preference162_for163',HERE.parent/'2026_10_10_position_error_iter162/preference.py')


def preferences(plan,cells):
    """No reference fields: both generations use the unchanged score policy."""
    import hashlib
    controls=[]
    for member in plan['members']:
        for binding in member['controls'].values():
            path=ROOT/binding['raw_path'];data=path.read_bytes()
            if hashlib.sha256(data).hexdigest()!=binding['sha256']:raise ValueError('control changed')
            controls.append(json.loads(data))
    labels=[m['label'] for m in plan['members']]
    baseline=PREFERENCE.preferences(controls,labels)
    published=json.loads((HERE.parent/'2026_10_10_position_error_iter162/PREFERENCES.json').read_text())
    if baseline!=published:raise ValueError('published control preferences differ')
    return dict(candidate=PREFERENCE.preferences(cells,labels),control=baseline)


def summarize(cells,choices,members):
    summary=OLD.summarize(cells,choices['candidate'],members)
    controls={(r['label'],r['arm']):r for r in choices['control']}
    for row in summary['rows']:
        previous=controls[(row['label'],row['arm'])]
        baseline=(row['hypothesis_errors'].get(previous['selected_hypothesis'])
                  if previous['status']=='selected' else None)
        row.update(control_preference=previous,control_error_km=baseline,
            delta_vs_control_km=None if baseline is None or row['selected_error_km'] is None
            else row['selected_error_km']-baseline)
        ordinary=row['hypothesis_errors'][row['arm']]
        row['ordinary_same_arm_error_km']=ordinary
        row['delta_vs_ordinary_same_arm_km']=(None if ordinary is None or row['selected_error_km'] is None
                                             else row['selected_error_km']-ordinary)
    for aggregate in summary['aggregates']:
        rows=[r for r in summary['rows'] if r['arm']==aggregate['arm']
              and (aggregate['dataset']=='pilot' or r['dataset']==aggregate['dataset'])]
        paired=[r for r in rows if r['delta_vs_control_km'] is not None]
        deltas=[r['delta_vs_control_km'] for r in paired]
        tol=OLD.GEOGRAPHIC_TOLERANCE
        aggregate.update(control_paired=OLD.stats(r['control_error_km'] for r in paired),
            candidate_paired=OLD.stats(r['selected_error_km'] for r in paired),
            delta_vs_control=OLD.stats(deltas),
            regressed_vs_control=sum(d>tol for d in deltas),
            improved_vs_control=sum(d < -tol for d in deltas),
            equal_vs_control=sum(abs(d)<=tol for d in deltas),
            control_regression_labels=[r['label'] for r in paired if r['delta_vs_control_km']>tol],
            maximum_control_regression_km=max((d for d in deltas if d>tol),default=0.))
        ordinary_pairs=[r for r in rows if r['delta_vs_ordinary_same_arm_km'] is not None]
        aggregate.update(ordinary_same_arm_paired=OLD.stats(r['ordinary_same_arm_error_km'] for r in ordinary_pairs),
                         delta_vs_ordinary_same_arm=OLD.stats(r['delta_vs_ordinary_same_arm_km'] for r in ordinary_pairs))
    return summary


def markdown(summary):
    def f(v):return 'missing' if v is None else f'{v:.4f}'
    lines=['# Symmetric calibration starts: results','',
        '![Position and held-score preference](comparison.png)','',
        'Both ordinary full-data calibration states supply starts at both fixed position hypotheses. '
        'Each new fit uses the same budget. The lowest qualified training objective, including an '
        'explicitly retained prior control, determines calibration. Only that selected state is scored '
        'on the opposite fold. No held score or reference error chooses a calibration start.', '',
        '| Dataset | Calibration arm | Resolved / members | Evaluated | Control selector mean | Candidate selector mean | Paired change km | Candidate median | p95 | Worst km | Correct preference / denominator |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for a in summary['aggregates']:
        lines.append(f"| {a['dataset']} | {a['arm']} | {a['resolved']} / {a['members']} | {a['evaluable']} | "
            +f"{f(a['control_paired']['mean'])} | {f(a['candidate_paired']['mean'])} | {f(a['delta_vs_control']['mean'])} | "
            +' | '.join(f(a['selected'][k]) for k in ('median','p95','worst'))
            +f" | {a['preference_correct']} / {a['preference_denominator']} |")
    lines+=['','| Dataset | Calibration arm | Ordinary same-arm mean km | Paired candidate change km | Pairs |',
        '|---|---|---:|---:|---:|']
    for a in summary['aggregates']:
        lines.append(f"| {a['dataset']} | {a['arm']} | {f(a['ordinary_same_arm_paired']['mean'])} | "
                     +f"{f(a['delta_vs_ordinary_same_arm']['mean'])} | {a['delta_vs_ordinary_same_arm']['n']} |")
    lines+=['','Ordinary same-arm means compare zero-c selection against the ordinary zero-source position, '
        'and fitted-c selection against the ordinary fitted-source position. '
        'Paired control/candidate means use the same evaluable members; no failures or unresolved '
        'preferences are zero-filled. Geographic ties (1e-9 km) are neutral. Both c arms, full ordinary '
        'hypothesis means, all ties/incomplete counts and every regression label are retained in SUMMARY.json.', '',
        '| Member | Calibration arm | Selected source geometry | Control error km | Candidate error km | Change km | Held NLL difference |',
        '|---|---|---|---:|---:|---:|---:|']
    for r in summary['rows']:
        lines.append(f"| {r['label']} | {r['arm']} | {r['status']} / {r['selected_hypothesis']} | "
            +f"{f(r['control_error_km'])} | {f(r['selected_error_km'])} | {f(r['delta_vs_control_km'])} | {f(r.get('delta_nll'))} |")
    lines+=['','## New work, retained controls and limitations','',
        f"New fits qualified: **{summary['new_qualified']}/192**. Selected calibrations qualified: "
        f"**{summary['qualified']}/96**; retained controls: **{summary['retained_controls']}**. "
        f"Selection-source counts: `{summary['selection_sources']}`. Geographic evaluations: "
        f"{summary['evaluated']}/96, representing twelve unique scans and two positions per scan. "
        'Repeated fixed-position fits are not independent geographic observations.', '',
        f"Incremental member worker time including input reconstruction, control audits, new fits and held scoring: "
        f"{summary['worker_s']:.3f} seconds. Historical iteration-162 time is excluded. No retained control "
        'is counted as a new successful optimization. All attempt failures, control audits and held-score '
        'failures are separate in the raw receipts. The training-only tie rule chooses from candidates '
        'within 1e-6 of the global minimum, then prioritizes control, zero-source and fitted-source starts.', '',
        'The seed pool and geometry hypotheses use full-data inference, including the held observations. '
        'This remains consumed-data conditional development, not independent validation or unbiased '
        'cross-validation. Zero-c projects static c and both RF-time coefficients to zero; fitted-c '
        'retains them. The source pool, all other initial coordinates, candidate positions, observations, '
        'priors and search budgets are matched. Predictive frequency fit and geographic error are '
        'separate reported outcomes. No reference-guided selection, scan-specific tuning or new RF collection.', '',
        'The official 193-member metric, deployed pipeline and reserved outcomes remain unchanged. '
        'The 0.4 km standalone goal remains unmet. [Plan](PLAN.md), [numerical protocol](protocol.json), '
        '[sealed preferences](PREFERENCES.json), [evaluation protocol](evaluation_protocol.json), '
        '[all results](SUMMARY.json), [raw receipts](raw-receipts.tar.gz).','']
    return '\n'.join(lines)


def main():
    import hashlib,tarfile
    import run,evaluation
    freezer=module('freeze163_report',HERE/'freeze.py')
    plan=json.loads((HERE/'protocol.json').read_text());run.BASE.verify(plan,freezer.POLICY)
    from leo.contracts.digests import canonical_digest
    digest=canonical_digest(plan);collection=evaluation.collect(plan,digest,HERE/'results')
    choices=preferences(plan,collection['cells'])
    if choices!=json.loads((HERE/'PREFERENCES.json').read_text()):raise ValueError('sealed preferences changed')
    evaluated=evaluation.evaluate(plan,digest,HERE/'results',json.loads((HERE/'evaluation_protocol.json').read_text()))
    summary=summarize(evaluated['rows'],choices,plan['members'])
    attempts=collection['attempts'];cells=evaluated['rows']
    summary.update(protocol_sha256=digest,cells=cells,attempts=attempts,members=collection['members'],
        raw_sha256=collection['raw_sha256'],new_qualified=sum(a['status']=='qualified' for a in attempts),
        qualified=sum(c['status']=='qualified' for c in cells),evaluated=sum(c['error_km'] is not None for c in cells),
        retained_controls=sum(c.get('control_retained',False) for c in cells),
        selection_sources={s:sum(c.get('selected_source')==s for c in cells) for s in ('control','zero-c','fitted-c')},
        worker_s=sum(m['elapsed_s'] for m in collection['members'].values()))
    (HERE/'SUMMARY.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    OLD.plot(summary,HERE/'comparison.png');(HERE/'README.md').write_text(markdown(summary))
    with tarfile.open(HERE/'raw-receipts.tar.gz','w:gz') as archive:
        for name in sorted(collection['raw_sha256']):archive.add(HERE/'results'/name,arcname=name)
    with tarfile.open(HERE/'raw-receipts.tar.gz','r:gz') as archive:
        actual={m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive.getmembers()}
    if actual!=collection['raw_sha256']:raise ValueError('archive differs')
    names=('README.md','SUMMARY.json','comparison.png','raw-receipts.tar.gz','protocol.json',
           'evaluation_protocol.json','PREFERENCES.json','report.py','evaluation.py')
    (HERE/'REPORT_INTEGRITY.json').write_text(json.dumps({n:evaluation.sha(HERE/n) for n in names},indent=2)+'\n')
    print(json.dumps(dict(new_qualified=summary['new_qualified'],qualified=summary['qualified'],retained=summary['retained_controls'],
        aggregates=summary['aggregates'])))


if __name__=='__main__':main()
