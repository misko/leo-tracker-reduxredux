"""Full-authority metadata projection; no selected endpoints or reference ports."""
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
LOADER='reports/2026_10_09_position_error_iter105/run.py'
AUTHORITY='reports/2026_10_09_position_error_iter107/protocol.json'
PROJECTIONS='reports/2026_10_10_position_error_iter137/parity-bindings.json'
MODEL_FIELDS=('session_id','input_manifest_sha256','analysis_manifest_sha256','evidence_sha256',
              'prior_signature','score_signature','bank_signature','snapshot_sha256')
PHYSICAL_FIELDS=('input_digest','evidence_digest','score_signature','bank_signature','observation_order_signature')
MEMBERSHIP_FIELDS=('dataset','inventory_label','dataset_label','session_id','recording_manifest_sha256',
                   'uncompressed_sha256','legacy_labels','historical_groups','exposure','evaluation_status')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def project_member(authority, projections, *, repository, loader_sha256):
    original=authority['member']
    membership={k:original[k] for k in MEMBERSHIP_FIELDS if k in original}
    label=original.get('inventory_label',original.get('dataset_label'))
    dataset=original.get('dataset',authority.get('dataset'))
    result=dict(label=label,dataset=dataset,membership=membership,binding=None,
                binding_status='failed',binding_error=None,
                exposure='previously consumed development')
    try:
        if len(projections)!=1:raise ValueError('Missing or ambiguous clean projection')
        source=projections[0];session=original['session_id']
        if source['label']!=label or source['session_id']!=session:
            raise ValueError('Projected recording identity differs')
        for field in ('session_id','recording_manifest_sha256','uncompressed_sha256'):
            if source['membership'][field]!=original[field]:
                raise ValueError('Projected membership differs: '+field)
        model={k:source['model_identity'][k] for k in MODEL_FIELDS if k!='session_id'}
        model['session_id']=source['model_identity'].get('session_id',session)
        expected={k:source['expected_input_binding'][k] for k in PHYSICAL_FIELDS}
        if not all(isinstance(v,str) and v for v in (*model.values(),*expected.values())):
            raise ValueError('Incomplete physical identity')
        mint_manifest=original['recording_manifest_sha256']
        # A sealed unpublished member can have no publication-manifest digest at
        # mint time. Preserve that absence; the later physical input authority is
        # still required and must match projection, sanitized document and loader.
        if mint_manifest is not None and (not isinstance(mint_manifest,str) or not mint_manifest
                or model['input_manifest_sha256']!=mint_manifest):
            raise ValueError('Published mint manifest differs from physical input')
        if (model['session_id']!=session
                or expected['input_digest']!=model['input_manifest_sha256']
                or expected['evidence_digest']!=model['evidence_sha256']
                or expected['bank_signature']!=model['bank_signature']):
            raise ValueError('Inconsistent physical binding')
        relative=source['document_path'];root=Path(repository).resolve();path=(root/relative).resolve()
        if Path(relative).is_absolute() or not path.is_relative_to(root):
            raise ValueError('Document escapes repository')
        if sha(path)!=source['document_sha256']:raise ValueError('Sanitized document changed')
        document=json.loads(path.read_text())
        # Reject reference-bearing documents instead of importing their whole bytes
        # as an inference gate.137's saved documents already have exactly this shape.
        if set(document)!={'session_id','input_manifest_sha256','analysis_manifest_sha256',
                           'evidence_sha256','configuration'}:
            raise ValueError('Document is not the clean inference whitelist')
        if set(document['configuration'])!={'prior','scores','run'}:
            raise ValueError('Configuration whitelist differs')
        for field in ('session_id','input_manifest_sha256','analysis_manifest_sha256','evidence_sha256'):
            if document[field]!=model[field]:raise ValueError('Document identity differs: '+field)
        result['binding']=dict(session_id=session,loader_source=LOADER,loader_sha256=loader_sha256,
            document_path=relative,document_sha256=source['document_sha256'],
            model_identity=model,expected_input_binding=expected)
        result['binding_status']='complete'
        result['manifest_provenance']=('mint-publication-digest-matched' if mint_manifest is not None
            else 'mint-publication-digest-absent; later-model/document/physical-input-bound')
    except Exception as error:
        result['binding_error']=repr(error)
    return result


def prepare_bindings(repository=ROOT, *, authority_path=AUTHORITY,
                     projection_path=PROJECTIONS, loader_sha256=None):
    root=Path(repository)
    authority=json.loads((root/authority_path).read_text())['members']
    projections=json.loads((root/projection_path).read_text())['members']
    labels=[m['member'].get('inventory_label',m['member'].get('dataset_label')) for m in authority]
    sessions=[m['member']['session_id'] for m in authority]
    datasets=Counter(m['member'].get('dataset',m.get('dataset')) for m in authority)
    if (len(authority)!=193 or len(set(labels))!=193 or len(set(sessions))!=193
            or any(not isinstance(v,str) or not v for v in labels)
            or datasets!=Counter({'DS16':63,'DS17':51,'DS18':34,'POST18-development':45})):
        raise ValueError('Full193 authority membership differs')
    actual=sha(root/LOADER)
    if loader_sha256 is not None and actual!=loader_sha256:raise ValueError('Loader source differs')
    by_label=defaultdict(list)
    for row in projections:by_label[row.get('label')].append(row)
    return [project_member(m,by_label[label],repository=root,loader_sha256=actual)
            for m,label in zip(authority,labels,strict=True)]


def make_loader(entry, member, repository=ROOT):
    if member.get('binding_status')!='complete' or not member.get('binding'):
        raise ValueError('Member binding unavailable: '+str(member.get('binding_error')))
    root=Path(repository)
    environment=entry.make_loader(root,member['binding'])
    path=root/'reports/2026_10_09_position_error_iter131/inference_loader.py'
    spec=importlib.util.spec_from_file_location('clean131_for164',path)
    clean=importlib.util.module_from_spec(spec);spec.loader.exec_module(clean)
    # load_case supplies existing public backend hooks, never historical admission.
    return clean.InferenceLoader(root,environment.load_case)
