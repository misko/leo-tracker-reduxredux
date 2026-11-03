"""Check provenance and generalized 2x2 eigenvalues independently."""
import hashlib
import json
import math
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
path=HERE/'outcome.json';data=json.loads(path.read_text())
for name,expected in data['sources'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected
largest=0.
for row in data['rows']:
    assert row['source_covered_tracks']<=row['tracks'] and row['source_groups']*2<=row['source_covered_tracks']
    for kind in ('source_drift','receiver_drift'):
        result=row[kind];a=result['baseline_information'];b=result['retained_information']
        qa=a[0][0]*a[1][1]-a[0][1]*a[1][0]
        qb=-(b[0][0]*a[1][1]+b[1][1]*a[0][0]-b[0][1]*a[1][0]-b[1][0]*a[0][1])
        qc=b[0][0]*b[1][1]-b[0][1]*b[1][0]
        assert qa>0
        root=math.sqrt(max(0.,qb*qb-4*qa*qc))
        values=[(-qb-root)/(2*qa),(-qb+root)/(2*qa)]
        largest=max(largest,max(abs(x-y) for x,y in zip(values,result['eigenvalues'])))
        assert all(-1e-9<=v<=1+1e-9 for v in values)
for kind in ('source_drift','receiver_drift'):
    assert abs(median(r[kind]['eigenvalues'][0] for r in data['rows'])-data['summary'][kind]['median_low_eigenvalue'])<1e-12
    assert abs(median(r[kind]['eigenvalues'][1] for r in data['rows'])-data['summary'][kind]['median_high_eigenvalue'])<1e-12
assert largest<1e-9
result=dict(verification_pass=True,tracks=sum(r['tracks'] for r in data['rows']),
            source_covered_tracks=sum(r['source_covered_tracks'] for r in data['rows']),
            maximum_eigenvalue_discrepancy=largest,independent_jacobian_replay=False,
            outcome_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
with (HERE/'verification.json').open('x') as f:json.dump(result,f,indent=2)
print(json.dumps(result,indent=2))
