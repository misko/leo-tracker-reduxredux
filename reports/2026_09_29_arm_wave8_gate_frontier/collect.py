#!/usr/bin/env python3
"""Collect the sealed host gate sweep and bind evidence hashes."""
import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for variant in ('313','3135','314','320','325','330'):
    cohort=ROOT/f'host704-{variant}'
    summary=json.loads((cohort/'summary.json').read_text())
    audit=json.loads((cohort/'standard-audit.json').read_text())
    assert summary['complete'] and sha(cohort/'rows.jsonl')==summary['rows_sha256']
    assert audit['native_sha256']==summary['rows_sha256']
    primary=audit['by_rate']['2500000'];total=audit['totals'];primary_entries=0
    for line in (cohort/'rows.jsonl').open():
        dwell=json.loads(line)
        if dwell['context']['rate_hz']==2500000:
            primary_entries+=sum(len(window['candidates']) for window in dwell['rows'])
    rows.append({'threshold':int(variant)/1000,'dwells':summary['dwells'],
        'candidate_entries':summary['candidate_entries'],'primary_candidate_entries':primary_entries,
        'mean_outer_cpu_ms_per_dwell':summary['mean_timings_ms']['fused_total'],
        'primary_recovered':primary['recovered_positive_hits'],
        'primary_denominator':primary['reference_positive_hits'],
        'all_rate_recovered':total['recovered_positive_hits'],
        'all_rate_denominator':total['reference_positive_hits'],
        'quality_floor_pass':primary['recovered_positive_hits']>=4116,
        'hashes':{name:sha(cohort/name) for name in
            ('summary.json','standard-audit.json','rows.jsonl','manifest.json','build-receipt.json')}})
result={'schema':'arm-wave8-gate-frontier-sweep/v1',
    'baseline':{'threshold':.312,'primary_recovered':4235,'primary_denominator':4573,
                'primary_candidate_entries':5463,'all_rate_recovered':18465,
                'all_rate_denominator':19581,'candidate_entries':77894},
    'required_primary_recovery':4116,'rows':rows,'selected_for_arm':.314,
    'decision':'0.314 is the highest tested threshold above the quality floor and removes 511 primary-rate candidates (9.35%); cross-build only, no ARM timing yet.'}
(ROOT/'results.json').write_text(json.dumps(result,indent=2)+'\n')
