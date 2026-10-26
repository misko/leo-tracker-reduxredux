"""Freeze and generate fixed development primary timing forecasts, no raw IQ."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import predictor

HERE=Path(__file__).resolve().parent
PRIOR=Path('/srv/bulk/leo/research/ds24-missed-visit-r01/prediction')
OLD_ADAPTER=PRIOR.parent/'timing/adapter.py'


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x')as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def bound(check=True):
    for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
        if os.environ.get(key)!='1':raise ValueError('BLAS1 required')
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('580-second bound')))
    signal.alarm(580)
    if check:
        for path,digest in read(HERE/'protocol.json')['files'].items():
            if sha(path)!=digest:raise ValueError('frozen source changed: '+path)


def prepare():
    bound(False)
    owned=['PROTOCOL.md','INTERFACE.md','predictor.py','study.py','evaluate.py','test_predictor.py','example_packet.json']
    inputs=[PRIOR/'prediction_packets.json',PRIOR/'predictions.json',PRIOR/'panel.json',PRIOR/'protocol.json',
        PRIOR/'ROUND2_PROPOSAL.md',PRIOR/'artifact_seal.json',PRIOR/'evaluation_targets.json',OLD_ADAPTER,
        PRIOR.parent/'split.json']
    frozen_prior=read(PRIOR/'artifact_seal.json')
    for name in ['predictor.py','protocol.json','prediction_packets.json','predictions.json','panel.json','ROUND2_PROPOSAL.md']:
        if sha(PRIOR/name)!=frozen_prior['files'][name]['sha256']:raise ValueError('round1 source changed: '+name)
    run=subprocess.run([sys.executable,'-m','unittest','-v','test_predictor.py'],cwd=HERE,text=True,capture_output=True,timeout=30)
    if run.returncode:raise RuntimeError(run.stderr)
    write(HERE/'test_results.json',dict(exit_code=run.returncode,expected_tests=6,stderr=run.stderr,stdout=run.stdout))
    files={str(path):sha(path)for path in inputs+[HERE/n for n in owned]+[HERE/'test_results.json']}
    write(HERE/'protocol.json',dict(schema=predictor.VERSION,frozen_utc_ns=time.time_ns(),files=files,
        input_packets=str(PRIOR/'prediction_packets.json'),panel=str(PRIOR/'panel.json'),
        expected_receiver_cells=576,expected_paired_windows=288,tests_passed=6,
        target_outcomes_analyzed=False,validation_target_files_opened=False,raw_IQ_reads=0,
        process_bound_seconds=580,BLAS_threads=1,
        timing_measurement_reference='nominal midpoint-effective historical constant epoch',
        legacy_adapter_control_separate=True,original_primary_branch_and_CFO_unchanged=True))
    print('frozen',sha(HERE/'protocol.json'),flush=True)


def predict():
    began=time.monotonic();bound();rows=[]
    source=read(PRIOR/'prediction_packets.json')
    for row in source['rows']:
        try:result=predictor.predict(row)
        except Exception as exc:result=dict(header=row['header'],prediction_id=row['header']['prediction_id'],status='failed',error=repr(exc),methods={})
        rows.append(result)
    write(HERE/'predictions.json',dict(schema=predictor.VERSION,protocol_sha256=sha(HERE/'protocol.json'),
        source_packets_sha256=sha(PRIOR/'prediction_packets.json'),rows=rows,seconds=time.monotonic()-began,
        target_candidates_read=False,validation_target_files_opened=False,raw_IQ_reads=0))
    write(HERE/'forecast_seal.json',dict(protocol_sha256=sha(HERE/'protocol.json'),predictions_sha256=sha(HERE/'predictions.json'),
        receiver_cells=len(rows),statuses=dict(Counter(r['status']for r in rows)),
        raw_IQ_reads=0,target_outcomes_analyzed_before_seal=False,frozen_utc_ns=time.time_ns()))
    print(json.dumps(read(HERE/'forecast_seal.json')),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','predict']);a=p.parse_args()
    dict(prepare=prepare,predict=predict)[a.action]()
