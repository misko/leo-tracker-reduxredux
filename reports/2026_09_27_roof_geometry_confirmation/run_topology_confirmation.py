"""Separately versioned, outcome-blind topology-integrity confirmation."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import pickle
import time
import numpy as np

import run_confirmation as original
from source_topology import filter_prepared
from source_links import resolve
from guided_selection import select_rx_guided_doppler
from reception_sensitivity import deduplicate_matched_physical_pairs

HERE=Path(__file__).resolve().parent
base=original.base


def frozen_audit():
    payload=(HERE/'audit_source_topology.json').read_bytes()
    audit=json.loads(payload)
    for name,path in [('source_topology.py',HERE/'source_topology.py'),
                      ('source_links.py',original.DIRECTION/'source_links.py')]:
        if audit['source_code_sha256'][name] != base.digest(path.read_bytes()):
            raise ValueError('topology implementation changed after outcome-blind audit')
    return audit,base.digest(payload)


def frozen_models(audit,audit_sha):
    frequency_bytes=(original.LOCATION/'topology_frequency_parameters.json').read_bytes()
    frequency=json.loads(frequency_bytes)
    reception_bytes=(HERE/'topology_calibration.json').read_bytes()
    calibration=json.loads(reception_bytes)
    expected=sorted(s['session_id'] for s in audit['sessions'] if s['split']=='calibration')
    for model in (frequency,calibration):
        if model['topology_audit_sha256']!=audit_sha or model['calibration_sessions']!=expected:
            raise ValueError('both models must use the exact audited calibration track population')
    if not frequency['converged'] or not frequency['parameters']['optimizer_success']:
        raise ValueError('filtered frequency calibration has not converged')
    extraction=frequency['extraction_file']
    if Path(extraction).name!=extraction or frequency['extraction_sha256']!=base.digest((original.LOCATION/extraction).read_bytes()):
        raise ValueError('filtered frequency extraction binding mismatch')
    for filename,key in (('robust_core.py','robust_core_sha256'),('fit_frequency.py','fit_frequency_sha256')):
        if frequency[key]!=base.digest((original.LOCATION/filename).read_bytes()):
            raise ValueError('frequency implementation changed after calibration')
    if calibration['source_model_rows_sha256']!=base.digest((original.DIRECTION/'model_rows.json').read_bytes()):
        raise ValueError('reception calibration source features changed')
    if calibration['model_eval_sha256']!=base.digest((original.DIRECTION/'model_eval.py').read_bytes()):
        raise ValueError('reception feature implementation changed after calibration')
    detection=base.model_eval.FittedModel(**calibration['detection'])
    continuous=base.model_eval.FittedModel(**calibration['ratio'])
    variance=float(calibration['ratio_variance'])
    if not np.isfinite(variance) or variance<=0:raise ValueError('invalid reception variance')
    pairing_bytes=(original.DIRECTION/'pairing_summary.json').read_bytes()
    if calibration['pairing_summary_sha256']!=base.digest(pairing_bytes):
        raise ValueError('receiver matching calibration changed after refit')
    bias=float(json.loads(pairing_bytes)['calibration_fit']['bias_hz'])
    if not np.isfinite(bias):raise ValueError('invalid receiver pairing bias')
    return frequency,detection,continuous,variance,bias,dict(
        frequency_parameters_sha256=base.digest(frequency_bytes),
        calibration_sha256=base.digest(reception_bytes),pairing_summary_sha256=base.digest(pairing_bytes))


def run(index,deduplicate=False):
    start=time.monotonic()
    entries,manifest_sha,inventory_sha=original.confirmation_entries()
    if not 0<=index<len(entries):raise IndexError('confirmation scan index out of range')
    entry=entries[index];sid=entry['session_id']
    prefix='topology-dedup-search-' if deduplicate else 'topology-search-'
    target=HERE/f'{prefix}{sid}.json'
    if target.exists():raise FileExistsError('amended result exists; refusing overwrite')
    audit,audit_sha=frozen_audit()
    audited=next(x for x in audit['sessions'] if x['session_id']==sid and x['split']=='confirmation')
    for key in ('cache_sha256','input_manifest_sha256','analysis_manifest_sha256'):
        if audited[key]!=entry[key]:raise ValueError('topology audit input binding mismatch')
    frequency,detection,continuous,variance,bias,model_hashes=frozen_models(audit,audit_sha)
    payload=Path(entry['cache_file']).read_bytes()
    if base.digest(payload)!=entry['cache_sha256']:raise ValueError('cache digest mismatch')
    raw=pickle.loads(payload)
    prepared=base.prepare_adaptive_tle_position_inputs(sid,inputs=base.CachedInput(raw),
        archive=base.TleArchiveReader(Path('/var/lib/leo/tle')))
    if (prepared.input_manifest_sha256,prepared.analysis_manifest_sha256)!=(entry['input_manifest_sha256'],entry['analysis_manifest_sha256']):
        raise ValueError('prepared input digest mismatch')
    links=resolve(raw)
    canonical=json.dumps(links,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if base.digest(canonical)!=audited['source_links_sha256']:raise ValueError('source links differ from frozen audit')
    prepared,receipt=filter_prepared(prepared,links)
    for key in ('removed_track_ids','counts','collisions','unchanged'):
        if receipt[key]!=audited[key]:raise ValueError('topology receipt differs from frozen audit')
    rows=original.reception_endpoints.build(raw,prepared,bias_hz=bias)
    reception,endpoints=original.reception_inputs(prepared,rows,detection,continuous)
    dependence=None
    if deduplicate:reception,dependence=deduplicate_matched_physical_pairs(reception,endpoints)
    banks,bank_receipt=base.build_prediction_banks(prepared.catalogue,prepared.candidate_indices,
        prepared.start_utc_ns,prepared.tracks,taus_s=np.array([0.]))
    out=dict(session_id=sid,finished=False,manifest_sha256=manifest_sha,inventory_sha256=inventory_sha,
        cache_sha256=entry['cache_sha256'],input_manifest_sha256=prepared.input_manifest_sha256,
        analysis_manifest_sha256=prepared.analysis_manifest_sha256,evidence_sha256=prepared.evidence_sha256,
        snapshot_digest=prepared.snapshot_digest,
        **model_hashes,topology_audit_sha256=audit_sha,topology_receipt=receipt,
        amendment_sha256=base.digest((HERE/'AMENDMENT_SOURCE_TOPOLOGY.md').read_bytes()),
        secondary_protocol_sha256=base.digest((HERE/'SECONDARY_PROTOCOL.md').read_bytes()),
        parameters=frequency['parameters'],prediction_receipt=asdict(bank_receipt),
        reception_endpoint_receipt=endpoints,dependence_sensitivity=dependence,branches={},
        protocol=dict(cohort='four frozen confirmation scans; separate outcome-blind topology amendment',
            budget_per_arm=160,priors=base.PRIORS,levels_km=base.LEVELS,timing_s=0,top_k=3,
            arms=base.ARMS,deduplicate_reception=deduplicate,
            secondary='D selection restricted to J-search evaluated points; no additional evaluations',
            truth_access='none; separate whole-cohort post-search reporter'))
    print('BANK_READY',sid,'retained',len(prepared.tracks),'removed',len(receipt['removed_track_ids']),flush=True)
    for name,(lat,lon,radius) in base.PRIORS.items():
        evaluator=original.RobustBranchEvaluator(banks,(lat,lon),reception,variance,frequency['parameters'])
        branch=dict(origin=[lat,lon],radius_km=radius,arms={})
        for arm in base.ARMS:
            result=original.search(evaluator.for_arm(arm),radius_km=radius,levels_km=base.LEVELS,budget_points=160)
            selected=result.global_incumbent
            chosen=evaluator.cache[(selected.east_km,selected.north_km)]
            branch['arms'][arm]=dict(selected=chosen,stop_reason=result.stop_reason,complete=result.complete,
                evaluated_points=len(result.all_evaluations),finest_points=len(result.finest_evaluations),trace=list(result.trace))
            print('ARM_DONE',sid,name,arm,flush=True)
        branch['point_components']=[{k:v for k,v in p.items() if k!='tracks'} for p in evaluator.cache.values()]
        branch['common_inventory_best']={arm:min(evaluator.cache.values(),key=lambda p:(p['scores'][arm],p['east_km'],p['north_km']))
            for arm in ('D','D_plus_detection','D_plus_geometry','D_plus_reversed_geometry')}
        branch['geometry_guided_doppler']=select_rx_guided_doppler(branch)
        out['branches'][name]=branch;out['elapsed_s']=time.monotonic()-start
        base.atomic(target,out)
    out['finished']=True;out['elapsed_s']=time.monotonic()-start
    files={name:HERE/name for name in ('run_topology_confirmation.py','run_confirmation.py','source_topology.py','guided_selection.py','reception_sensitivity.py')}
    files.update({name:original.LOCATION/name for name in ('run_robust_search.py','run_search.py','robust_core.py','reception_endpoints.py','measured_search.py')})
    out['code_sha256']={name:base.digest(path.read_bytes()) for name,path in files.items()}
    base.atomic(target,out);print('SCAN_DONE',sid,round(out['elapsed_s'],1),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--scan-index',type=int,required=True)
    parser.add_argument('--deduplicate-reception',action='store_true')
    args=parser.parse_args();run(args.scan_index,args.deduplicate_reception)
