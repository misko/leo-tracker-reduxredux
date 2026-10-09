"""Snapshot semantically addressed existing stages through the public get port."""
import datetime
import hashlib
import json
from dataclasses import replace
from pathlib import Path

from leo.application.hard60_b7 import B7_POLICY
from leo.application.hard60_runner import Hard60Configuration
from leo.application.regional_position_runner import json_value
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store
from inventory import pilot_members

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def main():
    authority=ROOT/'reports/2026_10_09_position_error_iter104/source_bindings.json'
    bindings=json.loads(authority.read_text())
    selected={m['session_id'] for m in pilot_members(bindings)}
    members=[m for m in bindings['members'] if m['session_id'] in selected]
    assert len(members)==5
    output=[]
    directory=HERE/'source-values';directory.mkdir(exist_ok=True)
    for member in members:
        names={f['source'] for f in member['failure_bindings']};assert len(names)==1
        name=names.pop();cls=B7Store if name=='B7' else Hard60Store
        manifest=cls(Path('/srv/bulk/leo')).status(member['session_id']).manifest
        document=manifest.document.model_dump(mode='json');d=document['diagnostics']
        binding=d['checkpoint_binding'];store=RegionalCheckpointStore(Path('/srv/bulk/leo'),member['session_id'],binding)
        points={f"point:{p['east_km']:g}:{p['north_km']:g}" for method in document['methods'] for p in method.get('points',[])}
        points.update(f['basin'] for f in member['failure_bindings'])
        config=Hard60Configuration(**{k:tuple(v) if k in ('levels_km','final_starts') else v for k,v in document['configuration']['run'].items()})
        keys={};coarse_keys=set()
        for point in points:
            if name=='B7':keys['b7-shared:'+point]='shared-coarse';coarse_keys.add('b7-shared:'+point)
            for separation in (12.5,25.,50.):
                prefix=canonical_digest(json_value(replace(config,basin_separation_km=separation)))+':'
                keys[prefix+point]='coarse';coarse_keys.add(prefix+point)
                for origin in (point,'recovery:'+point):
                    for suffix in ('calibration','association','coarse'):
                        keys[prefix+origin+':'+suffix]='regional-or-recovery'
                    for arm in ('fitted-c','zero-c'):
                        for start in config.final_starts:keys[prefix+origin+':'+arm+':'+start]='regional-final'
        for stage in B7_POLICY['stages']:
            for arm in ('fitted-c','zero-c'):keys[canonical_digest(B7_POLICY)+':b7:'+stage+':'+arm]='joint'
        receipts=[]
        for key,kind in sorted(keys.items()):
            value=store.get(key)
            row=dict(key=key,kind=kind,available=value is not None)
            if value is not None:
                filename=hashlib.sha256((member['session_id']+key).encode()).hexdigest()+'.json'
                payload=json.dumps(value,sort_keys=True,separators=(',',':')).encode()+b'\n'
                path=directory/filename
                if path.exists():assert path.read_bytes()==payload
                else:path.write_bytes(payload)
                row.update(value_sha256=canonical_digest(value),file=str(path.relative_to(HERE)),file_sha256=hashlib.sha256(payload).hexdigest(),has_result=value.get('result') is not None)
            receipts.append(row)
        available_points={k.removeprefix('b7-shared:') if k.startswith('b7-shared:') else k.split(':',2)[2] for k in coarse_keys if any(r['key']==k and r.get('has_result') for r in receipts)}
        row=dict(label=member['label'],session_id=member['session_id'],source_version=name,document_sha256=manifest.document_sha256,
                 input_manifest_sha256=document['input_manifest_sha256'],analysis_manifest_sha256=document['analysis_manifest_sha256'],evidence_sha256=document['evidence_sha256'],
                 checkpoint_binding=binding,configuration=document['configuration'],snapshot_sha256=d.get('snapshot_sha256'),snapshot_collected_utc_ns=d.get('snapshot_collected_utc_ns'),bank=d.get('bank'),
                 sampled_point_count=len(points),available_coarse_point_count=len(available_points),receipts=receipts,
                 checkpoints={r['key']:{k:r[k] for k in ('file','file_sha256','value_sha256')} for r in receipts if r['available']},
                 missing_keys=[r['key'] for r in receipts if not r['available']],
                 compatibility=dict(eligible=False,reasons=['Exact input/model/bank/runtime-source compatibility requires driver preflight; no automatic old-hard60 key alias']))
        row['document']={k:document[k] for k in ('session_id','input_manifest_sha256','analysis_manifest_sha256','evidence_sha256','configuration')}
        row['document']['diagnostics']={k:d.get(k) for k in ('snapshot_sha256','snapshot_collected_utc_ns','bank','checkpoint_binding')}
        row['document']['methods']=[dict(name=m['name'],points=[{k:p[k] for k in ('east_km','north_km','spacing_km','score') if k in p} for p in m.get('points',[])]) for m in document['methods']]
        row['source_files']={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT/'src/leo/application/hard60_runner.py',ROOT/'src/leo/application/hard60_b7.py',ROOT/'src/leo/application/hard60_recovery.py')}
        output.append(row)
        print(member['label'],name,'points',len(points),'coarse available',len(available_points),'existing stages',sum(r['available'] for r in receipts),flush=True)
    result=dict(created_utc=datetime.datetime.now(datetime.UTC).isoformat(),authority_sha256=hashlib.sha256(authority.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),members=output,
                scope='Public get/status only; five frozen development failures; no fits, model evaluation, reserves, production writes or reference-error extraction. Semantic grid points constrain discovery; unsampled/recovery-only points may still be missing.')
    (HERE/'source-snapshot.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
