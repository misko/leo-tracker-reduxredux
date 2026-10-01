"""Repeat bounded host trials and bind outputs to binary/input hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'2026_09_30_arm_fast_tracks/server-baseline/output'
SCI='/var/tmp/leo-arm-realtime-publication/.venv/bin/python'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--name',required=True)
    args=p.parse_args()
    out=HERE/'qualification'/args.name
    out.mkdir(parents=True,exist_ok=False)
    rows=[]
    for side in ('server','arm'):
        inp=BASE/f'{side}-observations.tsv'
        trials=[]
        for repeat in range(3):
            start=time.perf_counter()
            result=subprocess.run([str(args.binary.resolve()),str(inp.resolve())],
                                  capture_output=True,text=True,timeout=120,check=True)
            elapsed=time.perf_counter()-start
            path=out/f'{side}-{repeat}.tsv'
            path.write_text(result.stdout)
            (out/f'{side}-{repeat}.stderr').write_text(result.stderr)
            timing=next((float(line.split('\t')[2]) for line in result.stderr.splitlines()
                         if line.startswith('TIMING\treconstruct_s\t')),None)
            trials.append({'reconstruct_s':timing,'whole_process_s':elapsed,'sha256':sha(path)})
        if len({r['sha256'] for r in trials})!=1:
            raise RuntimeError('nondeterministic scientific output')
        subprocess.run([SCI,str(HERE/'evaluate.py'),'--tracks',str(out/f'{side}-0.tsv'),
                        '--side',side,'--output',str(out/f'{side}-evaluation.json')],check=True,timeout=60)
        rows.append({'side':side,'input_sha256':sha(inp),'repetitions':trials})
    synthetic=HERE.parent/'2026_09_30_arm_curvature_tracks/synthetic'
    result=subprocess.run([str(args.binary.resolve()),str((synthetic/'observations.tsv').resolve())],
                          capture_output=True,text=True,timeout=120,check=True)
    (out/'synthetic.tsv').write_text(result.stdout)
    (out/'synthetic.stderr').write_text(result.stderr)
    subprocess.run([SCI,str(synthetic.parent/'evaluate_synthetic.py'),'--truth',str(synthetic/'truth.json'),
                    '--tracks',str(out/'synthetic.tsv'),'--output',str(out/'synthetic-evaluation.json')],
                   check=True,stdout=subprocess.DEVNULL)
    (out/'receipt.json').write_text(json.dumps({'binary':str(args.binary.resolve()),
        'binary_sha256':sha(args.binary),'cases':rows,'all_repetitions_identical':True,
        'synthetic_input_sha256':sha(synthetic/'observations.tsv')},indent=2)+'\n')


if __name__=='__main__':
    main()
