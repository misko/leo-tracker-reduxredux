import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
protocol=json.loads((HERE/'protocol.json').read_text());rows=[]
for session in protocol['selected']:
    p=HERE/f'{session}.json'
    if not p.exists():continue
    r=json.loads(p.read_text())
    for t in r['tracks']:rows.append(dict(session_id=session,**t))
summary=dict(completed_scans=len({r['session_id'] for r in rows}),expected_scans=43,
    tracks=len(rows),candidates=sum(r['candidates'] for r in rows),
    all_converged=all(r['all_converged'] for r in rows),
    max_abs_gradient=max((r['max_abs_gradient'] for r in rows),default=None),
    train_gain=sum(r['train_gain'] for r in rows),held_gain=sum(r['held_gain'] for r in rows),
    map_changes=sum(r['old_map']!=r['new_map'] for r in rows),results=rows)
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))
