"""Audit all terminal inference first, then authorized post-seal GPS reporting."""

import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

HERE=Path(__file__).resolve().parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
RECOVERY=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encode(v):return v.tolist() if isinstance(v,np.ndarray) else v.item() if isinstance(v,np.generic) else str(v)
def write(name,value):
    with (HERE/name).open('x') as stream:json.dump(value,stream,indent=2,default=encode,allow_nan=False);stream.write('\n')


def distance_km(point,reference):
    a,b,c,d=map(math.radians,(*point,*reference))
    value=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 2*6371.0088*math.asin(min(1.,math.sqrt(value)))


def audit_inference():
    terminal=read(HERE/'position_terminal_seal.json')
    protocol=read(HERE/'position_protocol_v2.json')
    assert terminal['all_terminal'] and terminal['evaluation_now_permitted']
    assert not terminal['GPS_error_evaluation_performed'] and not terminal['denied_reads']
    for path,digest in terminal['terminal_output_hashes'].items():assert sha(path)==digest,path
    for path,digest in dict(protocol['input_hashes'],**protocol['source_hashes']).items():assert sha(path)==digest,path
    sys.path[:0]=['/tmp/algo03-feasible-deps',str(REPO/'src'),str(REPO/'tools'),str(RECOVERY)]
    import recovery
    audited=[]
    for job in protocol['jobs']:
        root=Path(job['root']);execution=read(root/'execution.json')
        receipts=[read(p) for p in (root/'read_receipts').glob('*.json')]
        if execution['status']=='complete':assert len(receipts)>=3
        assert not any(r['denied_paths'] for r in receipts)
        reads=sorted({p for receipt in receipts for p in receipt['read_paths']})
        assert not any('gps' in Path(p).name.lower() or 'oracle' in Path(p).name.lower() for p in reads)
        item=dict(case=job['case'],variant=job['variant'],status=execution['status'],
            seconds=execution['seconds'],read_receipt_processes=len(receipts),read_paths=reads)
        if execution['status']=='complete':
            recovery.SOURCE=root
            d=recovery.context(job['case'])
            members={arm:recovery.membership(d,arm,d['arms'][arm]) for arm in ('c0','fitted_c')}
            assert members['c0']['curved_observation_ids']==members['fitted_c']['curved_observation_ids']
            assert members['c0']['predictive_observation_ids']==members['fitted_c']['predictive_observation_ids']
            added=set(read(root/job['case']/'research_input_receipt.json')['added_native_observation_ids'])
            item['arms']={arm:dict(objective_replay_difference=m['objective_replay_difference'],
                likelihood_points=m['likelihood_points'],curved_points=m['curved_points'],predictive_points=m['predictive_points'],
                added_curved=len(added&set(m['curved_observation_ids'])),
                added_predictive=len(added&set(m['predictive_observation_ids'])),
                added_accepted=len(added&set(m['accepted_observation_ids'])),
                postfit_only_points=len(m['postfit_only_observation_ids']),
                RMS_hz=d['arms'][arm]['RMS_hz'],negative_twice_elbo=d['arms'][arm]['negative_twice_elbo'])
                for arm,m in members.items()}
            item['matched_c_observations_aliases_candidates_priors_and_budget']=True
        audited.append(item)
    seal=dict(all_terminal=True,all_complete=all(r['status']=='complete' for r in audited),
        audited=audited,GPS_errors_opened=False,no_denied_inference_reads=True,
        terminal_seal_sha256=sha(HERE/'position_terminal_seal.json'),
        protocol_sha256=sha(HERE/'position_protocol_v2.json'),evaluation_source_sha256=sha(__file__))
    write('position_inference_audit.json',seal)
    return seal,protocol


def evaluate():
    audit,protocol=audit_inference()
    # Authorized reporting-only reference is introduced after terminal/input/read
    # audits have been written; it is never in a run directory or inference env.
    reference=[37.849061591561885,-122.48574968092912]
    rows=[]
    for item,job in zip(audit['audited'],protocol['jobs'],strict=True):
        row={k:item[k] for k in ('case','variant','status','seconds')}
        if item['status']=='complete':
            final=read(Path(job['root'])/'family_cavity/position'/(job['case']+'.json'))
            row['arms']={arm:dict(item['arms'][arm],endpoint_latlon=final['policy_arms'][arm]['endpoint_latlon'],
                position_error_km=distance_km(final['policy_arms'][arm]['endpoint_latlon'],reference))
                for arm in ('c0','fitted_c')}
        rows.append(row)
    by_key={(r['case'],r['variant']):r for r in rows}
    effects=[]
    for case in protocol['cases']:
        base=by_key[case,'baseline']
        for variant in ('additions_proxy','additions_bin_floor'):
            changed=by_key[case,variant]
            record=dict(case=case,variant=variant)
            if base['status']==changed['status']=='complete':
                record['arms']={arm:dict(position_error_change_km=changed['arms'][arm]['position_error_km']-base['arms'][arm]['position_error_km'],
                    relative_error_change=(changed['arms'][arm]['position_error_km']/base['arms'][arm]['position_error_km']-1),
                    frequency_RMS_change_hz=changed['arms'][arm]['RMS_hz']-base['arms'][arm]['RMS_hz'],
                    likelihood_point_change=changed['arms'][arm]['likelihood_points']-base['arms'][arm]['likelihood_points'])
                    for arm in ('c0','fitted_c')}
            else:record['status']='unavailable'
            effects.append(record)
    write('position_evaluation.json',dict(schema='missed-visit-exploratory-regional-evaluation-v1',
        inference_audit_sha256=sha(HERE/'position_inference_audit.json'),post_seal_GPS_reporting_only=True,
        reference_latlon=reference,rows=rows,effects=effects,
        development_cases_selected_by_RF_graph_evidence=True,held_validation_claim=False,
        uncertainty_calibrated=False,promotion_authorized=False))
    print(json.dumps(dict(rows=rows,effects=effects),indent=2))


if __name__=='__main__':evaluate()
