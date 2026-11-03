"""Requirement-level evidence audit for the 2 + 16 scan deliverable.

Completed numerical experiments may contain scientifically negative or failed
fits; those flags must remain. This audit checks scope, accounting, source
binding and artifacts, not satellite truth or global optimality. Missing or
invalid evidence never becomes completion just because a renderer succeeded.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np

from cohort import digest,verify_capture
from freeze_final_settings import read_freeze
from package_report import assets
from refinement import winners
from render_pilot import validate_comparison
from render_position_summary import case_path
from render_positions import validate
from render_report import validate_export
from run_subset_batch import cases

HERE=Path(__file__).resolve().parent


def check_refinement(original,refined):
    records=refined['records'];source=original['records'];summary=refined['summary']
    if summary['status']!='complete' or len(records)!=len(source):raise ValueError('incomplete refinement')
    if {r['candidate_id'] for r in records}!={r['candidate_id'] for r in source}:raise ValueError('candidate population changed')
    if sorted(r['row_index'] for r in records)!=list(range(len(source))):raise ValueError('refinement row mapping changed')
    for row in records:
        initial=source[row['row_index']]
        if row['candidate_id']!=initial['candidate_id'] or row['probe_key']!=initial['probe_key']:
            raise ValueError('candidate/window binding changed')
        if row['refinement']['status']!='refined' and row['output_hz']!=initial['original_hz']:
            raise ValueError('failed refinement did not retain original')
    if refined['top_rows']!=winners(records):raise ValueError('top candidate is not highest refined score')
    if len(refined['top_rows'])!=original['summary']['passing_windows']:raise ValueError('window denominator changed')


def check_assignments(selection,original):
    for arm in ('fitted-c','zero-c'):
        for method in ('greedy','replacement','alternatives'):
            final=selection['arms'][arm][method]['final'];validate_comparison(final)
            if final['denominator']!=original['summary']['passing_windows']:raise ValueError('association denominator changed')
            assignments=final['assignments']
            groups=[original['records'][a['original_row_index']]['group_id'] for a in assignments]
            if len(groups)!=len(set(groups)) or len(groups)!=final['assigned']:raise ValueError('window double counting')
            if len({a['catalog_number'] for a in assignments})!=final['satellites']:raise ValueError('satellite accounting changed')
            if any(not np.isfinite(a['residual_hz']) or abs(a['residual_hz'])>600.000001 for a in assignments):
                raise ValueError('assignment outside frozen gate')


def check_position(document,ranking,fraction):
    validate(document);meta=document['signature']['inputs']
    signature=document['signature']
    if signature.get('probe_budget_s')!=8. or signature.get('search_budget_s')!=20.:
        raise ValueError('position search budgets differ from frozen experiment')
    if (meta['method'],meta['ranking'],meta['fraction'])!=('alternatives',ranking,fraction):
        raise ValueError('wrong position subset')
    indices=meta['fixed_observation_original_rows']
    if len(indices)!=len(set(indices)) or len(indices)!=meta['retained_windows']:raise ValueError('position membership accounting')
    for arm in ('fitted-c','zero-c'):
        result=document['arms'][arm];records=result['records'];best=result['best_found']
        expected={'roof'}|{f'probe-{i:02d}' for i in range(32)}|{f'search-{i}' for i in range(3)}
        expected|={f'{kind}-transfer-{i}' for kind in ('roof','best','joint') for i in range(2)}
        expected|={f'gradient-{h:g}-{axis}-{sign}' for h in (.05,.1) for axis in (0,1) for sign in (-1,1)}
        stages=[r['stage'] for r in records]
        if len(stages)!=len(expected) or set(stages)!=expected:
            raise ValueError('incomplete or duplicate position experiment stages')
        if any(bool(r['fixed_location'])==r['stage'].startswith(('search-','joint-transfer-')) for r in records):
            raise ValueError('fixed-site and joint search stages differ from protocol')
        if abs(best['objective']-min(r['objective'] for r in records))>1e-7:raise ValueError('best score was not selected')
        if abs(result['radius_m']-1000*np.linalg.norm(best['point_km']))>1e-6:raise ValueError('wrong reported distance')
        if arm=='zero-c' and any(abs(r['coefficient'])>1e-9 for r in records):raise ValueError('zero-c arm changed')
        if not all(k in result for k in ('boundary','ambiguous','finite_difference_gradient')):raise ValueError('missing numerical diagnostics')
        by_stage={r['stage']:r for r in records}
        for h in (.05,.1):
            finite=result['finite_difference_gradient'][str(h)]
            expected_gradient=[];converged=bool(result['roof']['success'])
            for axis in (0,1):
                pair=[by_stage[f'gradient-{h:g}-{axis}-{sign}'] for sign in (-1,1)]
                expected_gradient.append((pair[1]['objective']-pair[0]['objective'])/(2*h))
                converged &= all(r['success'] for r in pair)
            if not np.allclose(finite['gradient_per_km'],expected_gradient,rtol=1e-10,atol=1e-7):
                raise ValueError('finite-difference gradient differs from saved scores')
            if bool(finite['all_converged'])!=converged:raise ValueError('gradient convergence flag changed')
    left={r['stage']:r for r in document['arms']['fitted-c']['records']}
    right={r['stage']:r for r in document['arms']['zero-c']['records']}
    for stage in left:
        if stage=='roof' or stage.startswith(('probe-','gradient-')):
            if not np.allclose(left[stage]['point_km'],right[stage]['point_km'],atol=1e-12,rtol=0):
                raise ValueError('RF arms use different fixed position probes')


def audit(inputs,root=HERE):
    checks=[];verified={}
    def load(path):return json.loads(path.read_text())
    def bind(sources):
        for source,expected in sources.items():
            if source not in verified:verified[source]=digest(Path(source).read_bytes())
            if verified[source]!=expected:raise ValueError(f'stale source: {source}')
    def require(name,action):
        try:action();checks.append(dict(requirement=name,verified=True))
        except (ValueError,KeyError,IndexError,TypeError,OSError) as exc:
            checks.append(dict(requirement=name,verified=False,reason=str(exc)))
    cohort_path=root/'cohort-v2.json';cohort=load(cohort_path);scans=cohort['scans']
    def scope():
        if Counter(r['split'] for r in scans)!=dict(reference=2,development=8,validation=4,locked_test=4):
            raise ValueError('2 + 16 scope or split differs')
        for scan in scans:
            if not all(scan['metadata_checks'].values()):raise ValueError('capture metadata not verified')
            if scan['label']!='A' and scan['sample_rate_hz']!=2500000:raise ValueError('non-2.5 MS/s addition')
            bind({scan['manifest_path']:scan['manifest_file_sha256'],scan['pose_path']:scan['pose_file_sha256']})
            current=verify_capture(load(Path(scan['manifest_path'])),load(Path(scan['pose_path'])),scan['sample_rate_hz'])
            for key in ('session_id','manifest_sha256','pose_binding_digest','capture_start_ns','capture_end_ns'):
                if current[key]!=scan[key]:raise ValueError('capture/pose binding changed')
    require('cohort: 2 references + 16 metadata-bound additions',scope)
    require('settings: completed validation and immutable pre-test freeze',lambda:read_freeze(root))
    for scan in scans:
        label=scan['label'];directory=inputs/label;model=directory/'seed-timing-v6';plot=root/f'pilot-{label}-seeded'
        def refinement():
            original=load(directory/'observations.json');changed=load(directory/'refinement/refined.json')
            validate_export(original,scan,digest(cohort_path.read_bytes()))
            if changed['summary']['signature']['observations_sha256']!=digest((directory/'observations.json').read_bytes()):
                raise ValueError('refinement input changed')
            check_refinement(original,changed)
            for name in (f'{label}-before-after.png',f'{label}-pair-cutoffs.png'):
                if not (root/'refinement-audit'/name).is_file():raise ValueError('missing refinement figure')
        require(f'{label}: all-candidate refinement, top-window selection and distributions',refinement)
        def association():
            selected=load(model/'selection-p10-g600-t1.json');check_assignments(selected,load(directory/'observations.json'))
            metrics=load(plot/'pilot-metrics.json');bind(metrics['sources'])
            receipt=load(plot/'orbit-plot-receipt.json');bind(receipt['sources'])
            if receipt['selection_sha256']!=digest((model/'selection-p10-g600-t1.json').read_bytes()):raise ValueError('orbit selection changed')
            expected={f'{m}-{a}-orbits.png' for m in ('greedy','replacement','alternatives') for a in ('fitted-c','zero-c')}
            if set(receipt['figures'])!=expected:raise ValueError('missing method/RF orbit figures')
            bind({str(plot/n):h for n,h in receipt['figures'].items()})
        require(f'{label}: all 3 association methods × 2 RF arms, counts and orbit plots',association)
        for ranking,fraction in cases(['rms','support','glrt'],[.25,.5,.75,1.]):
            def position(ranking=ranking,fraction=fraction):
                doc=load(case_path(model,ranking,fraction));check_position(doc,ranking,fraction);bind(doc['signature']['inputs']['sources'])
            require(f'{label}: matched position {ranking} {fraction:g}',position)
        def diagnostics():
            doc=load(plot/'alternatives-diagnostics.json');bind(doc['sources'])
            if doc['source_sha256']!=digest((model/'selection-p10-g600-t1.json').read_bytes()):raise ValueError('diagnostic selection changed')
            if {r['arm'] for r in doc['rows']}!={'fitted-c','zero-c'}:raise ValueError('missing RF track diagnostics')
            gradient=load(plot/'satellite-gradients.json');bind(gradient['sources'])
            if set(gradient['statuses'])!={'fitted-c','zero-c'}:raise ValueError('missing RF gradients')
            if any(v['additive_error']>1e-7 for v in gradient['statuses'].values()):raise ValueError('gradient sum failure')
            for name in ('alternatives-track-statistics.csv','alternatives-fitted-c-residuals.png','alternatives-zero-c-residuals.png',
                         'alternatives-orientation.png','satellite-gradients.csv','satellite-gradients.png'):
                if not (plot/name).is_file():raise ValueError(f'missing {name}')
            if not (root/f'position-summary/{label}-subsets.png').is_file():raise ValueError('missing subset figure')
            figures=list(plot.glob('position-alternatives-support-100-position-fisher-v2*.json'))
            if len(figures)!=1:raise ValueError('missing or ambiguous baseline position figure')
            evidence=load(figures[0]);bind({evidence['source']:evidence['source_sha256']})
            if not figures[0].with_suffix('.png').is_file():raise ValueError('missing baseline position image')
        require(f'{label}: residuals, curvature, orientation, gradients, score map and subset figure',diagnostics)
    def aggregates():
        for name in ('leaderboard/summary.json','heldout-calibration/summary.json','position-summary/position-summary.json'):
            doc=load(root/name);bind(doc['sources'])
            if {r['scan'] for r in doc['rows']}!={r['label'] for r in scans}:raise ValueError(f'incomplete cohort aggregate: {name}')
        for name in ('leaderboard/overview.png','leaderboard/method-gains.png','leaderboard/method-gains.csv',
                     'heldout-calibration/comparison.png','position-summary/nuisance-vs-position.png'):
            if not (root/name).is_file():raise ValueError('missing aggregate figure')
    require('cohort aggregates: all18 fit/coverage/position/runtime and nuisance visualizations',aggregates)
    def presentation():
        receipt=load(root/'report-receipt.json')
        if receipt['outputs']['report.html']!=digest((root/'report.html').read_bytes()):raise ValueError('report receipt changed')
        bind(receipt['sources']);assets(root)
    require('standalone HTML: current evidence and every local link resolves',presentation)
    result=dict(scope=__doc__,status='analysis_artifacts_verified' if all(c['verified'] for c in checks) else 'incomplete',
                checks=checks,verified=sum(c['verified'] for c in checks),required=len(checks),
                note='Final delivery also requires reviewed rendered figures, component tests and verified portable bundle. This audit alone does not declare the user goal complete.')
    (root/'completion-audit.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:result[k] for k in ('status','verified','required')}),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=Path);p.add_argument('--require-complete',action='store_true')
    a=p.parse_args();result=audit(a.inputs)
    if a.require_complete and result['status']=='incomplete':raise SystemExit(1)
