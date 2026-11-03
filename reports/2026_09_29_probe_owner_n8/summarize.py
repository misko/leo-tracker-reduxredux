import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent


def distance(point):
    a,b=map(math.radians,point);c,d=map(math.radians,(37.849056280893684,-122.48575489722863))
    return 2*6371008.8*math.asin(math.sqrt(min(1,math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2)))


def main():
    rows=[]
    for ds in ('DS7','DS8','DS9'):
        assert json.loads((HERE/f'{ds}.receipt.json').read_text())['exit_code']==0
        p=json.loads((HERE/f'{ds}.json').read_text())
        r=dict(dataset=ds,qualified=p['selected'] is not None,qualified_starts=sum(s['qualified'] for s in p['starts']))
        for key in ('original_tracks','retained_tracks','original_training','retained_training','original_observations','retained_observations','original_groups','retained_groups','unrepresented_groups'):
            r[key]=sum(s[key] for s in p['ledgers'])
        r['training_retention']=r['retained_training']/r['original_training']
        r['excluded_tracks']=sum(t['excluded'] for s in p['ledgers'] for t in s['tracks'])
        if p['selected']:
            r.update(errors_m={k:distance(p[k]['estimate_deg']) for k in ('baseline','hard','selected')},held_change_vs_all=p['matched_scores']['owner']['held']-p['matched_scores']['all']['held'],held_change_vs_hard=p['matched_scores']['owner']['held']-p['matched_scores']['hard']['held'])
        rows.append(r)
    with (HERE/'summary.json').open('x') as out:json.dump(dict(rows=rows),out,indent=2)
    for name,h in json.loads((HERE/'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
