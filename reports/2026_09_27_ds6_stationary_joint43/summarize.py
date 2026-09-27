"""Post-selection assessment of the three frozen DS6 joint-position fits."""
import json
import math
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
protocol=json.loads((HERE/'protocol.json').read_text())
results=[json.loads((HERE/f'{name}.json').read_text()) for name in ['all','A','B']]
assert all(r['complete'] for r in results)
pose=json.loads((HERE.parent/'2026_09_27_ds6_roof/pose-authority.json').read_text())


def distance(a,b):
    la,lo,lb,lob=map(math.radians,[*a,*b])
    return 12742017.6*math.asin(math.sqrt(math.sin((la-lb)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lo-lob)/2)**2))


rows=[]
for result in results:
    best=result['best']
    rows.append(dict(fit=result['fit'],scans=len(result['sessions']),latitude=best['latitude'],longitude=best['longitude'],
        error_m=distance([best['latitude'],best['longitude']],[pose['latitude_deg'],pose['longitude_deg']]),
        success=best['success'],bound_hit=best['bound_hit'],
        held_gain_vs_independent=sum(a['held_gain_vs_independent'] for a in result['audits']),
        maximum_interpolation_error_hz=max(a['maximum_interpolation_error_hz'] for a in result['audits'])))
summary=dict(scope='Joint static-site inference, not individual-scan accuracy',results=rows,
    result_sha256={f'{name}.json':hashlib.sha256((HERE/f'{name}.json').read_bytes()).hexdigest() for name in ['all','A','B']},
    reference_sha256=hashlib.sha256((HERE.parent/'2026_09_27_ds6_roof/pose-authority.json').read_bytes()).hexdigest(),
    random_subset_separation_m=distance([rows[1]['latitude'],rows[1]['longitude']],[rows[2]['latitude'],rows[2]['longitude']]))
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
