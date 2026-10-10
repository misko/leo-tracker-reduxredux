"""Terminal-only receipt coverage; evaluation supplied later through public port."""
import json
import importlib.util
import math
from pathlib import Path
from ports import PARENT,ROOT,sha

TERMINAL=('complete','failed','budget-exhausted')

def sealed_receipts(directory):
    reports={}
    for branch in ('native','zero'):
        path=Path(directory)/branch/'result.json'
        if not path.exists():raise ValueError('both branches must be terminal before reporting')
        row=json.loads(path.read_text())
        if row.get('status') not in TERMINAL:raise ValueError('nonterminal branch')
        reports[branch]=row
    if len({r['protocol_sha256'] for r in reports.values()})!=1:raise ValueError('foreign branch receipt')
    return reports

def coverage(reports):
    # Keep complete raw structures, so failed/unqualified alternative stages
    # cannot vanish through a winner-only projection.
    return {branch:dict(status=r['status'],regions=r.get('regions'),operational=r.get('operational'),attempts=r.get('attempts'),reasons=r.get('reasons'),reason=r.get('reason'),elapsed_s=r.get('elapsed_s'),slice=r.get('slice'),fallback_available=r.get('fallback_available',False)) for branch,r in reports.items()}

def stage_coverage(plan,directory,digest,reports):
    result={}
    for branch in ('native','zero'):
        stages=[];claims=[]
        folder=Path(directory)/branch/'stages'
        for path in sorted(folder.glob('*.json')):
            row=json.loads(path.read_text())
            if row.get('protocol_sha256')!=digest:raise ValueError('foreign stage coverage')
            if path.name.endswith('.claim.json'):claims.append(row);continue
            value=row['value']
            stages.append(dict(key=row['key'],status='failed' if value.get('result') is None else 'completed',reason=value.get('reason'),value=value,elapsed_s=row.get('elapsed_s')))
        expected=[]
        for index,region in enumerate(plan['branches'][branch]):
            name='retained-'+str(index);saved=reports[branch].get('regions',{}).get(name)
            expected.append(dict(name=name,point=region['point'],status='present-in-terminal' if saved is not None else 'unavailable-in-terminal',region=saved))
        completed_keys={r['key'] for r in stages}
        result[branch]=dict(expected_regions=expected,stage_receipts=stages,unresolved_claims=[r for r in claims if r['key'] not in completed_keys],attempt_inventory_status='terminal-complete' if reports[branch].get('regions') is not None else 'stage-only-partial')
    return result

def finite_equal(a,b,tolerance):
    if isinstance(a,bool) or isinstance(b,bool):return a is b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tolerance
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(finite_equal(x,y,tolerance) for x,y in zip(a,b))
    if isinstance(a,dict) and isinstance(b,dict):return set(a)==set(b) and all(finite_equal(a[k],b[k],tolerance) for k in a)
    return a==b

def source_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def control_parity(plan,records):
    authority=plan['control_parity'];path=ROOT/authority['result_path']
    if sha(path)!=authority['result_sha256']:raise ValueError('historical control result changed')
    old=json.loads(path.read_text());new=records['native'];arms={}
    for arm in ('fitted-c','zero-c'):
        a=new.get('operational',{}).get(arm);b=old.get('operational',{}).get(arm)
        if not a or not b:arms[arm]=dict(passed=False,reason='missing endpoint');continue
        metadata=('region_source','basin','start','accepted_stage')
        same_metadata=all(a.get(k)==b.get(k) for k in metadata)
        vector=a['fit']['vector'];previous=b['fit']['vector']
        delta=max((abs(x-y) for x,y in zip(vector,previous)),default=0)
        objective_delta=abs(a['fit']['objective']-b['fit']['objective'])
        states=('clock_coefficients','smooth_clock_coefficients','rf_drift_coefficients','knots_hz','joint_state')
        state_matches={k:k in a['fit'] and k in b['fit'] and finite_equal(a['fit'][k],b['fit'][k],authority['vector_absolute_tolerance']) for k in states}
        arms[arm]=dict(passed=finite_equal(vector,previous,authority['vector_absolute_tolerance']) and same_metadata and math.isfinite(objective_delta) and objective_delta<=authority['objective_absolute_tolerance'] and all(state_matches.values()) and bool(a['fit'].get('converged'))==bool(b['fit'].get('converged')),same_metadata=same_metadata,maximum_vector_delta=delta,objective_delta=objective_delta,full_state_matches=state_matches)
    return dict(passed=all(r['passed'] for r in arms.values()),arms=arms)

def build(plan,directory,protocol_digest,*,evaluation_factory=None):
    records=sealed_receipts(directory)
    if any(r['protocol_sha256']!=protocol_digest or r.get('branch')!=b or r.get('fallback_available') is not False for b,r in records.items()):raise ValueError('foreign/fallback result')
    from run import preflight
    preflight(plan)
    if not plan.get('evaluation_source_sha256'):raise ValueError('missing evaluation source closure')
    for name,expected in plan['evaluation_source_sha256'].items():
        if sha(ROOT/name)!=expected:raise ValueError('evaluation source changed '+name)
    # All evaluation imports/documents occur below the both-terminal gate.
    summary=source_module('summary123_for148',PARENT/'report_downstream.py')
    summary.BRANCHES=('native','zero')
    if evaluation_factory is None:
        import sys
        previous=sys.modules.get('report_downstream')
        try:
            sys.modules['report_downstream']=summary
            publication=source_module('publication123_for148',PARENT/'publish_downstream.py')
        finally:
            if previous is None:sys.modules.pop('report_downstream',None)
            else:sys.modules['report_downstream']=previous
        #123 evaluator expects native/fixed labels only at its seal check.
        def evaluation_factory(p,r):return publication.evaluation_callback(p,dict(native=r['native'],fixed=r['zero']))
    evaluate,binding=evaluation_factory(plan,records)
    result=summary.summarize(records,evaluate=evaluate)
    result.update(protocol_sha256=protocol_digest,evaluation_binding=binding,coverage=coverage(records),stage_coverage=stage_coverage(plan,directory,protocol_digest,records),slices=summary.slice_summary(directory,protocol_digest),control_parity=control_parity(plan,records))
    for branch,row in result['branches'].items():
        byname={r['name']:r for r in row['regions']}
        row['regions']=[byname.get('retained-'+str(i),dict(name='retained-'+str(i),status='unavailable-in-terminal',finals=None,calibration_available=None,association_available=None)) for i in range(3)]
    result['interpretation']='Consumed zero-led discovery sensitivity; final arms remain fitted-led downstream. Raw cross-bank objectives do not select policies. Failed control parity forbids claiming archived baseline equivalence.'
    return result
