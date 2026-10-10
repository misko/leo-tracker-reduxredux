"""Receipt-only coarse-bank feasibility audit; no numerical model imports."""
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'2026_10_09_position_error_iter116'

def digest(raw):return hashlib.sha256(raw).hexdigest()

def ordinary_radius(spacing_km):
    if not math.isfinite(spacing_km) or spacing_km <= 0:
        raise ValueError('positive finite spacing required')
    return max(25.0, spacing_km / math.sqrt(2))

def retain(rows,expected=400):
    if len(rows)!=expected:raise ValueError('incomplete point domain')
    if len({(p['east_km'],p['north_km']) for p in rows})!=len(rows):raise ValueError('duplicate point')
    if any(not all(math.isfinite(p[k]) for k in ('east_km','north_km','score','spacing_km')) for p in rows):raise ValueError('nonfinite point')
    selected=[]
    for p in sorted(rows,key=lambda p:(p['score'],p['east_km'],p['north_km'])):
        if all(math.hypot(p['east_km']-q['east_km'],p['north_km']-q['north_km'])>=12.5 for q in selected):selected.append(p)
        if len(selected)==3:break
    return selected

def gate(best,native):
    if len(native)!=3:raise ValueError('incomplete native retention')
    distances=[math.hypot(best['east_km']-p['east_km'],best['north_km']-p['north_km']) for p in native]
    return min(distances)>12.5,distances

