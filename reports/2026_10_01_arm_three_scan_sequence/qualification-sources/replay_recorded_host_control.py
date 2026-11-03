"""Run the frozen native algorithm on full local IQ in bounded 16-dwell batches."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('scan',type=Path);p.add_argument('iq',type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    panel=json.loads((root/'reports/2026_09_30_arm_ds9_native_comparison/panel.json').read_text())
    capture=json.loads((a.scan/'capture-manifest.json').read_text());events=capture['receipt']['events']
    inventory=json.loads((a.iq/'inventory.json').read_text())
    if len(events)!=len(inventory) or any(r['event']!=e for r,e in zip(inventory,events)):
        raise ValueError('IQ authority mismatch')
    template_root=Path('/var/tmp/leo-arm-full-search-oracle-check.vUQA2Z/out')
    for kinds in panel['templates'].values():
        for info in kinds.values():
            if hashlib.sha256((template_root/info['file']).read_bytes()).hexdigest()!=info['sha256']:
                raise ValueError('template changed')
    binary=Path('/var/tmp/leo-three-host-glrt-v2/leo-native-glrt-bench')
    output=a.scan/'native-host-glrt';output.mkdir()
    started=time.monotonic();passing=0
    for start in range(0,len(events),16):
        rows=[]
        for i,e in enumerate(events[start:start+16]):
            kind=panel['templates'][e['target']['edge']]
            rows.append('\t'.join(map(str,[i,2500000,120,120,template_root/kind['exact']['file'],template_root/kind['control']['file'],a.iq/f'visit-{start+i:06d}.ci16'])))
        manifest=output/f'batch-{start:06d}.tsv';manifest.write_text('\n'.join(rows)+'\n')
        r=subprocess.run([str(binary),'--manifest',str(manifest),'--no-profile'],capture_output=True,text=True,timeout=60)
        (output/f'batch-{start:06d}.jsonl').write_text(r.stdout);(output/f'batch-{start:06d}.stderr').write_text(r.stderr)
        r.check_returncode()
        calls=[d['result'] for l in r.stdout.splitlines() if 'result' in (d:=json.loads(l))]
        if len(calls)!=len(rows):raise ValueError('incomplete control batch')
        passing+=sum(c['margin']>=.025 for call in calls for row in call['rows'] for c in row['candidates'])
    (output/'receipt.json').write_text(json.dumps({'status':'complete','visits':len(events),'passing_candidates':passing,
        'wall_s':time.monotonic()-started,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
        'scope':'Frozen native detector on x86 scalar/system FFTW; compare cross-architecture numerical differences explicitly'},indent=2)+'\n')
    print('complete',flush=True)


if __name__=='__main__':main()
