import hashlib
import json
import math
import statistics
from pathlib import Path

HERE=Path(__file__).resolve().parent


def describe(values):
    assert values and all(math.isfinite(x) for x in values)
    return dict(min=min(values),median=statistics.median(values),max=max(values),unique=len(set(values)))


def main():
    rows=[]
    for ds in ('DS7','DS8','DS9'):
        assert json.loads((HERE/f'{ds}.receipt.json').read_text())['exit_code']==0
        data=json.loads((HERE/f'{ds}.json').read_text());points=data['rows']
        expected=math.hypot(400.,15000.*data['timing_bracket_width_ns']/2e9)
        assert all(abs(p['raw_standard_uncertainty_hz']-expected)<1e-9 for p in points)
        rows.append(dict(dataset=ds,session_id=data['session_id'],tracks=data['tracks'],observations=data['observations'],training=sum(p['training'] for p in points),held=sum(not p['training'] for p in points),timing_bracket_width_ns=data['timing_bracket_width_ns'],fields={k:describe([p[k] for p in points]) for k in ('exact_score','control_score','margin','raw_standard_uncertainty_hz','canonical_standard_uncertainty_hz','support_duration_ns','relative_alias_index')},source_groups=len({p['source_group_id'] for p in points}),elapsed_seconds=data['elapsed_seconds']))
    with (HERE/'summary.json').open('x') as out:
        json.dump(dict(rows=rows),out,indent=2)
    for name,h in json.loads((HERE/'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1]/name).read_bytes()).hexdigest()==h
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    main()
