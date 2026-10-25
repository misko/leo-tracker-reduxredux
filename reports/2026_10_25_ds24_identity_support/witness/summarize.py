"""Summarize sealed ownership/time/RF metadata only; never loads CFO values."""
from collections import Counter
from itertools import combinations
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    sealed=json.loads((HERE/'seal02.json').read_text())
    for p,h in sealed['files'].items():assert sha(p)==h
    inventory=json.loads((HERE/'inventory.json').read_text())
    rx=[r for r in inventory['rows'] if r['receiver']=='RX2']
    curved=[r for r in rx if r['canonical_curved']]
    selected=[r for r in inventory['rows'] if r['primary_eligible'] or r['secondary_noncurved_eligible']]
    used=[i for r in inventory['rows'] for i in r['observation_ids']]
    rows=[]
    for r in selected:
        support=[]
        for ref in inventory['references']:
            support.append(dict(reference_component=ref['component'],
                candidate_points_in_reference_interval=sum(ref['start_s']<=t<=ref['end_s'] for t in r['times_s']),
                reference_points_in_candidate_interval=sum(r['start_s']<=t<=r['end_s'] for t in ref['times_s']),
                nearest_native_time_separation_s=min(abs(a-b) for a in r['times_s'] for b in ref['times_s'])))
        rows.append({k:r[k] for k in ('component','points','start_s','end_s','rf_hz','primary_eligible','secondary_noncurved_eligible','same_carrier_primary_eligible','same_carrier_secondary_eligible','observation_ids')}|dict(native_time_support=support))
    result=dict(counts=inventory['counts'],
        RX2_curved_exclusion_counts_not_disjoint=dict(Counter(x for r in curved for x in r['eligibility_reasons'])),
        unused_RX2_curved_without_time_support=sum(not any(r['original_accepted_ID_overlap'].values()) for r in curved),
        all_owner_ID_occurrences=len(used),all_distinct_native_IDs=len(set(used)),
        selected=rows,
        selected_pairwise_native_ID_overlaps=[dict(first=a['component'],second=b['component'],
            observation_ids=sorted(set(a['observation_ids'])&set(b['observation_ids']))) for a,b in combinations(selected,2)],
        metadata_selection_frozen_before_any_CFO_comparison=True,
        source_seal_sha256=sha(HERE/'seal02.json'),source_sha256=sha(__file__),
        new_RF_scores=0,position_fits=0,GPS_used=False)
    with (HERE/'summary.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    with (HERE/'summary_seal.json').open('x') as f:
        json.dump(dict(files={str(HERE/p):sha(HERE/p) for p in ('summarize.py','summary.json')},inventory_seal_sha256=sha(HERE/'seal02.json')),f,indent=2);f.write('\n')
    print(json.dumps(dict(selected=[{k:r[k] for k in ('component','points','native_time_support')} for r in rows],
        selected_native_ID_count=sum(r['points'] for r in rows),pairwise_ID_overlaps=result['selected_pairwise_native_ID_overlaps']),indent=2))


if __name__=='__main__':main()
