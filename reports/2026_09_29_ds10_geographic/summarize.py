import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
REFERENCE=[37.849056280893684,-122.48575489722863]


def distance(a,b):
    p,q=map(math.radians,a);r,s=map(math.radians,b)
    return 12742017.6*math.asin(math.sqrt(math.sin((r-p)/2)**2+math.cos(p)*math.cos(r)*math.sin((s-q)/2)**2))


def main():
    plan=json.loads((HERE/'plan.json').read_text());rows=[];missing=[]
    for height in [0,20,40]:
        for panel in ['N8_0','N8_1','N8_2','N24']:
            path=HERE/'fits'/f'{panel}_h{height}'/'result.json'
            if not path.exists():missing.append(f'{panel}_h{height}');continue
            data=json.loads(path.read_text())
            assert data['sessions']==plan['panels'][panel] and len(data['starts'])==6
            assert {(s['family'],s['initial'][0]) for s in data['starts']}=={(f,e) for f in ['cold','timing_grid'] for e in [-2,0,2]}
            for name,h in data['hashes'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==h,name
            selected=data['selected'];qualified=[s for s in data['starts'] if s['qualified']]
            assert (selected is not None)==bool(qualified)
            row=dict(panel=panel,height_m=height,qualified_starts=len(qualified),tracks=data['tracks'],observations=data['observations'],result_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),reference_distance_m=None)
            if selected:
                assert selected['qualified'] and selected['score']==max(s['score'] for s in qualified)
                row.update(reference_distance_m=distance(selected['estimate_deg'],REFERENCE),estimate_deg=selected['estimate_deg'],training_score=selected['score'],held_score=selected['held_score'])
            rows.append(row)
    result=dict(complete=not missing,rows=rows,missing=missing,reference_assumption='Prior operator roof coordinate; unchanged DS10 installation and coordinate uncertainty not independently attested.',configured_center_reference_distance_m=distance(plan['config']['geographic_prior_center_deg'],REFERENCE))
    (HERE/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
