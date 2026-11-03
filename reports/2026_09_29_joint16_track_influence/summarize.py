import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent


def distance(point):
    lat,lon=map(math.radians,point)
    a,b=map(math.radians,(37.849056280893684,-122.48575489722863))
    h=math.sin((lat-a)/2)**2+math.cos(lat)*math.cos(a)*math.sin((lon-b)/2)**2
    return 2*6371008.8*math.asin(math.sqrt(min(1,h)))


def main():
    rows=[]
    for ds in ('DS7','DS8','DS9'):
        assert json.loads((HERE/f'{ds}.receipt.json').read_text())['exit_code']==0
        for donor,target in [('early','middle'),('early','late'),('middle','late')]:
            p=json.loads((HERE/f'{ds}_{donor}_{target}.json').read_text())
            row=dict(dataset=ds,donor=donor,target=target,qualified=p['qualified'],tracks=len(p['tracks']),reference_distance_m=distance(p['estimate_deg']))
            if p['qualified']:
                row.update({k:p[k] for k in ('max_track_response_m','top10_norm_share','top10_vector_response_m')})
            rows.append(row)
    with (HERE/'summary.json').open('x') as out:
        json.dump(dict(rows=rows),out,indent=2)
    table=['| DS | Pair | Reference distance (m) | Max track response (m) | Top-ten share of summed norms | Top-ten vector response (m) |','|---|---|---:|---:|---:|---:|']
    for r in rows:
        if r['qualified']:
            values=f"{r['max_track_response_m']:.1f} | {100*r['top10_norm_share']:.2f}% | {r['top10_vector_response_m']:.1f}"
        else:
            values='unqualified | unqualified | unqualified'
        table.append(f"| {r['dataset']} | {r['donor']} + {r['target']} | {r['reference_distance_m']:.1f} | {values} |")
    (HERE/'table.md').write_text('\n'.join(table)+'\n')
    for name,h in json.loads((HERE/'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h
    print('\n'.join(table))


if __name__=='__main__':
    main()
