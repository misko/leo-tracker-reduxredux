"""Strict postseal receipt collection; no reference or scientific imports."""
import hashlib
import json
import math
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUTHORITY = ROOT / 'reports/2026_10_09_position_error_iter107/protocol.json'
AUTHORITY_SHA = '24df105bf4618947162f9438ea2a77115d1baa134a00b5f7b48279942848d227'

MODES = ('full', 'train0', 'train1')
ARMS = ('zero-c', 'fitted-c')
TERMINAL = {'qualified', 'unqualified', 'failed'}


def collect(plan, digest, directory):
    """Return {cells, members, raw_sha256} only after all 72 cells authenticate.

    cells is keyed by (label, mode, arm); paths in raw_sha256 are relative to
    directory. This function never opens a reference/evaluation authority.
    """
    directory = Path(directory)
    labels = [m['label'] for m in plan['members']]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError('exact twelve unique members required')
    cells, members, hashes = {}, {}, {}

    def read(path, identity):
        content = path.read_bytes()
        value = json.loads(content)
        if any(value.get(key) != expected for key, expected in identity.items()):
            raise ValueError('foreign receipt or claim: ' + str(path))
        hashes[str(path.relative_to(directory))] = hashlib.sha256(content).hexdigest()
        return value

    for label in labels:
        folder = directory / label
        identity = dict(label=label, protocol_sha256=digest)
        read(folder / 'claim.json', identity)
        member = read(folder / 'result.json', identity)
        if member.get('status') not in ('complete', 'failed'):
            raise ValueError('member is not terminal: ' + label)
        expected_keys = {mode + '--' + arm for mode in MODES for arm in ARMS}
        if set(member.get('cells', {})) != expected_keys:
            raise ValueError('incomplete member cell inventory: ' + label)
        qualified = True
        for mode in MODES:
            for arm in ARMS:
                key = mode + '--' + arm
                binding = dict(identity, mode=mode, arm=arm)
                path = folder / (key + '.json')
                read(folder / (key + '.claim.json'), binding)
                cell = read(path, binding)
                if cell.get('status') not in TERMINAL:
                    raise ValueError('cell is not terminal: ' + key)
                record = member['cells'][key]
                if record.get('status') != cell['status'] or record.get('sha256') != hashes[str(path.relative_to(directory))]:
                    raise ValueError('member/cell receipt differs: ' + key)
                # Authenticate the declared location without permitting path escape.
                declared = Path(record['path'])
                if not declared.is_absolute():
                    declared = folder / declared
                if declared.resolve() != path.resolve():
                    raise ValueError('member cell path differs: ' + key)
                cells[(label, mode, arm)] = cell
                qualified &= cell['status'] == 'qualified'
        if (member['status'] == 'complete') != qualified:
            raise ValueError('member qualification summary differs: ' + label)
        members[label] = member
    datasets = {m['label']: m['dataset'] for m in plan['members']}
    ordered = [dict(cell, dataset=datasets[label])
               for (label, mode, arm), cell in cells.items()]
    return dict(cells=ordered, members=members, raw_sha256=hashes)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_evaluation(plan, digest, collection):
    """Metadata-only evaluation manifest; caller publishes before evaluate()."""
    if len(collection['cells']) != 72 or len(collection['members']) != 12:
        raise ValueError('full sealed collection required')
    previous = json.loads((ROOT / 'reports/2026_10_10_position_error_iter154/protocol.json').read_text())
    sources = dict(previous['evaluation_source_sha256'])
    sources[str(Path(__file__).resolve().relative_to(ROOT))] = sha(__file__)
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError('evaluation source differs: ' + name)
    if sha(AUTHORITY) != AUTHORITY_SHA:
        raise ValueError('evaluation authority differs')
    return dict(inference_protocol_sha256=digest, authority_sha256=AUTHORITY_SHA,
                evaluation_source_sha256=sources, raw_sha256=collection['raw_sha256'],
                labels=[m['label'] for m in plan['members']], references='evaluation only')


def evaluate(plan, digest, directory, evaluation_plan, *, evaluation_factory=None):
    """Reauthenticate all receipts before opening any evaluation-coordinate port."""
    collection = collect(plan, digest, directory)
    if (evaluation_plan['inference_protocol_sha256'] != digest
            or evaluation_plan['raw_sha256'] != collection['raw_sha256']
            or evaluation_plan['labels'] != [m['label'] for m in plan['members']]
            or evaluation_plan['authority_sha256'] != AUTHORITY_SHA):
        raise ValueError('evaluation manifest differs')
    for group in ('source_sha256', 'input_sha256'):
        for name, expected in plan[group].items():
            if sha(ROOT / name) != expected:
                raise ValueError('inference closure differs: ' + name)
    for name, expected in evaluation_plan['evaluation_source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('evaluation source differs: ' + name)
    if sha(AUTHORITY) != AUTHORITY_SHA:
        raise ValueError('evaluation authority differs')
    if evaluation_factory is None:
        api = runpy.run_path(str(AUTHORITY.parent / 'report.py'))
        authority = json.loads(AUTHORITY.read_text())
        inventory = {m['member'].get('inventory_label', m['member'].get('dataset_label')): m
                     for m in authority['members']}
        requested = {m['label']: m for m in plan['members']}
        documents = {}

        def evaluation_factory(cell):
            label = cell['label']
            if label not in documents:
                binding = requested[label]['binding']
                if inventory[label]['member']['session_id'] != binding['session_id']:
                    raise ValueError('evaluation session differs')
                document = api['evaluation_document'](inventory[label])
                if sha(ROOT / binding['document_path']) != binding['document_sha256']:
                    raise ValueError('sanitized evaluation binding differs')
                sanitized = json.loads((ROOT / binding['document_path']).read_text())
                for key in ('session_id', 'input_manifest_sha256', 'analysis_manifest_sha256', 'evidence_sha256'):
                    if document[key] != sanitized[key]:
                        raise ValueError('evaluation identity differs: ' + key)
                if document['configuration']['prior'] != sanitized['configuration']['prior']:
                    raise ValueError('evaluation prior differs')
                documents[label] = document
            return api['evaluate_fit'](dict(fit=cell['solver']), documents[label])['error_km']
    rows = []
    for cell in collection['cells']:
        row = dict(cell, error_km=None, evaluation_error=None)
        if cell['status'] == 'qualified':
            try:
                row['error_km'] = evaluation_factory(cell)
                if not math.isfinite(row['error_km']) or row['error_km'] < 0:
                    raise ValueError('invalid geographic evaluation error')
            except Exception as error:
                row['error_km'] = None
                row['evaluation_error'] = repr(error)
        rows.append(row)
    return dict(rows=rows, raw_sha256=collection['raw_sha256'])
