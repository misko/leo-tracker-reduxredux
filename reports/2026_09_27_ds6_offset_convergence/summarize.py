import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
protocol=json.loads((HERE/'protocol.json').read_text())
results=[json.loads((HERE/f'{s}.json').read_text()) for s in protocol['sessions'] if (HERE/f'{s}.json').exists()]
summary=dict(completed=len(results),expected=len(protocol['sessions']),
    train_gain=sum(r['total_train_gain'] for r in results),held_gain=sum(r['total_held_gain'] for r in results),
    unconverged_visible=sum(r['unconverged_visible'] for r in results),
    scans_train_change_over_one=[dict(session_id=r['session_id'],train_gain=r['total_train_gain'],held_gain=r['total_held_gain']) for r in results if abs(r['total_train_gain'])>1],
    map_changes=sum(t['map_changed'] for r in results for t in r['tracks']),
    maximum_iterations=max((t['maximum_iterations'] for r in results for t in r['tracks']),default=0))
(HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
