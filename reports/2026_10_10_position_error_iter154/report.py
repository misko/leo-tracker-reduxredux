"""All48 terminal admission before inherited reporting/reference ports."""
import hashlib
import json
import math
from pathlib import Path
from ports import ROOT, HERE, POLICY, load

TERMINAL = {'complete', 'failed', 'budget-exhausted', 'not-run-search-failed'}


def progression(summary):
    pairs=[row['arms']['fitted-c'] for row in summary['rows']]
    complete=summary['full_comparison_complete'] and len(pairs)==12
    deltas=[row['delta_km'] for row in pairs if 'delta_km' in row]
    finite=all(math.isfinite(value) for value in deltas)
    return dict(paired_fitted=len(deltas),complete_pair_coverage=bool(complete),
                mean_delta_km=sum(deltas)/len(deltas) if deltas else None,
                worst_regression_km=max(deltas) if deltas else None,
                passed=bool(complete and len(deltas)==12 and finite and sum(deltas)<0 and max(deltas)<=1))


def parity(old, new, path=''):
    """Postseal comparison only; never a region/start admission rule."""
    if isinstance(old,(int,float)) and not isinstance(old,bool) and isinstance(new,(int,float)) and not isinstance(new,bool):
        return [] if math.isfinite(old) and math.isfinite(new) and abs(old-new)<=1e-6 else [path]
    if isinstance(old,dict) and isinstance(new,dict):
        return [p for key in sorted(set(old)|set(new)) for p in parity(old.get(key),new.get(key),path+'/'+key)]
    if isinstance(old,list) and isinstance(new,list) and len(old)==len(new):
        return [p for i,(a,b) in enumerate(zip(old,new)) for p in parity(a,b,path+'/'+str(i))]
    return [] if old==new else [path]


def selected_state(row):
    fields=('vector','objective','clock_coefficients','joint_state','converged')
    return dict(status=row['status'],operational={arm:dict(
        fit={k:operation.get('fit',{}).get(k) for k in fields},
        selection={k:operation.get(k) for k in ('region_source','basin','accepted_stage','start')})
        for arm,operation in row.get('operational',{}).items()})


def transition_records(value, path=''):
    if isinstance(value,dict):
        records=[]
        for key,item in value.items():
            if key=='own_arm':records.append(dict(payload_path=path+'/'+key,receipt=item))
            elif key not in ('vector','clock_coefficients','association'):
                records.extend(transition_records(item,path+'/'+key))
        return records
    if isinstance(value,list) and len(value)<20:
        return [r for i,item in enumerate(value) for r in transition_records(item,path+'/'+str(i))]
    return []


def verify(plan, groups=('source_sha256', 'input_sha256')):
    for group in groups:
        for name, expected in plan[group].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError('closure changed ' + name)


def sealed_cells(plan, directory, canonical_digest):
    labels = [m['label'] for m in plan['members']]
    if len(labels) != 12 or len(set(labels)) != 12:
        raise ValueError('exact12 membership required')
    cells = {}
    for label in labels:
        for condition in POLICY['conditions']:
            digest = canonical_digest(dict(plan, execution_condition=condition))
            for branch in POLICY['discovery_policies']:
                path = Path(directory) / label / condition / branch / 'result.json'
                if not path.exists():
                    raise ValueError('all48 cells must seal before evaluation')
                row = json.loads(path.read_text())
                if row.get('protocol_sha256') != digest or row.get('label') != label or row.get('branch') != branch:
                    raise ValueError('foreign condition/member/branch')
                if row.get('status') not in TERMINAL or row.get('fallback_available') is not False:
                    raise ValueError('nonterminal or undeclared fallback')
                cells[(label, condition, branch)] = row
    return cells


def build(plan, directory, canonical_digest, *, evaluation_factory=None):
    verify(plan)
    cells = sealed_cells(plan, directory, canonical_digest)
    # No inherited dynamic source or reference port is opened before all48 seal.
    verify(plan, ('evaluation_source_sha256',))
    verify(plan, ('historical_control_sha256',))
    path = HERE.parent / '2026_10_09_position_error_iter129/report_cohort.py'
    api = load('report129_for154', path)
    coverage = load('report151_coverage154', HERE.parent/'2026_10_10_position_error_iter151/report.py')
    policies = {}
    for branch in POLICY['discovery_policies']:
        rows = []
        for member in plan['members']:
            discovery = json.loads((ROOT / member['sealed_search_path'] / 'result.json').read_text())
            phases = {'search': api.compact_receipt(discovery)}
            for condition, alias in (('control', 'native'), ('repair', 'fixed')):
                raw = cells[(member['label'], condition, branch)]
                phases[alias] = api.compact_receipt(raw)
                phases[alias]['operational'] = raw.get('operational', {})
                folder=Path(directory)/member['label']/condition/branch
                timings=[json.loads(p.read_text()) for p in sorted((folder/'slices').glob('*.done.json'))]
                expected=canonical_digest(dict(plan,execution_condition=condition))
                if any(t['protocol_sha256']!=expected or not math.isfinite(t['elapsed_s']) or t['elapsed_s']<0 for t in timings):
                    raise ValueError('foreign/nonfinite invocation timing')
                phases[alias]['recorded_invocation_elapsed_s']=sum(t['elapsed_s'] for t in timings) if timings else None
                stages,hashes=coverage.stage_coverage(Path(directory)/member['label']/condition,'',branch,expected)
                terminal=folder/'result.json'
                hashes[str(terminal)]=hashlib.sha256(terminal.read_bytes()).hexdigest()
                phases[alias]['stage_coverage']=stages
                phases[alias]['receipt_sha256']=hashes
                phases[alias]['transition_records']=[r for p in sorted((folder/'stages').glob('*.json')) if not p.name.endswith('.claim.json') for r in transition_records(json.loads(p.read_text()).get('value'))]
                if condition=='control':
                    old=json.loads((ROOT/member['sealed_search_path']).parent.joinpath(branch,'result.json').read_text())
                    phases[alias]['historical_parity_differences']=parity(selected_state(old),selected_state(raw))
            rows.append(dict(label=member['label'], dataset=member['dataset'], phases=phases))
        evaluate = (evaluation_factory or api.evaluation_callback)(plan, rows)
        summary = api.summarize(rows, evaluate=evaluate)
        for row in summary['rows']:
            for alias in ('native','fixed'):
                known={region['name']:region for region in row['regions'][alias]}
                row['regions'][alias]=[known.get('retained-'+str(i),dict(
                    name='retained-'+str(i),coverage='unavailable',calibration=None,
                    finals=None,attempts=None)) for i in range(3)]
        summary['comparison_labels'] = {'native': 'fresh-control', 'fixed': 'own-arm-repair'}
        summary['discovery_policy'] = branch
        summary['aggregates'] = api.aggregate(summary)
        summary['progression']=progression(summary)
        summary['cell_receipts']={row['label']:{alias:{key:row['phases'][alias][key] for key in ('stage_coverage','receipt_sha256','transition_records','recorded_invocation_elapsed_s') if key in row['phases'][alias]} for alias in ('native','fixed')} for row in rows}
        summary['historical_control_parity']={row['label']:row['phases']['native']['historical_parity_differences'] for row in rows}
        policies[branch] = summary
    return dict(all48_terminal=True, policies=policies,
                progression_passed=all(p['progression']['passed'] for p in policies.values()),
                scope='Consumed separate discovery policies; no reference-based policy selection')
