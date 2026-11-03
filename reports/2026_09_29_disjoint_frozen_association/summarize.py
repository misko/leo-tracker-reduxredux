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
        for p in json.loads((HERE/f'{ds}.json').read_text())['pairs']:
            row=dict(dataset=ds,donor=p['donor'],target=p['target'],qualified=p['qualified'],donor_error_m=distance(p['donor_estimate_deg']),target_error_m=distance(p['target_estimate_deg']))
            if p['qualified']:
                scores=p['scores']
                row.update(frozen_error_m=distance(p['selected']['estimate_deg']),held_vs_target=scores['frozen_fit']['held']-scores['target']['held'],held_vs_donor=scores['frozen_fit']['held']-scores['donor_position']['held'],qualified_starts=sum(s['qualified'] for s in p['starts']))
            else:
                row['exception']=p.get('exception')
            rows.append(row)
    valid=[r for r in rows if r['qualified']]
    summary=dict(pairs=len(rows),qualified_pairs=len(valid),qualified_starts=sum(r['qualified_starts'] for r in valid),geographic_wins_vs_target=sum(r['frozen_error_m']<r['target_error_m'] for r in valid),geographic_wins_vs_donor=sum(r['frozen_error_m']<r['donor_error_m'] for r in valid),held_wins_vs_target=sum(r['held_vs_target']>0 for r in valid),held_wins_vs_donor=sum(r['held_vs_donor']>0 for r in valid),sum_held_vs_target=sum(r['held_vs_target'] for r in valid),sum_held_vs_donor=sum(r['held_vs_donor'] for r in valid),frozen_subkm=sum(r['frozen_error_m']<1000 for r in valid),target_subkm=sum(r['target_error_m']<1000 for r in valid),donor_subkm=sum(r['donor_error_m']<1000 for r in valid))
    with (HERE/'summary.json').open('x') as out:
        json.dump(dict(summary=summary,rows=rows),out,indent=2)
    table=['| DS | Donor → target | Donor distance (m) | Target distance (m) | Frozen-fit distance (m) | Held Δ vs target | Held Δ vs donor |','|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        vals=[f"{r[k]:.1f}" if r['qualified'] else 'unqualified' for k in ('frozen_error_m','held_vs_target','held_vs_donor')]
        table.append(f"| {r['dataset']} | {r['donor']} → {r['target']} | {r['donor_error_m']:.1f} | {r['target_error_m']:.1f} | {' | '.join(vals)} |")
    (HERE/'table.md').write_text('\n'.join(table)+'\n')
    for name,h in json.loads((HERE/'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