def main():
    integrity_raw=(OLD/'SEARCH_INTEGRITY.json').read_bytes();integrity=json.loads(integrity_raw)
    hashes={};protocol=integrity['protocol_digest']
    def pinned(path):
        raw=path.read_bytes();expected=integrity['receipt_sha256'].get(str(path))
        if expected is None:expected=integrity['artifact_sha256'].get(str(path.relative_to(OLD)))
        if expected is None or digest(raw)!=expected:raise ValueError('missing/mismatched historical hash '+str(path))
        hashes[str(path)]=digest(raw);return json.loads(raw)
    snapshot=pinned(OLD/'SEARCH_SNAPSHOT.json');terminal=pinned(OLD/'results/DS18-022/result.json')
    continuation_path=HERE.parent/'2026_10_09_position_error_iter123/protocol.json'
    continuation_raw=continuation_path.read_bytes()
    if digest(continuation_raw)!='96b45034497dd50b0134a95510190d577d9e192928b9880a6830ee9cec79bb43':
        raise ValueError('Published123 protocol changed')
    continuation=json.loads(continuation_raw)
    assert continuation['policy']['local_radius_km']==25
    hashes[str(continuation_path)]=digest(continuation_raw)
    historical_caches={}
    for name,expected in continuation['input_sha256'].items():
        if '/points/' in name:
            path=HERE.parents[1]/name
            if digest(path.read_bytes())!=expected:
                raise ValueError('Published123 point cache changed')
            historical_caches[str(path)]=expected
    assert terminal['complete'] and terminal['point_failure_count']==0
    point_rows={};current_hashes={}
    for path in (OLD/'results/DS18-022/points').glob('*.json'):
        if '.claim.' in path.name:continue
        raw=path.read_bytes();r=json.loads(raw)
        if r['key'][0]!='point':continue
        assert r['protocol_sha256']==protocol
        current_hashes[str(path)]=digest(raw);r['published123_cache_bound']=str(path) in historical_caches;point_rows[tuple(r['key'][1:])]=r
    output=dict(scope='Consumed DS18-022 search-only audit; no position accuracy inference',historical_integrity_sha256=digest(integrity_raw),historical_hashes=hashes,point_cache_current_hashes=current_hashes,arms={})
    for arm in ('fitted-c','zero-c'):
        traces={}
        for mode in ('native','fixed'):
            events=[pinned(p)['event'] for p in sorted((OLD/'results/DS18-022/traces'/f'{arm}-{mode}').glob('*.json'))]
            assert events[-1]['event']=='ranks'
            traces[mode]=[e for e in events if e['event']=='evaluated']
            assert len(traces[mode])==400
        fixed_map={(e['east'],e['north']):e for e in traces['fixed']};rows=[];missing=[];unqualified=[]
        for e in traces['native']:
            key=(e['east'],e['north'],arm);r=point_rows[key]
            if r['status']!='complete':missing.append(key);continue
            value=r['value'];assert abs(value['scores']['native']['objective']-e['score'])<1e-6
            score=value['scores']['fixed']['objective'];coord=key[:2]
            if coord in fixed_map:assert abs(score-fixed_map[coord]['score'])<1e-6
            if not value['fit']['converged']:unqualified.append(list(coord))
            rows.append(dict(east_km=e['east'],north_km=e['north'],score=score,spacing_km=(40,20,10,5)[e['depth']],fixed_trace_bound=coord in fixed_map,published123_cache_bound=r['published123_cache_bound'],historically_pinned_fixed_score=coord in fixed_map or r['published123_cache_bound']))
        selected=retain(rows);native=snapshot['retained_regions'][arm+'-native'];full=snapshot['retained_regions'][arm+'-fixed'];active,distances=gate(selected[0],native)
        intersection=[p for p in rows if p['historically_pinned_fixed_score']]
        strict=retain(intersection,len(intersection))
        geometry=[]
        for q in full:
            nearest=min(rows,key=lambda p:(math.hypot(p['east_km']-q['east_km'],p['north_km']-q['north_km']),p['east_km'],p['north_km']))
            geometry.append(dict(center=[q['east_km'],q['north_km']],nearest_native_sample=[nearest['east_km'],nearest['north_km']],distance_km=math.hypot(nearest['east_km']-q['east_km'],nearest['north_km']-q['north_km']),nearest_spacing_km=nearest['spacing_km']))
        for p in selected:
            p['ordinary_local_radius_km']=ordinary_radius(p['spacing_km'])
            p['direct123_local_radius_km']=continuation['policy']['local_radius_km']
        output['arms'][arm]=dict(points=rows,missing=missing,unqualified_native_points=unqualified,retained=selected,strict_intersection_retained=strict,strict_intersection_gate=gate(strict[0],native)[0],full_fixed_retained_membership_in_native_domain=[any((p['east_km'],p['north_km'])==(q['east_km'],q['north_km']) for p in rows) for q in full],native_retained=native,full_fixed_retained=full,gate=active,best_to_native_distances_km=distances,historically_pinned_fixed_points=sum(p['historically_pinned_fixed_score'] for p in rows),distances_to_full_fixed_km=[[math.hypot(p['east_km']-q['east_km'],p['north_km']-q['north_km']) for q in full] for p in selected])
        output['arms'][arm]['full_fixed_nearest_native_sample_geometry']=geometry
    output['published123_cache_hashes']=historical_caches
    output['provenance_limit']='Most point cache bytes have retrospective hashes only; native scores and overlapping fixed scores verified against pinned traces. Published123 pins eight point caches, adding two fitted-native fixed scores beyond the overlap. Remaining115 fitted/94zero scores lack historical hash authority.'
    output['source_sha256']={p.name:digest(p.read_bytes()) for p in HERE.glob('*.py')}
    (HERE/'results.json').write_text(json.dumps(output,indent=2))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,5))
    for ax,(arm,row) in zip(axes,output['arms'].items()):
        ax.scatter([p['east_km'] for p in row['points']],[p['north_km'] for p in row['points']],s=5,color='lightgray',label='Native sampled points')
        for field,marker,label in [('native_retained','x','Native retained'),('retained','o','Cached fixed rerank'),('full_fixed_retained','+','Full fixed discovery')]:
            ps=row[field];ax.scatter([p['east_km'] for p in ps],[p['north_km'] for p in ps],marker=marker,s=80,label=label)
        ax.set_title(arm+' discovery sensitivity');ax.set_xlabel('East km');ax.set_ylabel('North km');ax.set_aspect('equal');ax.legend(fontsize=7)
    fig.tight_layout();fig.savefig(HERE/'search-only.png',dpi=140)
    print(json.dumps({a:{k:v for k,v in r.items() if k in ('retained','gate','best_to_native_distances_km','historically_pinned_fixed_points')} for a,r in output['arms'].items()},indent=2))

if __name__=='__main__':main()
