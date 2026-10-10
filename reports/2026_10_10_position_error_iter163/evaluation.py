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

HYPOTHESES = ('zero-c', 'fitted-c')
MODES = ('train0', 'train1')
ARMS = ('zero-c', 'fitted-c')
TERMINAL = {'qualified', 'unqualified', 'failed'}



def collect(plan, digest, directory, *, choose=None):
    """Authenticate exact600 files and reproduce training-only selection."""
    directory = Path(directory)
    labels = [m['label'] for m in plan['members']]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError('exact twelve unique members required')
    if choose is None:
        path = HERE/'selection.py'
        expected = plan['source_sha256'][str(path.relative_to(ROOT))]
        if sha(path) != expected:
            raise ValueError('selection source differs')
        choose = runpy.run_path(str(path))['choose']
    hashes, cells, attempts, members = {}, [], [], {}
    def read(path, identity):
        content = path.read_bytes(); value = json.loads(content)
        if any(value.get(k) != v for k,v in identity.items()):
            raise ValueError('foreign receipt/claim: '+str(path))
        hashes[str(path.relative_to(directory))] = hashlib.sha256(content).hexdigest()
        return value
    for member in plan['members']:
        label = member['label']; folder = directory/label
        identity = dict(label=label, protocol_sha256=digest)
        read(folder/'claim.json', identity)
        terminal = read(folder/'result.json', identity)
        keys = [h+'--'+m+'--'+a for h in HYPOTHESES for m in MODES for a in ARMS]
        expected_attempts = {k+'--start-'+s for k in keys for s in ARMS}
        if (terminal.get('status') not in ('complete','failed')
                or set(terminal.get('cells',{})) != set(keys)
                or set(terminal.get('attempts',{})) != expected_attempts):
            raise ValueError('incomplete terminal inventory')
        qualified = True
        def artifact(key, bound, group):
            path = folder/(key+'.json')
            read(folder/(key+'.claim.json'), bound)
            row = read(path, bound); record = terminal[group][key]
            if row.get('status') not in TERMINAL or record.get('status') != row['status']:
                raise ValueError('terminal status differs')
            if record.get('sha256') != hashes[str(path.relative_to(directory))]:
                raise ValueError('member receipt hash differs')
            declared = Path(record['path'])
            if not declared.is_absolute(): declared = folder/declared
            if declared.resolve() != path.resolve():
                raise ValueError('receipt path differs')
            return row
        for key in keys:
            h,m,a = key.split('--')
            bound = dict(identity,hypothesis=h,mode=m,arm=a)
            cell = artifact(key,bound,'cells')
            original_attempts = {}
            for source in ARMS:
                attempt = artifact(key+'--start-'+source,
                    dict(bound,start_source=source),'attempts')
                original_attempts[source] = attempt
                attempts.append(dict(attempt,dataset=member['dataset']))
            candidates = cell.get('candidates',{})
            if set(candidates) != {'control',*ARMS}:
                raise ValueError('candidate inventory differs')
            for source in ARMS:
                if candidates[source] != original_attempts[source]:
                    raise ValueError('embedded attempt differs')
            control = candidates['control']
            if 'control_audit' in cell and cell['control_audit'] != control:
                raise ValueError('embedded control audit differs')
            binding = member['controls'][key]
            control_path = ROOT/binding['raw_path']
            claim_path = ROOT/binding['claim_path']
            if sha(control_path) != binding['sha256'] or sha(claim_path) != binding['claim_sha256']:
                raise ValueError('retained control bytes differ')
            raw = json.loads(control_path.read_text())
            claim = json.loads(claim_path.read_text())
            old_identity = dict(bound,protocol_sha256=binding['protocol_sha256'])
            if any(raw.get(k)!=v or claim.get(k)!=v for k,v in old_identity.items()):
                raise ValueError('foreign retained control')
            if control.get('status') == 'qualified' and control.get('solver') != raw['solver']:
                raise ValueError('control solver differs')
            if control.get('status') == 'qualified':
                objective = control['audit']['objective']
                if (not math.isfinite(objective)
                        or abs(objective-raw['solver']['objective']) > 1e-6):
                    raise ValueError('retained control objective differs')
            winner = choose(candidates)
            selected = cell.get('selected_source')
            if selected is not None and selected != winner:
                raise ValueError('training selection differs')
            if cell['status'] == 'qualified':
                if selected is None or selected != winner:
                    raise ValueError('qualified cell lacks reproducible winner')
                chosen = candidates[selected]
                if cell.get('solver') != chosen.get('solver') or cell.get('audit') != chosen.get('audit'):
                    raise ValueError('selected state/audit differs')
            if cell.get('control_retained') != (selected == 'control'):
                raise ValueError('retained-control label differs')
            qualified &= cell['status'] == 'qualified'
            cells.append(dict(cell,dataset=member['dataset']))
        if (terminal['status']=='complete') != qualified:
            raise ValueError('member qualification summary differs')
        members[label] = terminal
    if len(hashes) != 600:
        raise ValueError('exact600 receipt inventory required')
    return dict(cells=cells,attempts=attempts,members=members,raw_sha256=hashes)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_evaluation(plan, digest, collection):
    """Metadata-only evaluation manifest; caller publishes before evaluate()."""
    if (len(collection['cells']) != 96 or len(collection['attempts']) != 192
            or len(collection['members']) != 12):
        raise ValueError('full sealed collection required')
    previous_path = ROOT / 'reports/2026_10_10_position_error_iter154/protocol.json'
    if sha(previous_path) != 'f148eb97a3e789b297c842bb5329bd0162f2e46490c18e056d21adb30d0a6f31':
        raise ValueError('evaluation-source authority changed')
    previous = json.loads(previous_path.read_text())
    sources = dict(previous['evaluation_source_sha256'])
    prior_evaluation = HERE.parent/'2026_10_10_position_error_iter162/evaluation_protocol.json'
    if sha(prior_evaluation) != '845302f60591c036b17ad8b4667b4ee139c4ac1743f52ba2ebdff55a50ccf084':
        raise ValueError('162 evaluation authority changed')
    prior_sources = json.loads(prior_evaluation.read_text())['evaluation_source_sha256']
    prior_report = HERE.parent/'2026_10_10_position_error_iter162/report.py'
    report_key = str(prior_report.relative_to(ROOT))
    expected_report = prior_sources[report_key]
    if sha(prior_report) != expected_report:
        raise ValueError('162 report source differs')
    sources[report_key] = expected_report
    sources[str(Path(__file__).resolve().relative_to(ROOT))] = sha(__file__)
    for name in ('EVALUATION_PLAN.md', 'report.py', 'test_evaluation.py', 'test_report.py'):
        path = HERE/name
        sources[str(path.relative_to(ROOT))] = sha(path)
    for name, expected in sources.items():
        if sha(ROOT / name) != expected:
            raise ValueError('evaluation source differs: ' + name)
    if sha(AUTHORITY) != AUTHORITY_SHA:
        raise ValueError('evaluation authority differs')
    return dict(inference_protocol_sha256=digest, authority_sha256=AUTHORITY_SHA,
                evaluation_source_sha256=sources, raw_sha256=collection['raw_sha256'],
                input_sha256={str((HERE/'PREFERENCES.json').relative_to(ROOT)):
                              sha(HERE/'PREFERENCES.json'),
                              str((HERE.parent/'2026_10_10_position_error_iter162/PREFERENCES.json').relative_to(ROOT)):
                              sha(HERE.parent/'2026_10_10_position_error_iter162/PREFERENCES.json')},
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
    expected_preference_path = str((HERE/'PREFERENCES.json').relative_to(ROOT))
    prior_preference_path = str((HERE.parent/'2026_10_10_position_error_iter162/PREFERENCES.json').relative_to(ROOT))
    if set(evaluation_plan['input_sha256']) != {expected_preference_path, prior_preference_path}:
        raise ValueError('exact frozen preference authority required')
    for name, expected in evaluation_plan['input_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('evaluation preference input differs: ' + name)
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
