"""Use one spare worker for frozen tail exports, preserving batch receipts."""
import json
from pathlib import Path
import subprocess
import time

import additional_export as exporter


def main():
    # The original batch traverses 0..11 and skips terminal receipts. A conflict
    # is an explicit stop, never permission to replace or race an existing log.
    for index in (11,10,9):
        folder=exporter.HERE/'additional'
        receipt=folder/f'export_{index:02d}.receipt.json'
        log=folder/f'export_{index:02d}.log'
        if receipt.exists():
            continue
        command=['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',
                 'timeout','--kill-after=5s','180s','nice','-n','19',exporter.PYTHON,
                 str(exporter.HERE/'additional_export.py'),'one',str(index)]
        start=time.monotonic()
        with log.open('x') as stream:
            result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
        row=dict(index=index,exit_code=result.returncode,wall_s=time.monotonic()-start,
                 command=command,source_sha256=exporter.digest(exporter.HERE/'additional_export.py'),
                 coordinator_sha256=exporter.digest(Path(__file__)))
        with receipt.open('x') as stream:
            json.dump(row,stream,indent=2)
        print(json.dumps(row),flush=True)


if __name__=='__main__':
    main()
