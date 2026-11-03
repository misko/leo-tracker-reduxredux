"""Account for failed attempts that never produced a completed archive."""
import importlib.util
import json
import re
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

runner_path=Path('/opt/leo-adaptive-cadence/9a98fcf4c38417156e024e8ac705988e69723a9c058105f2b6423011a8cb98f4/run_adaptive_capture_cycle.py')
spec=importlib.util.spec_from_file_location('capture_policy',runner_path)
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
raw=subprocess.check_output(['journalctl','-u','leo-v052-adaptive.service','--since','2026-10-05 09:59:31 UTC','--until','2026-10-05 13:59:31 UTC','-o','json','--no-pager'],text=True)
attempts=[];events=[];current=None
for line in raw.splitlines():
    d=json.loads(line); msg=d['MESSAGE']; epoch=int(d['__REALTIME_TIMESTAMP'])/1e6
    if msg.startswith('Starting leo-v052-adaptive.service'):
        choices={runner.slot_configuration(int(epoch)+delay,'1040005e0b100007100010000bf33a5d4d')[1] for delay in range(6)}
        current=dict(start_utc=datetime.fromtimestamp(epoch,ZoneInfo('UTC')).isoformat(),
                     start_pacific=datetime.fromtimestamp(epoch,ZoneInfo('America/Los_Angeles')).isoformat(),
                     scheduled_rate_hz=next(iter(choices)) if len(choices)==1 else None,state='unknown')
        attempts.append(current)
    if current is None:continue
    if 'AdaptiveScanQualificationError: qualification session' in msg:
        assert current['scheduled_rate_hz'] is not None, 'Ambiguous failed-attempt rate'
        current.update(state='failed',error=msg,elapsed_s=epoch-datetime.fromisoformat(current['start_utc']).timestamp())
        for key in ['planned','delivered','skipped','invalid','cancelled']:
            current[key]=int(re.search(r'\b'+key+r'=(\d+)',msg)[1])
        events.append(dict(timestamp=d['__REALTIME_TIMESTAMP'],message=msg))
    if msg.startswith('/srv/bulk/leo/v052-adaptive-live/') and msg.endswith('.json'):
        evidence=json.loads(Path(msg).read_text())
        assert current['scheduled_rate_hz'] in (None,evidence['rate_hz'])
        current['scheduled_rate_hz']=evidence['rate_hz']
        current.update(state='complete',session_id=Path(evidence['iq_archive']).name,
                       elapsed_s=epoch-datetime.fromisoformat(current['start_utc']).timestamp())
result=dict(attempts=attempts,failures=events,rate_assignment='Successful rates checked against receipts; failed rates reconstructed from deployed deterministic scheduler at invocation start, invariant over next five seconds.',
            counts={str(rate):dict(Counter(a['state'] for a in attempts if a['scheduled_rate_hz']==rate)) for rate in [2500000,10000000]})
Path('/var/tmp/leo-recent-10msps-attempts.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
