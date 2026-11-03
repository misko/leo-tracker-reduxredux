"""Apply the frozen validation rule; never select settings using test outcomes.

Freezing requires all four configurations and both RF arms on all validation
scans, including explicitly failed results. Inconclusive evidence retains the
baseline reference, without calling it optimal. Existing freezes are immutable.
"""
import argparse
from datetime import datetime,timezone
import json
import math
from pathlib import Path
from statistics import median

from cohort import digest

HERE=Path(__file__).resolve().parent


def decide(protocol,rows):
    labels=protocol['validation_scans']
    configs=[c['name'] for c in protocol['configurations']]
    expected={(s,c,a) for s in labels for c in configs for a in ('fitted-c','zero-c')}
    selected=[r for r in rows if r['split']=='validation']
    keys=[(r['scan'],r['configuration'],r['arm']) for r in selected]
    if len(keys)!=len(set(keys)) or set(keys)!=expected:
        raise ValueError('complete unique matched validation matrix required')
    if any(not math.isfinite(r['error_m']) or not 0<=r['error_m']<=2000.001 for r in selected):
        raise ValueError('invalid validation position error')
    primary={(r['scan'],r['configuration']):r for r in selected if r['arm']=='fitted-c'}
    failures={c:sum(not primary[s,c]['eligible'] for s in labels) for c in configs}
    comparisons=[]
    for config in configs:
        if config=='baseline':continue
        common=[s for s in labels if primary[s,'baseline']['eligible'] and primary[s,config]['eligible']]
        base=median(primary[s,'baseline']['error_m'] for s in common) if common else None
        challenger=median(primary[s,config]['error_m'] for s in common) if common else None
        reduction=(base-challenger)/base if base is not None and base>0 else None
        qualifies=bool(len(common)>=3 and reduction is not None and reduction>=.2
                       and failures[config]<=failures['baseline'])
        comparisons.append(dict(configuration=config,common_eligible_scans=common,
            baseline_median_error_m=base,challenger_median_error_m=challenger,
            relative_median_reduction=reduction,failures=failures[config],qualifies=qualifies))
    winners=[r for r in comparisons if r['qualifies']]
    # Deterministic tie order is the frozen configuration order. No test data.
    best=max(winners,key=lambda r:r['relative_median_reduction']) if winners else None
    sufficient=any(len(r['common_eligible_scans'])>=3 for r in comparisons)
    return dict(selected_configuration=best['configuration'] if best else 'baseline',
        status='validation_selected' if best else 'baseline_retained_no_qualifying_challenger' if sufficient
               else 'inconclusive_baseline_reference',
        primary_arm='fitted-c',baseline_failures=failures['baseline'],comparisons=comparisons,
        notes=['Known-roof-conditioned association experiment, not blind identity validation.',
               'Failure and boundary outcomes are retained; failed roof starts do not count as zero-error success.',
               'No test outcome was read. Both RF arms remain required; c=0 is a controlled ablation.'])


def read_freeze(root=HERE):
    saved=json.loads((root/'final-settings.json').read_text())
    if saved.get('schema')!='offline-final-settings/v1' or not saved.get('sources'):
        raise ValueError('invalid final settings freeze')
    if saved['cohort_sha256']!=digest((root/'cohort-v2.json').read_bytes()):
        raise ValueError('frozen cohort changed')
    for source,expected in saved['sources'].items():
        if digest(Path(source).read_bytes())!=expected:raise ValueError('frozen settings evidence changed')
    return saved


def freeze(root=HERE):
    target=root/'final-settings.json'
    if target.exists():return read_freeze(root)
    protocol_path=root/'validation-shortlist.json';summary_path=root/'finalist-comparison/summary.json'
    protocol=json.loads(protocol_path.read_text());summary=json.loads(summary_path.read_text())
    # Validate all input provenance, but bind the final freeze only to validation
    # records: later rendering more development/test figures must not invalidate it.
    for source,expected in {**protocol['sources'],**summary['sources']}.items():
        if digest(Path(source).read_bytes())!=expected:raise ValueError('validation evidence changed')
    decision=decide(protocol,summary['rows'])
    sources={str(protocol_path):digest(protocol_path.read_bytes())}
    for source,expected in summary['sources'].items():
        if any(label in Path(source).parts for label in protocol['validation_scans']):sources[source]=expected
    if len(sources)!=1+4*len(protocol['configurations']):raise ValueError('validation summary provenance incomplete')
    implementation=['association_search.py','select_associations.py','calibration.py','seed_timing_variant.py',
                    'discovery.py','position_search.py','run_fisher_positions.py','freeze_final_settings.py']
    for name in implementation:sources[str(root/name)]=digest((root/name).read_bytes())
    config=next(c for c in protocol['configurations'] if c['name']==decision['selected_configuration'])
    result=dict(schema='offline-final-settings/v1',frozen_utc=datetime.now(timezone.utc).isoformat(),
        cohort_sha256=protocol['cohort_sha256'],sources=sources,decision=decision,configuration=config,
        satellite_penalty=protocol['satellite_penalty'],position_timing_prior_scale=protocol['position_timing_prior_scale'],
        variant='seed-timing-v6',methods=['greedy','replacement','alternatives'],rf_arms=['fitted-c','zero-c'],
        position_policy='Independent 2 km disk, matched Fisher-v2 budgets; failed fits remain failed.',
        subset_rankings=['rms','support','glrt'],subset_fractions=[.25,.5,.75,1.],
        locked_test_policy='Run frozen settings once; no hyperparameter changes based on test outcomes.')
    with target.open('x') as stream:json.dump(result,stream,indent=2)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.parse_args();print(json.dumps(freeze()['decision'],indent=2))
