"""Evaluate completed fits after selection; no reference enters the optimizer."""
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
result=json.loads((HERE/'results.json').read_text());assert result['complete']
pose=json.loads((HERE.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text())
rows=[]
for name,row in result['fits'].items():
    a,b,c,d=map(math.radians,[row['latitude'],row['longitude'],pose['latitude_deg'],pose['longitude_deg']])
    error=12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
    rows.append(dict(fit=name,error_m=error,success=row['best']['success'],bound_hit=row['best']['bound_hit'],
        included_held_gain=sum(r['held_gain_vs_independent'] for r in row['included_audits'].values()),
        omitted_held_gain=None if row['omitted_adaptation'] is None else row['omitted_adaptation']['held_gain_vs_independent']))
summary=dict(scope='Four development scans, not DS6-wide validation',results=rows)
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
