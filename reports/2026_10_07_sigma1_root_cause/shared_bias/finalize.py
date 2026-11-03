"""Render receipts and record nested-arm gaps without changing fit results."""
import csv,json
from pathlib import Path
p=Path(__file__).resolve().parent;d=json.loads((p/'results.json').read_text())
gaps=[]
for basin in d['basins']:
    best={arm:min((r for r in d['rows'] if r['basin']==basin and r['arm']==arm and r['feasible']),key=lambda r:r['objective']) for arm in ('fitted-c','zero-c')}
    delta=best['fitted-c']['objective']-best['zero-c']['objective']
    if delta>1e-6:gaps.append(dict(scope='basin',label=basin,free_minus_zero=delta))
for label,arms in d['block_selected'].items():
    delta=arms['fitted-c']['objective']-arms['zero-c']['objective']
    if delta>1e-6:gaps.append(dict(scope='block',label=label,free_minus_zero=delta))
(p/'nested_gaps.json').write_text(json.dumps(gaps,indent=2))
for key in ('rows','block_rows'):
    rows=d[key]
    with (p/(key+'.csv')).open('w') as f:
        writer=csv.DictWriter(f,fieldnames=[k for k in rows[0] if k!='vector'],extrasaction='ignore');writer.writeheader();writer.writerows(rows)
print(json.dumps(gaps,indent=2))
