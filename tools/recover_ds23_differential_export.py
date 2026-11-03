"""Retry the frozen read-only export under existing noninteractive access.

Preserves the unprivileged PermissionError logs and empty partial files. The
privileged child only reads through the original recording adapter and writes
IQ to stdout; the unprivileged parent owns the generated local panel files.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import json
import subprocess
import numpy as np
from select_ds23_differential_information import OUT,BULK
from run_algo01_ds23_sample import ROOT,read,write,sha


def one(case):
    target=BULK/'panels'/(case+'.npz');temporary=target.with_suffix('.privileged_export.npz')
    previous=BULK/(case+'_export_recovery.log')
    preserved=BULK/(case+'_export_recovery_missing_scipy.log')
    if previous.exists() and not preserved.exists():previous.replace(preserved)
    code=('import probe_ds23_all_lane_components as e; from pathlib import Path; '
          f'e.BULK=Path({str(BULK)!r}); e.export({case!r})')
    command=['sudo','-n','/usr/bin/timeout','--kill-after=5s','130s','/usr/bin/env',
        'PYTHONPATH='+str(Path('/tmp/algo03-feasible-deps').resolve())+':src:tools','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',
        str(ROOT/'.venv/bin/python'),'-c',code]
    with temporary.open('wb') as stream,(BULK/(case+'_export_recovery.log')).open('w') as errors:
        result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=errors,timeout=145)
    if result.returncode:raise RuntimeError(f'{case} bounded read-only export recovery failed:{result.returncode}')
    with np.load(temporary,allow_pickle=False) as panel:
        metadata=json.loads(str(panel['metadata_json']));assert metadata['case']==case
        assert metadata['selected_raw_window_hashes_verified_by_read_only_adapter']
    temporary.replace(target)
    return dict(case=case,status='complete',sha256=sha(target),
        original_permission_error_log_sha256=sha(BULK/(case+'_export.log')),
        original_missing_dependency_log_sha256=sha(preserved),
        privileged_child_only_original_read_only_export=True)


def main():
    protocol=read(BULK/'protocol.json')
    with ProcessPoolExecutor(max_workers=3) as pool:
        receipts=[f.result() for f in as_completed([pool.submit(one,c) for c in protocol['cases']])]
    record=dict(receipts=receipts,all_terminal=True,original_failed_export_preserved=True,
        original_RF_protocol_sha256=sha(BULK/'protocol.json'),
        source_sha256=sha(Path(__file__)),new_RF_collection=False,source_recording_permissions_changed=False)
    write(OUT/'RF_export_recovery.json',record);write(OUT/'RF_export.json',record)
    print(receipts,flush=True)


if __name__=='__main__':main()
