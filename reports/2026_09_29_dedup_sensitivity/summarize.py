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
        r=dict(dataset=ds,qualified=p['fit']['qualified'],removed=len(p['removals']),removed_training=sum(x['training'] for x in p['removals']),old_error_m=distance(p['original']['estimate_deg']))
        if r['qualified']:
            r.update(new_error_m=distance(p['fit']['estimate_deg']),position_shift_m=p['position_shift_m'],deduplicated_training_gain=p['scores']['deduplicated']['new']['training']-p['scores']['deduplicated']['old']['training'],deduplicated_held_gain=p['scores']['deduplicated']['new']['held']-p['scores']['deduplicated']['old']['held'],original_held_gain=p['scores']['original']['new']['held']-p['scores']['original']['old']['held'])
        rows.append(r)
    with (HERE/'summary.json').open('x') as out:
        json.dump(dict(rows=rows),out,indent=2)
    for name,h in json.loads((HERE/'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    main()
