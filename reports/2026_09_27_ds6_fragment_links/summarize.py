"""Summarize fragment and lane-offset diagnostics; no roof reference loaded."""
import cmath
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parent
protocol=json.loads((HERE/'protocol.json').read_text())
rows=[]
for session in protocol['sessions']:
    result=json.loads((HERE/f'{session}.json').read_text());assert result['complete']
    lanes=[]
    for rx,ch,rf in sorted({(t['receiver_id'],t['channel'],t['rf_hz']) for t in result['tracks']}):
        members=[t for t in result['tracks'] if (t['receiver_id'],t['channel'],t['rf_hz'])==(rx,ch,rf) and t['confidence']>=.99]
        if len(members)<2:continue
        spacing=11.2e9/rf/4.4e-6
        z=sum(cmath.exp(2j*math.pi*t['offset']/spacing) for t in members)/len(members)
        lanes.append(dict(receiver_id=rx,channel=ch,rf_hz=rf,tracks=len(members),
            offset_resultant_length=abs(z),circular_offset_hz=cmath.phase(z)*spacing/(2*math.pi)))
    groups=result['groups']
    rows.append(dict(session_id=session,tracks=len(result['tracks']),repeated_groups=len(groups),
        linked_tracks=result['linked_tracks'],total_held_change=result['total_held_change'],
        longest_group_span_s=max((g['span_s'] for g in groups),default=None),
        offset_spreads_hz=[g['offset_spread_hz'] for g in groups],lanes=lanes))
(HERE/'summary.json').write_text(json.dumps(dict(results=rows),indent=2)+'\n')
for r in rows:print({k:v for k,v in r.items() if k!='lanes'})
