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
            r=dict(dataset=ds,donor=p['donor'],target=p['target'],reused=p['reused'],qualified=p['selected'] is not None,qualified_new_starts=sum(s['qualified'] for s in p['starts']))
            if p['selected']:
                r.update(joint_error_m=distance(p['selected']['estimate_deg']),frozen_error_m=distance(p['control_estimates']['frozen']),target_error_m=distance(p['control_estimates']['target']),donor_error_m=distance(p['control_estimates']['donor']),held_joint_minus_frozen=p['target_score']['held']-p['control_scores']['frozen_fit']['held'],held_joint_minus_target=p['target_score']['held']-p['control_scores']['target']['held'],held_joint_minus_donor=p['target_score']['held']-p['control_scores']['donor_position']['held'])
            rows.append(r)
    valid=[r for r in rows if r['qualified']]
    summary=dict(pairs=len(rows),qualified_pairs=len(valid),new_qualified_starts=sum(r['qualified_new_starts'] for r in rows),reused_fits=sum(r['reused'] for r in rows),joint_subkm=sum(r['joint_error_m']<1000 for r in valid),frozen_subkm=sum(r['frozen_error_m']<1000 for r in valid),joint_geographic_wins_vs_frozen=sum(r['joint_error_m']<r['frozen_error_m'] for r in valid),joint_held_wins_vs_frozen=sum(r['held_joint_minus_frozen']>0 for r in valid),sum_held_joint_minus_frozen=sum(r['held_joint_minus_frozen'] for r in valid),joint_held_wins_vs_target=sum(r['held_joint_minus_target']>0 for r in valid),sum_held_joint_minus_target=sum(r['held_joint_minus_target'] for r in valid))
    with (HERE/'summary.json').open('x') as out:
        json.dump(dict(summary=summary,rows=rows),out,indent=2)
    table=['| DS | Pair | Joint16 reference distance (m) | Constrained reference distance (m) | Target held Δ, joint minus constrained (nats) |','|---|---|---:|---:|---:|']
    for r in rows:
        vals=[f"{r[k]:.1f}" if r['qualified'] else 'unqualified' for k in ('joint_error_m','frozen_error_m','held_joint_minus_frozen')]
        table.append(f"| {r['dataset']} | {r['donor']} → {r['target']} | {' | '.join(vals)} |")
    (HERE/'table.md').write_text('\n'.join(table)+'\n')
    for name,h in json.loads((HERE/'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
