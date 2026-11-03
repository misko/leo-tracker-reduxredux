"""Freeze a small validation shortlist from completed development screens.

This is NOT the final-settings freeze and does not unlock test inference.
Keep the task's reference penalty10 and baseline timing priors: the penalty
screen gives no gain at the common penalty10 objective, and timing-width
results have too few common converged scans to establish a robust winner.
Validation compares coverage/purity/curvature tradeoffs, not raw NLL across
different retained observations. All four validation scans get all finalists.
"""
import argparse
import json
from pathlib import Path
from cohort import digest

HERE=Path(__file__).resolve().parent
CONFIGS=[dict(name='baseline',selection='selection-p10-g600-t1.json',gate_hz=600,curvature_cutoff=None),
         dict(name='tight_gate',selection='selection-p10-g300-t1.json',gate_hz=300,curvature_cutoff=None),
         dict(name='wide_gate',selection='selection-p10-g900-t1.json',gate_hz=900,curvature_cutoff=None),
         dict(name='curvature_1.1',selection='selection-curvature-1.1.json',gate_hz=600,curvature_cutoff=1.1)]


def prior_evidence(rows):
    scales=(.5,1.,2.)
    result={}
    for arm in ('fitted-c','zero-c'):
        by_scale={s:{r['scan']:r for r in rows if r['arm']==arm and r['prior_width_scale']==s} for s in scales}
        common=set.intersection(*({n for n,r in by_scale[s].items() if r['best_joint_stationary'] and not r['boundary']} for s in scales))
        result[arm]=dict(common_valid_scans=sorted(common),by_scale={str(s):dict(
            joint_stationary=sum(r['best_joint_stationary'] for r in by_scale[s].values()),
            nonstationary=sum(not r['best_joint_stationary'] for r in by_scale[s].values()),
            mean_error_common_valid_m=sum(by_scale[s][n]['radius_m'] for n in common)/len(common) if common else None)
            for s in scales})
    return result


def freeze():
    target=HERE/'validation-shortlist.json'
    if target.exists():
        saved=json.loads(target.read_text())
        for path,expected in saved['sources'].items():
            if digest(Path(path).read_bytes())!=expected:raise ValueError('frozen development evidence changed')
        return target
    cohort_path=HERE/'cohort-v2.json';cohort=json.loads(cohort_path.read_text())
    dev=[r['label'] for r in cohort['scans'] if r['split']=='development']
    aggregate=HERE/'hyperparameter-screen/aggregate.json'
    if set(json.loads(aggregate.read_text())['scans'])!=set(dev):raise ValueError('all development association screens required')
    sources={str(cohort_path):digest(cohort_path.read_bytes()),str(aggregate):digest(aggregate.read_bytes())}
    prior_rows=[]
    for label in dev:
        p=HERE/f'timing-prior-screen/{label}.json';document=json.loads(p.read_text())
        if {(r['arm'],r['prior_width_scale']) for r in document['rows']}!={(a,s) for a in ('fitted-c','zero-c') for s in (.5,1.,2.)}:
            raise ValueError('incomplete prior screen')
        for source,expected in document['sources'].items():
            if digest(Path(source).read_bytes())!=expected:raise ValueError('prior screen checkpoint changed')
        prior_rows.extend(document['rows']);sources[str(p)]=digest(p.read_bytes())
        p=HERE/f'curvature-screen/{label}.json';curve=json.loads(p.read_text())
        if {r['cutoff'] for r in curve['rows']}!={1.1,1.05}:raise ValueError('incomplete curvature screen')
        sources[str(p)]=digest(p.read_bytes())
    document=dict(schema='offline-validation-shortlist/v1',status='validation_shortlist_frozen_not_test_unlock',
        sources=sources,cohort_sha256=digest(cohort_path.read_bytes()),development_scans=dev,
        validation_scans=[r['label'] for r in cohort['scans'] if r['split']=='validation'],configurations=CONFIGS,
        satellite_penalty=10,position_timing_prior_scale=1.,curvature_cutoffs=[1.1],
        prior_evidence=prior_evidence(prior_rows),scope=__doc__,
        selection_rule={'primary_arm':'fitted-c','required_completed_validation_scans':4,
            'eligible_fit':'Jointly stationary best-found basin within 1e-7 NLL and 0.1m numerical tolerance; no calibration warning; no search boundary.',
            'comparison':'Report failures and coverage first. Compare median position error only on at least three common eligible validation scans, with scans equally weighted.',
            'winner':'A challenger must reduce common-scan median position error by at least 20% versus baseline without increasing failure count. Report all coverage and common300Hz support tradeoffs.',
            'fallback':'If no challenger satisfies the rule, retain baseline as reference; label selection inconclusive when common eligible evidence is insufficient. Do not call a failed roof-start result zero-error success.',
            'rf_ablation':'Always evaluate and report c=0 with matched observations, bank, other priors and budgets; no inference of better position from frequency fit alone.'},
        notes=['1.05 curvature is retained as a development diagnostic, not promoted over 1.1 without position evidence.',
               'RMS/curvature selection at the known roof remains an oracle-conditioned diagnostic, not blind identity or localization validation.',
               'Baseline validation position runs may already exist; no challenger validation position outcomes were used to choose this shortlist.'])
    with target.open('x') as stream:json.dump(document,stream,indent=2)
    return target


def prepare(inputs,label):
    protocol=freeze();document=json.loads(protocol.read_text())
    if label not in document['validation_scans']:raise ValueError('shortlist preparation accepts validation scans only')
    from select_associations import run
    from screen_curvature import run as curvature
    directory=inputs/label/'seed-timing-v6'
    for gate in (600.,300.,900.):run(directory,penalty=10.,gate=gate)
    curvature(inputs,label,protocol)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',type=Path,nargs='?');p.add_argument('--label')
    a=p.parse_args()
    if a.label:prepare(a.inputs,a.label)
    else:print(freeze())
