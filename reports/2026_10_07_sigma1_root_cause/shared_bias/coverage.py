"""Read-only time/RF coverage; prevent drift conclusions from scan confounding."""
import json
from pathlib import Path
import numpy as np
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.application.regional_position_inputs import prepare_position_windows

p=Path(__file__).resolve().parent
store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
try:source=store.load('scan-fw-6a376b600fc2f542')
finally:store.close()
obs=prepare_position_windows(source).observations
rows=[]
for rx in np.unique(obs.receiver):
    for channel in np.unique(obs.channel):
        mask=(obs.receiver==rx)&(obs.channel==channel)
        if not mask.any():continue
        rows.append(dict(rx=int(rx),channel=int(channel),rf_hz=np.unique(obs.rf_hz[mask]).tolist(),windows=int(mask.sum()),min_s=float(obs.times_s[mask].min()),max_s=float(obs.times_s[mask].max()),early=int(np.sum(mask&(obs.times_s<=obs.time_center_s))),late=int(np.sum(mask&(obs.times_s>obs.time_center_s))),quartile_counts=[int(np.sum(mask&(obs.times_s>=low)&(obs.times_s<high))) for low,high in zip(np.linspace(obs.times_s.min(),obs.times_s.max()+1e-9,5)[:-1],np.linspace(obs.times_s.min(),obs.times_s.max()+1e-9,5)[1:])]))
out=dict(time_center_s=obs.time_center_s,min_s=float(obs.times_s.min()),max_s=float(obs.times_s.max()),input_sha256=source.input_manifest_sha256,analysis_sha256=source.analysis_manifest_sha256,rows=rows)
(p/'coverage.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
