"""Report every DS6 member, including pending and unavailable scans."""
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
protocol=json.loads((HERE/'protocol.json').read_text())
pose=json.loads((HERE.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text())
rows=[]
for session in protocol['sessions']:
    path=HERE/f'{session}.json'
    if not path.exists():
        rows.append(dict(session_id=session,state='pending'));continue
    result=json.loads(path.read_text())
    if result['state']=='unavailable':
        rows.append(dict(session_id=session,state='unavailable',reason=result['reason']));continue
    best=result['best']
    a,b,c,d=map(math.radians,[best['latitude'],best['longitude'],pose['latitude_deg'],pose['longitude_deg']])
    error=12742017.6*math.asin(math.sqrt(math.sin((a-c)/2)**2+math.cos(a)*math.cos(c)*math.sin((b-d)/2)**2))
    rows.append(dict(session_id=session,state='complete',error_m=error,rate_msps=result['rate_hz']/1e6,
        success=best['success'],bound_hit=best['bound_hit'],timing_s=best['x'][2],tracks=result['tracks'],
        minimum_anchor_top8_mass=result['minimum_anchor_top8_mass']))
done=[r for r in rows if r['state']=='complete']
summary=dict(scope='All 43 DS6 scans; fixed local model; not blind global validation',
    completed=len(done),pending=sum(r['state']=='pending' for r in rows),
    unavailable=sum(r['state']=='unavailable' for r in rows),
    sub_km=sum(r['error_m']<1000 for r in done),results=rows)
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))
for row in done:print(row)
