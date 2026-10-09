"""Supplemental read-only research-cache recovery via frozen get adapter."""
import importlib.util
import json
import sys
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ADAPTER=ROOT/'reports/2026_10_08_hard60_bounded_recovery/inputs.py'
spec=importlib.util.spec_from_file_location('frozen_inventory_inputs',ADAPTER)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)


def main():
    inventory=json.loads((ROOT/'reports/2026_10_09_position_error_iter101/inventory.json').read_text())
    protocol=json.loads((ROOT/'reports/2026_10_09_position_error_iter85/protocol.json').read_text())
    bindings={b['member']['session_id']:b['loader_binding'] for b in protocol['members']}
    rows=[]
    for member in inventory['members']:
        if member['dataset']=='POST18-development':continue
        binding=bindings[member['session_id']]
        relevant=[s for s in member['sources'] if s['calibration_failures']]
        if not relevant:continue
        root=Path('/srv/bulk/leo')
        if binding.get('completion_path'):
            completion=json.loads((ROOT/binding['completion_path']).read_text())
            if completion['baseline_mode']=='isolated_standard_baseline':root=ROOT/'reports/2026_10_08_position_error_iter45/local/standard-baselines'
        if binding.get('baseline_path'):
            baseline=json.loads((ROOT/binding['baseline_path']).read_text())
        else:
            manifest=Hard60Store(root).status(member['session_id']).manifest
            baseline=manifest.document.model_dump(mode='json') if manifest else None
        original=baseline
        if binding['kind']=='legacy_ds17':
            published=ROOT/'reports/2026_10_08_position_error_iter01/published'/f"{member['label']}.json"
            if published.exists():original=json.loads(published.read_text())
        elif binding['kind']=='legacy_ds16':
            manifest=Hard60Store(root).status(member['session_id']).manifest
            if manifest:original=manifest.document.model_dump(mode='json')
        for source in relevant:
            document=json.loads((ROOT/source['path']).read_text())
            config=document['configuration']['run'];signature=canonical_digest(config)
            cache=None
            if '2026_10_09_position_error_iter51/' in source['path'] and baseline:
                directory=ROOT/'reports/2026_10_09_position_error_iter51/local/checkpoints'/member['label']/source['name']
                cache=module.ExperimentCheckpoints(directory,dict(baseline=canonical_digest(baseline),config=config))
            for failure in source['calibration_failures']:
                record=dict(dataset=member['dataset'],label=member['label'],session_id=member['session_id'],source=source['path'],basin=failure['basin'],configuration_signature=signature,attempts=[])
                key=signature+':'+failure['basin']
                if cache:
                    for suffix in ('',':calibration'):
                        try:
                            value=cache.get(key+suffix)
                            record['attempts'].append(dict(port='ExperimentCheckpoints.get',directory=str(cache.directory.relative_to(ROOT)),key=key+suffix,available=value is not None,value_sha256=canonical_digest(value) if value is not None else None,contains_bootstrap=bool(value and value.get('result') and 'bootstrap'in value['result'])))
                        except Exception as error:record['attempts'].append(dict(port='ExperimentCheckpoints.get',key=key+suffix,error=f'{type(error).__name__}: {error}',available=False))
                if original and original['diagnostics'].get('checkpoint_binding'):
                    store=RegionalCheckpointStore(root,member['session_id'],original['diagnostics']['checkpoint_binding'])
                    borrowed_key=canonical_digest(original['configuration']['run'])+':'+failure['basin']
                    try:
                        value=store.get(borrowed_key)
                        record['attempts'].append(dict(port='RegionalCheckpointStore.get (ReplayCheckpoints borrowed stage)',root=str(root),key=borrowed_key,available=value is not None,value_sha256=canonical_digest(value) if value is not None else None,contains_bootstrap=bool(value and value.get('result') and 'bootstrap'in value['result'])))
                    except Exception as error:record['attempts'].append(dict(port='RegionalCheckpointStore.get',key=borrowed_key,available=False,error=f'{type(error).__name__}: {error}'))
                record['bootstrap_available']=any(a.get('contains_bootstrap') for a in record['attempts'])
                record['gap']=None if record['bootstrap_available'] else 'No matching bootstrap in tested frozen51 cache / bound ordinary borrowed source; other archived adapters not yet resolved'
                rows.append(record)
    (HERE/'research_source_bindings.json').write_text(json.dumps(dict(scope='Supplemental receipt; no fits/no reserves; only get ports',adapter_sha256=__import__('hashlib').sha256(ADAPTER.read_bytes()).hexdigest(),failures=rows),indent=2)+'\n')
    print(len(rows),'pass failures;',sum(r['bootstrap_available'] for r in rows),'bootstrap available')


if __name__=='__main__':main()
