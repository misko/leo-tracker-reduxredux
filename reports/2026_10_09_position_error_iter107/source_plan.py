"""Full193 metadata/model-source plan; no fits or numerical objectives."""
import collections
import datetime
import hashlib
import json
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def model_identity(document):
    diagnostics=document['diagnostics']
    return dict(session_id=document['session_id'],input_manifest_sha256=document['input_manifest_sha256'],
                analysis_manifest_sha256=document['analysis_manifest_sha256'],evidence_sha256=document['evidence_sha256'],
                prior_signature=canonical_digest(document['configuration']['prior']),
                score_signature=canonical_digest(document['configuration']['scores']),
                bank_signature=canonical_digest(diagnostics['bank']['retained_numbers']) if diagnostics.get('bank') else None,
                snapshot_sha256=diagnostics.get('snapshot_sha256'))


def compatible(left,right):
    return [key for key in left if left[key] is not None and right.get(key) is not None and left[key]!=right.get(key)]


def sanitize(document):
    result={k:document[k] for k in ('session_id','input_manifest_sha256','analysis_manifest_sha256','evidence_sha256','configuration')}
    result['diagnostics']={k:document['diagnostics'].get(k) for k in ('bank','snapshot_sha256','snapshot_collected_utc_ns','checkpoint_binding')}
    if result['diagnostics'].get('bank'):
        bank=result['diagnostics']['bank']
        result['diagnostics']['bank_receipt_sha256']=canonical_digest(bank)
        result['diagnostics']['bank']={'retained_numbers':bank.get('retained_numbers',[])}
    result['methods']=[dict(name=m['name'],points=[{k:p[k] for k in ('east_km','north_km','spacing_km','score') if k in p} for p in m.get('points',[])]) for m in document['methods']]
    return result


def source_identity_check(document):
    mismatches=[];missing=[]
    for name,expected in document['configuration'].get('source_digests',{}).items():
        path=ROOT/'src/leo'/name
        if not path.exists():missing.append(name)
        elif 'sha256:'+sha(path)!=expected:mismatches.append(name)
    return dict(current_source_mismatches=mismatches,missing_source_files=missing,
                source_identity_present=bool(document['configuration'].get('source_digests')),
                scope='Metadata comparison only; runtime input/bank/objective reconstruction not performed')


