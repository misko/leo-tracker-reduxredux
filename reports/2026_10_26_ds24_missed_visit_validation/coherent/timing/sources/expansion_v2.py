"""Metadata-corrected handoff/application wrapper; exact R01 scorer unchanged."""
import argparse
import importlib.util
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('unchanged_coherent_application_v1',HERE/'expansion.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.OUT=HERE/'expansion_v2'
UPSTREAM=base.R01/'expansion/prediction'


def prepare():
    if base.OUT==HERE/'expansion':raise ValueError('v1 output directory must remain untouched')
    verification=base.read(UPSTREAM/'verification_v2.json')
    base.prepare(UPSTREAM/'panel.json',UPSTREAM/'prediction_packets_v2.json',UPSTREAM/'protocol.json')
    path=base.OUT/'protocol.json';p=base.read(path)
    files=[Path(__file__),UPSTREAM/'forecast_seal_v2.json',UPSTREAM/'verification_v2.json']
    p['files'].update({str(f):base.sha(f) for f in files})
    p.update(schema='sealed-R01-coherent-application/v2',metadata_handoff_version=2,
        metadata_correction='Reload sealed forecasts before enrichment; corrected stream labels only; numeric forecasts/native support unchanged',
        previous_v1_protocol_sha256=base.sha(HERE/'expansion/protocol.json'),
        previous_v1_authorization_revoked=True,v1_raw_outcomes_started=False,
        verification_v2_sha256=base.sha(UPSTREAM/'verification_v2.json'),
        frozen_utc_ns=time.time_ns())
    path.write_text(json.dumps(p,indent=2,allow_nan=False)+'\n')
    print('v2 expansion frozen',base.sha(path),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run']);parser.add_argument('--case');args=parser.parse_args()
    prepare() if args.action=='prepare' else base.run(args.case)
