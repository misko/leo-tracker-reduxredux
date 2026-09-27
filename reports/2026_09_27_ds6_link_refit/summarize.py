"""Compare frozen matched-arm outcomes against the operator coordinate."""
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
protocol=json.loads((HERE/'protocol.json').read_text())
results=[json.loads((HERE/f'{s}.json').read_text()) for s in protocol['sessions']]
assert all(r['complete'] for r in results)
pose=json.loads((HERE.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text())
rows=[]
for result in results:
    row=dict(session_id=result['session_id'],linked_groups=len(result['groups']))
    for name,arm in result['arms'].items():
        best=arm['best']
        a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
        error=12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
        row[name]=dict(error_m=error,exact_held=arm['exact_held'],success=best['success'],bound_hit=best['bound_hit'])
    row['held_gain']=row['shared']['exact_held']-row['separate']['exact_held']
    rows.append(row)
summary=dict(scope='Four development scans; conditional fixed identities; no full-DS6 accuracy claim',results=rows)
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
