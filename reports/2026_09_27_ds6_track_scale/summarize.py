"""Post-selection coordinate audit of the frozen scale-calibration experiment."""
import json
import math
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent
protocol=json.loads((HERE/'protocol.json').read_text())
results=[json.loads((HERE/name.replace('-plan','')).read_text()) for name in protocol['inputs']]
assert all(r['complete'] for r in results)
pose=json.loads((HERE.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text())
rows=[]
for result in results:
    row={'session_id':result['session_id']}
    for name,arm in result['arms'].items():
        best=arm['best']
        a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
        error=12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
        row[name]=dict(error_m=error,exact_held=arm['exact_held'],success=best['success'],
            bound_hit=best['bound_hit'],timing_s=best['x'][2])
    row['held_improvement']=row['training_scale']['exact_held']-row['fixed_100']['exact_held']
    scales=[r['sigma'] for r in result['calibration']]
    row['scales_hz']=dict(min=min(scales),median=statistics.median(scales),max=max(scales),
        floor_count=scales.count(20.),ceiling_count=scales.count(1000.))
    rows.append(row)
summary=dict(scope='Four development scans, not DS6-wide validation',results=rows)
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
