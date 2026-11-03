"""Decompose fixed-height horizontal shifts without using reference coordinates."""
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent


def mean(points):
    return [sum(p[k] for p in points)/len(points) for k in range(2)]


def norm2(p):
    return sum(v*v for v in p)


def decompose(base,points):
    if len(base)!=len(points) or not base:
        raise ValueError('Require matched nonempty point sets')
    center=mean(points)
    shifts=[[p[k]-b[k] for k in range(2)] for b,p in zip(base,points,strict=True)]
    common=mean(shifts)
    total=sum(norm2(d) for d in shifts)/len(shifts)
    differential=sum(norm2([d[k]-common[k] for k in range(2)]) for d in shifts)/len(shifts)
    assert abs(total-norm2(common)-differential)<1e-12
    return dict(centroid_en_km=center,
                scatter_rms_m=1000*math.sqrt(sum(norm2([p[k]-center[k] for k in range(2)]) for p in points)/len(points)),
                centroid_shift_m=1000*math.sqrt(norm2(common)),
                differential_shift_rms_m=1000*math.sqrt(differential),
                shared_shift_energy_fraction=norm2(common)/total if total else None,
                pairwise_distances_m=[1000*math.sqrt(norm2([points[i][k]-points[j][k] for k in range(2)])) for i in range(len(points)) for j in range(i+1,len(points))])


def main():
    hashes={};results=[]
    centers=[]
    for folder in ['2026_09_29_source_consistent_n8','2026_09_29_scan_budget']:
        path=HERE.parent/folder/'manifest.json'
        raw=path.read_bytes();hashes[str(path)]=hashlib.sha256(raw).hexdigest()
        centers.append(json.loads(raw)['config']['geographic_prior_center_deg'])
    assert centers[0]==centers[1], 'Require a common E/N coordinate origin'
    for label,folder in [('N8','2026_09_29_height_sensitivity'),('N24','2026_09_29_height_n24')]:
        points={h:[] for h in [0,100,300]}
        for ds in ['DS7','DS8','DS9']:
            path=HERE.parent/folder/f'{ds}.json'
            raw=path.read_bytes();hashes[str(path)]=hashlib.sha256(raw).hexdigest()
            source=json.loads(raw)
            for name,h in source['hashes'].items():
                assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
            assert source['baseline']['qualified']
            points[0].append(source['baseline']['x'][:2])
            assert [a['height_m'] for a in source['results']]==[100.,300.]
            for a in source['results']:
                assert a['fit']['qualified']
                points[a['height_m']].append(a['fit']['x'][:2])
        rows=[dict(height_m=h,positions_en_km=points[h],**decompose(points[0],points[h])) for h in [0,100,300]]
        results.append(dict(panel=label,datasets=['DS7','DS8','DS9'],rows=rows,
                            least_scatter_tested_height_m=min(rows,key=lambda r:r['scatter_rms_m'])['height_m']))
    for name in ['build.py','test_decomposition.py']:
        path=HERE/name;hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    with (HERE/'results.json').open('x') as out:
        json.dump(dict(results=results,hashes=hashes),out,indent=2,allow_nan=False)
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
