import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

parser=argparse.ArgumentParser(description='Inventory saved adaptive and fixed-hop recordings by capture-start UTC.')
parser.add_argument('--end-utc',required=True)
parser.add_argument('--hours',type=float,default=8)
parser.add_argument('--bulk-root',type=Path,default=Path('/srv/bulk/leo'))
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
boundary=datetime.fromisoformat(args.end_utc.replace('Z','+00:00'))
if boundary.tzinfo is None or not 0 < args.hours <= 168:
    parser.error('A timezone-aware end time and 0 < hours <= 168 are required')
if args.output.exists():
    raise FileExistsError('Choose a fresh inventory output path')
end=int(boundary.timestamp()*1e9)
start=end-round(args.hours*3600*10**9)
s=ScannerTrackingInputStore(args.bulk_root)
try:
    rows=s.adaptive.tracking_metadata_index()
    selected=[{'session_id':id,'created':created,'captured':captured,'radio':radio,'mode':'adaptive'}
              for created,captured,radio,id in rows if start<=captured<end]
    print('adaptive total',len(rows),'in window',len(selected),flush=True)
    fixed=s.fixed.session_ids()
    print('fixed total',len(fixed),flush=True)
    for id in fixed:
        m=s.fixed.inspect(id).manifest
        timing=getattr(m,'timing',None)
        captured=timing.first_sample_estimate_utc_ns if timing else m.created_utc_ns
        if start<=captured<end:
            selected.append({'session_id':id,'created':m.created_utc_ns,'captured':captured,
                             'radio':m.receipt.radio_id,'mode':'fixed'})
    out={'start_utc_ns':start,'end_utc_ns':end,'sessions':sorted(selected,key=lambda r:r['captured'])}
    args.output.write_text(json.dumps(out,indent=2))
    print('selected',len(selected),'radios',sorted(set(r['radio'] for r in selected)),flush=True)
finally:
    s.close()
