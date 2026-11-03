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
        r=json.loads((HERE/f'{ds}.json').read_text())
        row=dict(dataset=ds,qualified=r['selected'] is not None,qualified_starts=sum(s['qualified'] for s in r['starts']),tracks=r['tracks'],edges=r['edges'],max_component=max(r['component_sizes']),no_conflict_audit=r['no_conflict_audit'])
        if r['selected']:
            s=r['scores']
            row.update(errors_m={k:distance(r[k]['estimate_deg']) for k in ('baseline','hard_consistent','selected')},new_model_held_parameter_change=s['new']['exclusive']['held']-s['old']['exclusive']['held'],old_model_held_parameter_change=s['new']['original']['held']-s['old']['original']['held'],held_model_change_at_old_parameters=s['old']['exclusive']['held']-s['old']['original']['held'],held_total_replacement_change=s['new']['exclusive']['held']-s['old']['original']['held'],expected_active_tracks=s['new']['exclusive']['expected_active_tracks'])
        rows.append(row)
    with (HERE/'summary.json').open('x') as out:json.dump(dict(rows=rows),out,indent=2)
    for name,h in json.loads((HERE/'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
