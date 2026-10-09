"""Resolve failure-source metadata via public checkpoint/status ports only."""
import datetime
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from leo.application.hard60_runner import Hard60Configuration
from leo.application.regional_position_runner import json_value
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    authority = ROOT/'reports/2026_10_09_position_error_iter101/inventory.json'
    inventory = json.loads(authority.read_text())
    endpoints = json.loads((ROOT/'reports/2026_10_09_position_error_iter85/protocol.json').read_text())
    matched = {b['member']['session_id']: b['result_source'] for b in endpoints['members']}
    rows=[]
    for member in inventory['members']:
        row=dict(dataset=member['dataset'],label=member['label'],session_id=member['session_id'],
                 matched_b7_endpoint=matched.get(member['session_id']), failure_bindings=[])
        for source in member['sources']:
            if not source['calibration_failures']:
                continue
            if 'path' in source:
                document=json.loads((ROOT/source['path']).read_text())
            else:
                cls=B7Store if source['name']=='B7' else Hard60Store
                document=cls(Path('/srv/bulk/leo')).status(member['session_id']).manifest.document.model_dump(mode='json')
            binding=document['diagnostics'].get('checkpoint_binding')
            for failure in source['calibration_failures']:
                result=dict(source=source['name'], **failure, checkpoint_binding=binding, checkpoint_attempts=[])
                if not binding:
                    result['availability']='missing-checkpoint-binding';row['failure_bindings'].append(result);continue
                config_values=dict(document['configuration']['run'])
                for k in ('levels_km','final_starts'):
                    if k in config_values:config_values[k]=tuple(config_values[k])
                config=Hard60Configuration(**config_values)
                if source['name']=='B7':config=replace(config,basin_separation_km={'baseline':12.5,'sep25':25.,'sep50':50.}[failure['region']])
                signature=canonical_digest(json_value(config));basin=failure['basin']
                store=RegionalCheckpointStore(Path('/srv/bulk/leo'),member['session_id'],binding)
                keys=([f'b7-shared:{basin}'] if source['name']=='B7' else [])+[signature+':'+basin,signature+':'+basin+':calibration']
                for key in keys:
                    try:
                        value=store.get(key)
                        receipt=dict(key=key,available=value is not None)
                        if value is not None:
                            receipt.update(value_sha256=canonical_digest(value),reason=value.get('reason'),has_result=value.get('result') is not None)
                            if value.get('result') and 'bootstrap' in value['result']:
                                receipt['bootstrap_sha256']=canonical_digest(value['result']['bootstrap'])
                                receipt['contains_coarse_fit']='fits' in value['result']
                        result['checkpoint_attempts'].append(receipt)
                    except Exception as error:result['checkpoint_attempts'].append(dict(key=key,available=False,error=f'{type(error).__name__}: {error}'))
                result['configuration_signature']=signature
                result['availability']='bootstrap-and-coarse-available' if any(r.get('contains_coarse_fit') for r in result['checkpoint_attempts']) else 'missing-bootstrap-or-coarse'
                result['input_manifest_sha256']=document.get('input_manifest_sha256')
                result['score_prior_signature']=canonical_digest(document['configuration'].get('scores',{}))
                row['failure_bindings'].append(result)
        rows.append(row)
    assert len(rows)==193
    result=dict(created_utc=datetime.datetime.now(datetime.UTC).isoformat(),inventory_sha256=hashlib.sha256(authority.read_bytes()).hexdigest(),members=rows,
                scope='Metadata/checkpoint read only. No fit, reserve access, reference-error reads, or checkpoint writes. Available bootstrap/coarse is necessary, not sufficient: input bank/model reconstruction must still match.')
    (HERE/'source_bindings.json').write_text(json.dumps(result,indent=2)+'\n')
    print('members',len(rows),'failure members',sum(bool(r['failure_bindings']) for r in rows),'available failure bindings',sum(f['availability']=='bootstrap-and-coarse-available' for r in rows for f in r['failure_bindings']))


if __name__=='__main__':main()
