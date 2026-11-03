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
        assert json.loads((HERE/f'{ds}.fit.receipt.json').read_text())['exit_code']==0
        p=json.loads((HERE/f'{ds}.fit.json').read_text())
        r=dict(dataset=ds,qualified=p['selected'] is not None,qualified_starts=sum(s['qualified'] for s in p['starts']),old_error_m=distance(p['baseline']['estimate_deg']))
        for key in ('original_tracks','retained_tracks','original_training','retained_training'):
            r[key]=sum(s[key] for s in p['selections'])
        r['training_retention']=r['retained_training']/r['original_training']
        if p['selected']:
            r.update(new_error_m=distance(p['selected']['estimate_deg']),matched_held_change=p['matched_scores']['consistent']['held']-p['matched_scores']['all']['held'])
        rows.append(r)
    with (HERE/'summary.json').open('x') as out:
        json.dump(dict(rows=rows),out,indent=2)
    for file in ('manifest.json','quality-seal.json'):
        for name,h in json.loads((HERE/file).read_text())['hashes'].items():
            assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    main()
