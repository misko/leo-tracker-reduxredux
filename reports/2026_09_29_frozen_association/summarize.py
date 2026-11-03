import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def distance(point):
    lat, lon = map(math.radians, point)
    a, b = map(math.radians, (37.849056280893684, -122.48575489722863))
    h = math.sin((lat-a)/2)**2 + math.cos(lat)*math.cos(a)*math.sin((lon-b)/2)**2
    return 2*6371008.8*math.asin(math.sqrt(min(1,h)))


def main():
    rows = []
    for ds in ('DS7','DS8','DS9'):
        assert json.loads((HERE / f'{ds}.receipt.json').read_text())['exit_code'] == 0
        for p in json.loads((HERE / f'{ds}.json').read_text())['panels']:
            row = dict(dataset=ds, family=p['family'], panel=p['panel'], qualified_starts=sum(s['qualified'] for s in p['starts']), qualified=p['selected'] is not None, old_error_m=distance(p['old_estimate_deg']))
            if p['selected']:
                scores = p['original_model_scores']
                row.update(new_error_m=distance(p['selected']['estimate_deg']), held_change=scores['frozen_fit']['held']-scores['panel']['held'], training_change=scores['frozen_fit']['training']-scores['panel']['training'], surrogate_gain_over_donor=p['surrogate_gain_over_donor'], bound_gap=scores['frozen_fit']['training']-p['selected']['score'])
            rows.append(row)
    valid = [r for r in rows if r['qualified']]
    summary = dict(panels=len(rows), qualified_panels=len(valid), qualified_starts=sum(r['qualified_starts'] for r in rows), geographic_improvements=sum(r['new_error_m']<r['old_error_m'] for r in valid), old_subkm=sum(r['old_error_m']<1000 for r in valid), new_subkm=sum(r['new_error_m']<1000 for r in valid), held_improvements=sum(r['held_change']>0 for r in valid), total_held_change=sum(r['held_change'] for r in valid))
    with (HERE / 'summary.json').open('x') as out:
        json.dump(dict(summary=summary, rows=rows), out, indent=2)
    table = ['| DS | Panel | Qualified starts /2 | Original reference distance (m) | Frozen-fit distance (m) | Original-model held change (nats) |', '|---|---|---:|---:|---:|---:|']
    for r in rows:
        new = f"{r['new_error_m']:.1f}" if r['qualified'] else 'unqualified'
        held = f"{r['held_change']:+.2f}" if r['qualified'] else 'unqualified'
        table.append(f"| {r['dataset']} | {r['family']} {r['panel']} | {r['qualified_starts']} | {r['old_error_m']:.1f} | {new} | {held} |")
    (HERE / 'table.md').write_text('\n'.join(table)+'\n')
    for name,h in json.loads((HERE/'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h,name
    print(json.dumps(dict(summary=summary, rows=rows), indent=2))


if __name__ == '__main__':
    main()
