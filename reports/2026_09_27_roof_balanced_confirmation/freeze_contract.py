"""Bind the fixed model, inputs and search implementation before evaluation."""
import json
from pathlib import Path
import run_balanced_confirmation as runner

HERE=Path(__file__).resolve().parent


def main():
    target=HERE/'contract.json'
    if target.exists(): raise FileExistsError(target)
    inventory=json.loads((HERE/'inventory.json').read_text())
    if len(inventory)!=4 or len({x['session_id'] for x in inventory})!=4 or not all(x['ready'] for x in inventory):
        raise ValueError('need exactly four ready frozen inputs')
    paths=[HERE/name for name in ('manifest.json','inventory.json','audit_source_topology.json',
        'PROTOCOL.md','run_balanced_confirmation.py','freeze_contract.py','score_results.py',
        'select_balanced_confirmation.py','audit_source_topology.py')]
    paths += [runner.PREVIOUS/name for name in ('run_topology_confirmation.py','run_confirmation.py',
        'source_topology.py','guided_selection.py','reception_sensitivity.py','audit_source_topology.json',
        'topology_calibration.json')]
    paths += [runner.LOCATION/name for name in ('depth_balanced_search.py','measured_search.py',
        'run_robust_search.py','run_search.py','robust_core.py','fit_frequency.py',
        'reception_endpoints.py','topology_frequency_parameters.json','topology_frequency_fixedpoint.json')]
    paths += [runner.frozen.original.DIRECTION/name for name in ('model_eval.py','source_links.py','pairing_summary.json','model_rows.json')]
    paths += [Path(x['cache_file']) for x in inventory]
    audit,sha=runner.frozen.frozen_audit();runner.frozen.frozen_models(audit,sha)
    newaudit=json.loads((HERE/'audit_source_topology.json').read_text())
    if newaudit['parent_calibration_topology_audit_sha256']!=sha:
        raise ValueError('confirmation audit/calibration binding mismatch')
    for name in ('manifest','inventory'):
        if newaudit[name+'_sha256']!=runner.base.digest((HERE/(name+'.json')).read_bytes()):
            raise ValueError('audit input binding mismatch')
    out=dict(session_ids=[x['session_id'] for x in inventory],
        calibration_audit_sha256=sha,files={str(p):runner.base.digest(p.read_bytes()) for p in paths})
    runner.base.atomic(target,out)
    print('CONTRACT_FROZEN',out['session_ids'],runner.base.digest(target.read_bytes()))


if __name__=='__main__': main()
