"""Extract IQ-only PSD proposals; retain every input and template binding."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from psd_proposal import make_bank, propose

HERE = Path(__file__).resolve().parent
ORACLE = Path('/var/tmp/leo-arm-full-search-oracle-allrates')
INPUTS = {'DS7': Path('/var/tmp/leo-ds7-large-arm-20260928'),
          'DS8': Path('/var/tmp/leo-arm-ds89-validation/inputs'),
          'DS9': Path('/var/tmp/leo-arm-ds89-validation/inputs')}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_native(rows):
    selected = []
    for rate in (2500000,5000000,7500000,10000000):
        for edge in ('lower','upper'):
            group = [r for r in rows if r['rate_hz']==rate and r['target']['edge']==edge]
            if len(group)<4:
                raise ValueError('Insufficient metadata stratum')
            selected.extend(group[round(i*(len(group)-1)/3)] for i in range(4))
    return selected


def run(dataset, output):
    root = INPUTS[dataset]
    inputs = json.loads((root/'inputs.json').read_text())
    if not inputs['complete']:
        raise ValueError('Inputs incomplete')
    selected = [dict(r,dataset_id=dataset) for r in inputs['rows']
                if dataset=='DS7' or r['dataset_id']==dataset]
    native = select_native(selected)
    output.mkdir(parents=True,exist_ok=False)
    manifest = dict(dataset=dataset,selected=selected,native_selected=native,
        input_manifest_sha256=sha(root/'inputs.json'),
        oracle_manifest_sha256=sha(ORACLE/'oracle.json'),
        estimator_sha256=sha(HERE/'psd_proposal.py'),runner_sha256=sha(Path(__file__)),
        complete=False,planned_dwells=len(selected))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    banks={};templates={}
    for case in json.loads((ORACLE/'oracle.json').read_text())['cases']:
        key=(case['context']['rate_hz'],case['context']['target']['edge'])
        t=case['templates']['exact'];path=ORACLE/t['file']
        assert sha(path)==t['sha256']
        if key not in banks:
            banks[key]=make_bank(np.fromfile(path,dtype='<c16'),key[0])
            templates[str(key)]=t
    elapsed=[]
    with (output/'rows.jsonl').open('x') as stream:
        for i,ctx in enumerate(selected):
            path=root/ctx['file'];assert sha(path)==ctx['sha256']
            iq=np.load(path,allow_pickle=False);rate=ctx['rate_hz']
            assert list(iq.shape)==ctx['shape'] and iq.dtype==np.int16
            bank=banks[(rate,ctx['target']['edge'])];windows=[]
            for probe in range(11):
                for rx in range(2):
                    start=probe*(rate//100);size=rate//50
                    t=time.process_time()
                    block=iq[start:start+size,rx,0].astype(float)+1j*iq[start:start+size,rx,1]
                    result=propose(block,bank)
                    cpu_ms=(time.process_time()-t)*1000;elapsed.append(cpu_ms)
                    windows.append(dict(receiver_id=rx,probe_index=probe,proposal=result,cpu_ms=cpu_ms))
            stream.write(json.dumps(dict(context=ctx,windows=windows),allow_nan=False)+'\n');stream.flush()
            if (i+1)%32==0:print(json.dumps(dict(dataset=dataset,processed_dwells=i+1)),flush=True)
    manifest.update(complete=True,processed_dwells=len(selected),processed_windows=len(elapsed),
        rows_sha256=sha(output/'rows.jsonl'),templates=templates,
        host_psd_cpu_ms_per_window=float(np.mean(elapsed)),
        estimator_unchanged=manifest['estimator_sha256']==sha(HERE/'psd_proposal.py'))
    assert manifest['estimator_unchanged']
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(dataset=dataset,complete=True,windows=len(elapsed),host_psd_cpu_ms_per_window=float(np.mean(elapsed)))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',choices=INPUTS,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.dataset,a.output)
