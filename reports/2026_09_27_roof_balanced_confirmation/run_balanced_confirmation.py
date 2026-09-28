"""Second frozen confirmation; reference manifest remains opaque to searches."""
import argparse
import json
from pathlib import Path
import pickle
import sys
import time
import numpy as np

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent/'2026_09_27_roof_geometry_confirmation'
LOCATION = HERE.parent/'2026_09_27_roof_location_geometry'
# Resolve the unchanged previous confirmation helpers explicitly.
sys.path[:0] = [str(PREVIOUS), str(LOCATION)]
import run_topology_confirmation as frozen
from depth_balanced_search import search

base = frozen.base


def inputs():
    contract = json.loads((HERE/'contract.json').read_text())
    for name, expected in contract['files'].items():
        if base.digest(Path(name).read_bytes()) != expected:
            raise ValueError('frozen contract mismatch: '+name)
    inventory = json.loads((HERE/'inventory.json').read_text())
    if [x['session_id'] for x in inventory] != contract['session_ids'] or len(inventory)!=4:
        raise ValueError('frozen cohort order/membership mismatch')
    return inventory, contract


def run(index, deduplicate=False):
    start=time.monotonic(); entries,contract=inputs(); entry=entries[index]; sid=entry['session_id']
    target=HERE/f"{'dedup-' if deduplicate else ''}search-{sid}.json"
    if target.exists(): raise FileExistsError(target)
    oldaudit, oldsha=frozen.frozen_audit()
    frequency,detection,continuous,variance,bias,models=frozen.frozen_models(oldaudit,oldsha)
    payload=Path(entry['cache_file']).read_bytes()
    if base.digest(payload)!=entry['cache_sha256']: raise ValueError('cache changed')
    raw=pickle.loads(payload)
    prepared=base.prepare_adaptive_tle_position_inputs(sid,inputs=base.CachedInput(raw),
        archive=base.TleArchiveReader(Path('/var/lib/leo/tle')))
    for key in ('input_manifest_sha256','analysis_manifest_sha256'):
        if getattr(prepared,key)!=entry[key]: raise ValueError('prepared input changed')
    links=frozen.resolve(raw)
    prepared,receipt=frozen.filter_prepared(prepared,links)
    audit=json.loads((HERE/'audit_source_topology.json').read_text())
    audited=next(x for x in audit['sessions'] if x['session_id']==sid)
    for key in ('removed_track_ids','counts','collisions','unchanged'):
        if receipt[key]!=audited[key]: raise ValueError('topology changed: '+key)
    canonical=json.dumps(links,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if base.digest(canonical)!=audited['source_links_sha256']: raise ValueError('source links changed')
    rows=frozen.original.reception_endpoints.build(raw,prepared,bias_hz=bias)
    reception,endpoints=frozen.original.reception_inputs(prepared,rows,detection,continuous)
    dependence=None
    if deduplicate:
        reception,dependence=frozen.deduplicate_matched_physical_pairs(reception,endpoints)
    banks,_=base.build_prediction_banks(prepared.catalogue,prepared.candidate_indices,
        prepared.start_utc_ns,prepared.tracks,taus_s=np.array([0.]))
    out=dict(session_id=sid,finished=False,branches={},model_hashes=models,
        contract_sha256=base.digest((HERE/'contract.json').read_bytes()),
        cache_sha256=entry['cache_sha256'],topology_receipt=receipt,
        deduplicate_reception=deduplicate,dependence_sensitivity=dependence,
        protocol=dict(budget_per_arm=160,timing_s=0,priors=base.PRIORS,levels_km=base.LEVELS,
            truth_access='opaque manifest digest only; independent priors and per-location catalogue fits'))
    for name,(lat,lon,radius) in base.PRIORS.items():
        evaluator=frozen.original.RobustBranchEvaluator(banks,(lat,lon),reception,variance,frequency['parameters'])
        branch=dict(origin=[lat,lon],radius_km=radius,arms={})
        for arm in base.ARMS:
            result=search(evaluator.for_arm(arm),radius_km=radius,levels_km=base.LEVELS,budget_points=160)
            selected=result.global_incumbent
            branch['arms'][arm]=dict(selected=evaluator.cache[(selected.east_km,selected.north_km)],
                evaluated_points=len(result.all_evaluations),finest_points=len(result.finest_evaluations),
                stop_reason=result.stop_reason,trace=list(result.trace))
            print('ARM_DONE',sid,name,arm,flush=True)
        branch['point_components']=[{k:v for k,v in p.items() if k!='tracks'} for p in evaluator.cache.values()]
        branch['geometry_guided_doppler']=frozen.select_rx_guided_doppler(branch)
        out['branches'][name]=branch; base.atomic(target,out)
    out['finished']=True;out['elapsed_s']=time.monotonic()-start
    base.atomic(target,out);print('SCAN_DONE',sid,round(out['elapsed_s'],1),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scan-index',type=int,required=True,choices=range(4))
    parser.add_argument('--deduplicate-reception',action='store_true')
    args=parser.parse_args();run(args.scan_index,args.deduplicate_reception)
