"""Freeze descriptive long-track plots using metadata only."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'protocol.json').exists(), 'Do not replace a frozen selection'
    candidates = []
    plans = {}
    for path in sorted((ROOT / '2026_09_27_ds6_pair_catalogue').glob('*-plan.json')):
        plan = json.loads(path.read_text())
        plans[plan['session_id']] = (path, plan)
        for group in plan['eligible_groups']:
            visits = sorted(group['visits'], key=lambda v: v['valid_start_counter'])
            span = (visits[-1]['valid_start_counter'] - visits[0]['valid_start_counter']) / plan['rate_hz']
            if len(visits) >= 20:
                candidates.append(dict(session_id=plan['session_id'], group=group['group'],
                                       span_s=span, support=len(visits), visits=visits))
    candidates.sort(key=lambda g: (-g['span_s'], -g['support'], g['session_id'], g['group']))
    chosen = candidates[:3]
    groups = []
    for group in chosen:
        visits = group['visits']
        selected = [visits[round(i * (len(visits)-1) / 15)] for i in range(16)]
        groups.append({k: v for k, v in group.items() if k != 'visits'} |
                      dict(selected_visits=[v['visit'] for v in selected]))
    sessions = sorted({g['session_id'] for g in groups})
    previous = json.loads((ROOT / '2026_09_27_ds6_phase_expansion/protocol.json').read_text())
    protocol = dict(scope='Descriptive plots, not a new blind association validation',
        selection='Three longest eligible pairs with at least 20 joint visits in the published ten-scan census; 16 evenly spaced visit-order quantiles per pair, including endpoints; no phase-result selection or replacement',
        starts_ms=[0, 21, 42, 63, 84, 105], width_ms=7,
        source_sha256=previous['source_sha256'],
        census_plan_sha256={sid: sha(plans[sid][0]) for sid in sessions},
        selected=[dict(session_id=sid) for sid in sessions], groups=groups,
        prepare_sha256=sha(Path(__file__)), replay_sha256=sha(HERE/'replay.py'))
    (HERE/'protocol.json').write_text(json.dumps(protocol, indent=2)+'\n')
    for sid in sessions:
        source, plan = plans[sid]
        selected_groups = [g for g in groups if g['session_id'] == sid]
        selected = [v for g in chosen if g['session_id'] == sid for v in g['visits']
                    if v['visit'] in next(s['selected_visits'] for s in selected_groups if s['group'] == g['group'])]
        assert len(selected) <= 32 and len({v['visit'] for v in selected}) == len(selected)
        plan.update(protocol_sha256=sha(HERE/'protocol.json'), selected=sorted(selected, key=lambda v:v['visit']),
                    selected_groups=selected_groups, census_plan_sha256=sha(source))
        (HERE/f'{sid}-plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    print(json.dumps(groups, indent=2))


if __name__ == '__main__':
    main()
