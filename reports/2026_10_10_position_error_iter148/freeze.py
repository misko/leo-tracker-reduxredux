"""Unexecuted metadata freezer; no recording models or automatic protocol write."""
import argparse
import json
from pathlib import Path
from ports import HERE,ROOT,PARENT,sha,admit,evaluation_sources

SEARCH=ROOT/'reports/2026_10_09_position_error_iter116'

def prepare():
    integrity=json.loads((SEARCH/'SEARCH_INTEGRITY.json').read_text())
    inputs={}
    historical123=PARENT/'protocol.json'
    if sha(historical123)!='96b45034497dd50b0134a95510190d577d9e192928b9880a6830ee9cec79bb43':raise ValueError('123 historical protocol changed')
    historical_cache=json.loads(historical123.read_text())['input_sha256']
    inputs[str(historical123.relative_to(ROOT))]=sha(historical123)
    def pinned(path):
        expected=integrity['receipt_sha256'].get(str(path)) or integrity['artifact_sha256'].get(str(path.relative_to(SEARCH)))
        if expected is None or sha(path)!=expected:raise ValueError('historical hash mismatch '+str(path))
        inputs[str(path.relative_to(ROOT))]=expected
        return json.loads(path.read_text())
    parent=pinned(SEARCH/'protocol.json');terminal=pinned(SEARCH/'results/DS18-022/result.json')
    if not terminal['complete'] or terminal['point_failure_count']!=0:raise ValueError('incomplete search')
    inputs.update(parent['input_sha256'])
    imported=json.loads((SEARCH/'coarse-import.json').read_text())
    seeds={tuple(r['point']):r['receipt']['result']['bootstrap'] for r in imported['records']}
    branches={};retrospective={};historically_bound={}
    for branch,arm in [('native','fitted-c'),('zero','zero-c')]:
        events=[pinned(p)['event'] for p in sorted((SEARCH/'results/DS18-022/traces'/f'{arm}-native').glob('*.json'))]
        if events[-1]['event']!='ranks':raise ValueError('unsealed trace')
        trace={(e['east'],e['north']):e['score'] for e in events if e['event']=='evaluated'}
        if len(trace)!=400:raise ValueError('incomplete native trace')
        regions=terminal['searches'][arm+':native']['regions']
        if len(regions)!=3:raise ValueError('retention count changed')
        wanted={(r['east_km'],r['north_km']) for r in regions};fits={}
        for path in sorted((SEARCH/'results/DS18-022/points').glob('*.json')):
            if path.name.endswith('.claim.json'):continue
            row=json.loads(path.read_text());key=row['key']
            point=tuple(key[1]) if key[0]=='bootstrap' else tuple(key[1:3])
            if point not in wanted:continue
            if row['protocol_sha256']!=terminal['protocol_sha256'] or row['status']!='complete':raise ValueError('foreign/incomplete point')
            if key[0]=='bootstrap':
                if point in seeds and seeds[point]!=row['value']:raise ValueError('bootstrap conflict')
                seeds[point]=row['value']
            elif key[0]=='point' and key[3]==arm:
                fit=row['value']['fit']
                if abs(fit['objective']-row['value']['scores']['native']['objective'])>1e-6:raise ValueError('native coarse score mismatch')
                fits[point]=fit
            else:continue
            name=str(path.relative_to(ROOT));inputs[name]=sha(path)
            if name in historical_cache:
                if inputs[name]!=historical_cache[name]:raise ValueError('123 bound coarse bytes changed')
                historically_bound[name]=inputs[name]
            else:retrospective[name]=inputs[name]
        branches[branch]=[dict(point=[r['east_km'],r['north_km']],discovery_score=r['score'],spacing_km=r['spacing_km'],original=admit([r['east_km'],r['north_km']],seeds[(r['east_km'],r['north_km'])],fits[(r['east_km'],r['north_km'])],len(imported['bank_numbers']),arm,trace[(r['east_km'],r['north_km'])])) for r in regions]
    sources=dict(parent['source_sha256'])
    evaluation_closure=evaluation_sources()
    sources.update(evaluation_closure)
    for folder in (PARENT,HERE):
        for path in folder.glob('*.py'):sources[str(path.relative_to(ROOT))]=sha(path)
    for path in (HERE/'PLAN.md',SEARCH/'SEARCH_INTEGRITY.json'):inputs[str(path.relative_to(ROOT))]=sha(path)
    for group in (sources,inputs):
        for name,expected in group.items():
            if sha(ROOT/name)!=expected:raise ValueError('closure changed '+name)
    baseline=PARENT/'results/native/result.json'
    authority=json.loads((PARENT/'DOWNSTREAM_INTEGRITY.json').read_text())
    if sha(baseline)!=authority['raw_files']['results/native/result.json']['sha256']:raise ValueError('123 control result changed')
    inputs[str(baseline.relative_to(ROOT))]=sha(baseline)
    # Explicit report closure is also identifiable independently of inference.
    # Insert in returned protocol without changing scientific policy.
    return dict(binding=parent['binding'],identity=parent['identity'],branches=branches,evaluation_source_sha256=evaluation_closure,source_sha256=sources,input_sha256=inputs,retrospective_coarse_sha256=retrospective,historically_123_bound_coarse_sha256=historically_bound,control_parity=dict(result_path=str(baseline.relative_to(ROOT)),result_sha256=sha(baseline),vector_absolute_tolerance=1e-6,objective_absolute_tolerance=1e-6,require_same_selection_metadata=True),scope='Consumed DS18-022; zero-led native discovery sensitivity, not independence',policy=dict(discovery={'native':'fitted-c-native','zero':'zero-c-native'},regions=3,local_radius_km=25,maximum_slices_per_branch=6,slice_seconds=500,maximum_workers=2,threads=1,final_arms=['fitted-c','zero-c'],fresh_control=True,cross_branch_selection=False,no_new_search=True))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true');args=parser.parse_args()
    if not args.write:raise SystemExit('Explicit --write required after review/authorization')
    value=prepare()
    with (HERE/'protocol.json').open('x') as f:json.dump(value,f,indent=2,allow_nan=False)
