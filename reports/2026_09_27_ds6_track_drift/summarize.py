"""Reference comparison only after all four estimates are frozen."""
import json
import math
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
protocol=json.loads((HERE/'protocol.json').read_text())
results=[json.loads((HERE/f'{s}.json').read_text()) for s in protocol['sessions']]
assert all(r['complete'] for r in results)
pose=json.loads((HERE.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text())
rows=[]
for result in results:
    best=result['best']
    a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
    error=12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
    rows.append(dict(session_id=result['session_id'],error_m=error,held_gain=result['held_gain'],
        success=best['success'],bound_hit=best['bound_hit'],timing_s=best['x'][2],
        median_absolute_slope_hz_s=statistics.median(abs(t['slope_hz_s']) for t in result['details']),
        iteration_audit=result['iteration_audit']))
summary=dict(scope='Four development scans; inherited approximate catalogue shortlists; no DS6-wide claim',results=rows)
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
