"""Read checkpoint health through storage ports and reconcile operational states."""
import argparse
import json
from pathlib import Path
from leo.acquisition.authority import LocalCaptureAuthority,RadioResource
from leo.application.reconcile_fast_capture import reconcile
from leo.storage.fast_capture_health import checkpoint_health
from leo.storage.fast_scan import FastScanStore

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bulk-root',type=Path,required=True);p.add_argument('--recording-root',type=Path,action='append',required=True)
    p.add_argument('--serial',required=True);p.add_argument('--uri',required=True)
    a=p.parse_args();authority=LocalCaptureAuthority(a.bulk_root/'control',(RadioResource(a.serial,a.serial,a.uri),))
    health={r['run_id']:r for root in a.recording_root for r in checkpoint_health(root)}
    print(json.dumps(reconcile(authority,a.serial,health.values(),FastScanStore(a.bulk_root))))
