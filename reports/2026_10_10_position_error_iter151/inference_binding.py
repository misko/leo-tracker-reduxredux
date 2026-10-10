"""Metadata-only131 policy generalized identically across twelve members."""
import copy
import json
from ports import HERE,ROOT,load

MODEL_FIELDS=('session_id','input_manifest_sha256','analysis_manifest_sha256','evidence_sha256','prior_signature','score_signature','bank_signature','snapshot_sha256')
PHYSICAL_FIELDS=('input_digest','evidence_digest','score_signature','bank_signature','observation_order_signature')

def projected_binding(member,source,baseline,document):
    """Never project geographic reference, error, endpoint or fit fields."""
    if source['member']['session_id']!=member['membership']['session_id']:raise ValueError('recording session changed')
    if baseline.get('status')!='complete' or baseline.get('label')!=member['label']:raise ValueError('physical authority unavailable')
    model={key:source['model_identity'][key] for key in MODEL_FIELDS}
    expected={key:baseline['input_binding'][key] for key in PHYSICAL_FIELDS}
    if not all(model.values()) or not all(expected.values()):raise ValueError('incomplete inference authority')
    for key in ('session_id','input_manifest_sha256','analysis_manifest_sha256','evidence_sha256'):
        if document[key]!=model[key]:raise ValueError('inference identity differs '+key)
    if expected['input_digest']!=document['input_manifest_sha256'] or expected['evidence_digest']!=document['evidence_sha256'] or expected['bank_signature']!=model['bank_signature']:raise ValueError('physical signature changed')
    return dict(copy.deepcopy(member['binding']),model_identity=model,expected_input_binding=expected)

def prepare_bindings(members):
    previous=ROOT/'reports/2026_10_09_position_error_iter107/protocol.json'
    source_members=json.loads(previous.read_text())['members']
    inference=load('inference131_metadata151',HERE.parent/'2026_10_09_position_error_iter131/inference_loader.py')
    result=[]
    for member in members:
        matches=[s for s in source_members if s['member'].get('inventory_label',s['member'].get('dataset_label'))==member['label']]
        if len(matches)!=1:raise ValueError('ambiguous inference member')
        baseline=json.loads((previous.parent/'results'/member['label']/'baseline.json').read_text())
        document=inference.inference_document(json.loads((ROOT/member['binding']['document_path']).read_text()))
        result.append(dict(copy.deepcopy(member),binding=projected_binding(member,matches[0],baseline,document)))
    return result

def make_loader(entry,member):
    # make_loader constructs the existing105 backend environment only; its
    # historical load_case is passed as a hooks carrier, never called by131.
    environment=entry.make_loader(ROOT,member['binding'])
    inference=load('inference131_runtime151',HERE.parent/'2026_10_09_position_error_iter131/inference_loader.py')
    return inference.InferenceLoader(ROOT,environment.load_case)
