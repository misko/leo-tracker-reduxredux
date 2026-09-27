"""Score frozen group fits; the fitting script does not load the roof coordinate."""
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
protocol=json.loads((HERE/'protocol.json').read_text())
results=[json.loads((HERE/f'{session}.json').read_text()) for session in protocol['sessions']]
assert all(r['complete'] for r in results)
pose=json.loads((HERE.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text())
rows=[]
for result in results:
    for name,group in result['groups'].items():
        best=group['best']
        a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
        error=12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
        rows.append(dict(session_id=result['session_id'],group=name,error_m=error,
            shift_km=group['shift_from_all_km'],timing_s=best['x'][2],
            success=best['success'],bound_hit=best['bound_hit'],
            included_held_gain=group['included_held_gain'],omitted_held_gain=group['omitted_held_gain']))
summary=dict(scope='Diagnostic group sensitivity on four development scans; no group promoted by geographic score',results=rows)
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for row in rows:print(row)
