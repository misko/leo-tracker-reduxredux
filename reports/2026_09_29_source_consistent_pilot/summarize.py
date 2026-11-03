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
        p=json.loads((HERE/f'{ds}.json').read_text())
        r={k:p[k] for k in ('dataset','session_id','original_tracks','retained_tracks','original_training','retained_training','original_observations','retained_observations','elapsed_seconds')}
        r['qualified_starts']={k:sum(s['qualified'] for s in a['starts']) for k,a in p['arms'].items()}
        r['errors_m']={k:distance(a['selected']['estimate_deg']) if a['selected'] else None for k,a in p['arms'].items()}
        if 'matched_selected_scores' in p:
            s=p['matched_selected_scores'];r['matched_held_change']=s['consistent']['held']-s['all']['held']
        rows.append(r)
    with (HERE/'summary.json').open('x') as out:
        json.dump(dict(rows=rows),out,indent=2)
    for name,h in json.loads((HERE/'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    main()