def main():
    authority=ROOT/'reports/2026_10_09_position_error_iter85/protocol.json';protocol=json.loads(authority.read_text())
    membership_path=ROOT/'reports/2026_10_09_position_error_iter89/membership.json';membership=json.loads(membership_path.read_text())
    original104=json.loads((ROOT/'reports/2026_10_09_position_error_iter104/source_bindings.json').read_text())
    research104=json.loads((ROOT/'reports/2026_10_09_position_error_iter104/research_source_bindings.json').read_text())
    failure_by_session=collections.defaultdict(list)
    for f in research104['failures']:failure_by_session[f['session_id']].append(f)
    values=HERE/'documents';values.mkdir(exist_ok=True);rows=[]
    for binding in protocol['members']:
        member=binding['member'];loader=binding['loader_binding'];root=Path('/srv/bulk/leo');sources=[];gaps=[]
        if loader.get('completion_path'):
            completion=json.loads((ROOT/loader['completion_path']).read_text())
            if completion['baseline_mode']=='isolated_standard_baseline':root=ROOT/'reports/2026_10_08_position_error_iter45/local/standard-baselines'
        baseline_path=loader.get('baseline_path')
        if baseline_path:baseline=json.loads((ROOT/baseline_path).read_text());baseline_receipt=dict(path=baseline_path,sha256=sha(ROOT/baseline_path))
        else:
            manifest=Hard60Store(root).status(member['session_id']).manifest
            if manifest is None:raise ValueError('Bound historical baseline missing:'+member['session_id'])
            baseline=manifest.document.model_dump(mode='json');baseline_receipt=dict(port='Hard60Store.status',root=str(root),document_sha256=manifest.document_sha256)
            if loader.get('baseline_document_digest'):assert canonical_digest(baseline)==loader['baseline_document_digest']
        identity=model_identity(baseline)
        assert baseline['input_manifest_sha256']==loader['effective_input_digest']
        original=baseline;original_receipt=baseline_receipt
        if loader['kind']=='legacy_ds17':
            path=ROOT/'reports/2026_10_08_position_error_iter01/published'/f"{member['inventory_label']}.json"
            if path.exists():original=json.loads(path.read_text());original_receipt=dict(path=str(path.relative_to(ROOT)),sha256=sha(path))
        elif loader['kind']=='legacy_ds16':
            manifest=Hard60Store(root).status(member['session_id']).manifest
            if manifest:original=manifest.document.model_dump(mode='json');original_receipt=dict(port='Hard60Store.status',root=str(root),document_sha256=manifest.document_sha256)
        if identity['bank_signature'] is None or identity['snapshot_sha256'] is None:
            inherited=model_identity(original)
            assert not compatible(identity,inherited)
            identity=inherited
        point_count=0
        for name,document,receipt in [('baseline',baseline,baseline_receipt)]+[(n,json.loads((ROOT/p).read_text()),dict(path=p,sha256=sha(ROOT/p))) for n,p in binding['regions'].items() if p]:
            mismatch=compatible(identity,model_identity(document))
            path=values/f"{member['inventory_label']}-{name}.json";payload=json.dumps(sanitize(document),sort_keys=True,indent=2)+'\n'
            path.write_text(payload)
            diagnostics=document['diagnostics'];point_count=max(point_count,sum(len(m.get('points',[])) for m in document['methods']))
            sources.append(dict(name=name,source=receipt,sanitized_path=str(path.relative_to(HERE)),sanitized_sha256=sha(path),model_identity=model_identity(document),model_identity_mismatches=mismatch,
                                configuration_signature=canonical_digest(document['configuration']['run']),
                                retained_count=len(diagnostics.get('retained_basins',[])),calibration_payloads=len(diagnostics.get('calibrations',{})),final_start_payloads=len(diagnostics.get('final_starts',[])),
                                checkpoint_binding=diagnostics.get('checkpoint_binding'),source_compatibility=source_identity_check(document)))
            sources[-1]['missing_model_identity_fields']=[k for k,v in model_identity(document).items() if v is None]
            if mismatch:gaps.append(dict(source=name,reason='regional-model-identity-mismatch',fields=mismatch))
        endpoint=ROOT/'reports/2026_10_09_position_error_iter85/results'/f"{member['inventory_label']}.json"
        data=json.loads(endpoint.read_text());assert data['status']=='complete'
        assert data['protocol_sha256']==sha(authority)
        endpoint_receipt=dict(path=str(endpoint.relative_to(ROOT)),sha256=sha(endpoint),available_stages=list(data['stages']),raw_stages=list(data['raw']),b7_arm_presence={a:a in data['stages']['B7'] for a in ('fitted-c','zero-c')},scope='Archived85endpoint; upstream result_source is ancestry, not this endpoint')
        metadata={k:member.get(k) for k in ('dataset','inventory_label','session_id','recording_manifest_sha256','uncompressed_sha256','legacy_labels','historical_groups','exposure','evaluation_status')}
        rows.append(dict(member=metadata,kind=loader['kind'],model_identity=identity,sources=sources,original_checkpoint_source=original_receipt,
                         original_checkpoint_binding=original['diagnostics'].get('checkpoint_binding'),original_configuration_signature=canonical_digest(original['configuration']['run']),
                         original_model_mismatches=compatible(identity,model_identity(original)),raw_input_root=str(root),baseline_endpoint=endpoint_receipt,
                         upstream_ancestry=dict(path=binding['result_source'],sha256=sha(ROOT/binding['result_source'])),failure_checkpoint_bindings=failure_by_session[member['session_id']],sampled_point_count=point_count,gaps=gaps))
    allow={s for g in membership['grouping']['groups'] if g['assignment']=='development' for s in g['session_ids']};assert len(allow)==45
    pilot105=json.loads((ROOT/'reports/2026_10_09_position_error_iter105/source-snapshot.json').read_text());pilots={m['session_id']:m for m in pilot105['members']}
    for member in membership['members']:
        if member['session_id'] not in allow:continue
        sources=[]
        for name,cls in [('B7',B7Store),('hard60',Hard60Store)]:
            manifest=cls(Path('/srv/bulk/leo')).status(member['session_id']).manifest
            if manifest is None:continue
            document=manifest.document.model_dump(mode='json');path=values/f"{member['dataset_label']}-{name}.json";payload=json.dumps(sanitize(document),sort_keys=True,indent=2)+'\n'
            path.write_text(payload)
            sources.append(dict(name=name,port=cls.__name__+'.status',document_sha256=manifest.document_sha256,sanitized_path=str(path.relative_to(HERE)),sanitized_sha256=sha(path),model_identity=model_identity(document),source_compatibility=source_identity_check(document),checkpoint_binding=document['diagnostics'].get('checkpoint_binding')))
        pilot=pilots.get(member['session_id'])
        rows.append(dict(member={k:member.get(k) for k in ('dataset_label','session_id','recording_manifest_sha256','uncompressed_sha256','exposure')},dataset='POST18-development',sources=sources,gaps=[] if sources else ['No publication'],
                         pilot105_source=None if pilot is None else dict(snapshot_sha256=sha(ROOT/'reports/2026_10_09_position_error_iter105/source-snapshot.json'),label=pilot['label'],existing_coarse_points=pilot['available_coarse_point_count'],reuse_condition='Only exact unchanged105policy/source/input/model; complete105baseline/candidate remain consumed development results'),
                         baseline_requirement='Fresh matchedB7 unless exact archived/current-policy parity independently demonstrated'))
    assert len(rows)==193 and len({r['member']['session_id'] for r in rows})==193
    result=dict(created_utc=datetime.datetime.now(datetime.UTC).isoformat(),authorities={str(p.relative_to(ROOT)):sha(p) for p in [authority,membership_path,ROOT/'reports/2026_10_09_position_error_iter104/source_bindings.json',ROOT/'reports/2026_10_09_position_error_iter104/research_source_bindings.json']},members=rows,
                scope='Metadata only; no fits/objective evaluation/reference-error extraction/reserve access. All45development publication metadata accessed supplementally, previously opened101; no unseen validation claim')
    (HERE/'source-plan.json').write_text(json.dumps(result,indent=2)+'\n')
    print('members',len(rows),'historical model mismatches',sum(bool(r.get('gaps')) for r in rows[:148]),'historical endpoints',148,'historical failure entries',len(research104['failures']))


if __name__=='__main__':main()
