import csv,hashlib,json,math,statistics
from pathlib import Path
HERE=Path(__file__).resolve().parent
METHODS=['iid','shared','correlated','contrast','q020','q020_correlated','cone40','q020_cone40','slope','curvature']
REFERENCE=(37.849056280893684,-122.48575489722863)

def distance(point,reference=REFERENCE):
    lat,lon=map(math.radians,point);a,b=map(math.radians,reference)
    h=math.sin((lat-a)/2)**2+math.cos(lat)*math.cos(a)*math.sin((lon-b)/2)**2
    return 2*6371008.8*math.asin(math.sqrt(max(0,min(1,h))))

def percentile(values,q):
    values=sorted(values);pos=(len(values)-1)*q;lo=int(pos);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(pos-lo)

def main():
    cells=[];sources={}
    for i in range(8):
        for method in METHODS:
            path=HERE/'runs'/f'{i:02d}_{method}.json';receipt=HERE/'runs'/f'{i:02d}_{method}.receipt.json'
            retry=HERE/'runs'/f'{i:02d}_{method}.retry.receipt.json'
            if retry.exists():receipt=retry
            if not receipt.exists():raise ValueError('Batch incomplete')
            r=json.loads(receipt.read_text());sources[str(receipt.relative_to(HERE))]=hashlib.sha256(receipt.read_bytes()).hexdigest()
            result=json.loads(path.read_text()) if path.exists() else None
            selected=result['selected'] if result else None
            status='qualified' if selected else ('timeout' if r['exit_code']==124 else 'unqualified' if r['exit_code']==0 else 'execution_failed')
            row=dict(scan_index=i,method=method,status=status,wall_s=r['wall_s'],distance_m=distance(selected['estimate_deg']) if selected else None,
                     common_q020_held=selected['common_q020_held'] if selected else None)
            cells.append(row)
            if result:sources[str(path.relative_to(HERE))]=hashlib.sha256(path.read_bytes()).hexdigest()
    complete=[i for i in range(8) if all(r['status']=='qualified' for r in cells if r['scan_index']==i)]
    summary=[]
    for method in METHODS:
        rows=[r for r in cells if r['method']==method];valid=[r for r in rows if r['status']=='qualified'];values=[r['distance_m'] for r in valid]
        shared=[r['distance_m'] for r in valid if r['scan_index'] in complete]
        paired=[]
        for r in valid:
            base=next(c for c in cells if c['scan_index']==r['scan_index'] and c['method']=='q020')
            if base['status']=='qualified':paired.append(r['common_q020_held']-base['common_q020_held'])
        summary.append(dict(method=method,qualified=len(valid),attempted=8,below1km=sum(v<1000 for v in values),
           median_m=statistics.median(values) if values else None,p90_m=percentile(values,.9) if values else None,
           min_m=min(values) if values else None,max_m=max(values) if values else None,
           matched_all_methods_median_m=statistics.median(shared) if shared else None,
           median_wall_s=statistics.median(r['wall_s'] for r in rows),
           median_wall_with_prerequisite_s=statistics.median(r['wall_s']+(next(c['wall_s'] for c in cells if c['scan_index']==r['scan_index'] and c['method']=='q020') if method in ('slope','curvature') else 0) for r in rows),
           common_q020_held_gain=sum(paired) if paired else None,common_score_pairs=len(paired)))
    result=dict(summary=summary,cells=cells,all_methods_qualified_scan_indices=complete,source_sha256=sources)
    (HERE/'summary.json').write_text(json.dumps(result,indent=2))
    with (HERE/'metrics.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    print(json.dumps(summary,indent=2));print('matched scans',complete)

if __name__=='__main__':main()
