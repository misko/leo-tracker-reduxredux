"""Rebuild the qualified ungated detector recipe with generate/use PGO flags."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def recipes(receipt,output,mode):
    if mode not in ('generate','use'):raise ValueError('invalid PGO mode')
    original=next(Path(c['argv'][2]).parent for c in receipt['commands'] if c['argv'][0].endswith('gcc-ar'))
    result=[]
    for item in receipt['commands']:
        argv=item['argv']
        # The training/evaluation bench drives the library directly; the
        # independent CLI main is not trained and is not part of this build.
        if any('native_glrt_cli' in x for x in argv):continue
        if argv[-1]==str(original/'leo-native-glrt'):continue
        argv=[v.replace(str(original),str(output)) for v in argv]
        # Refinement mode 2 does not link the CZT archive member. Keep that
        # optional member ordinary instead of silently accepting absent data.
        unused_czt=any(x.endswith('/conditioned_czt_wrapper.c') for x in argv)
        if not argv[0].endswith('gcc-ar') and not unused_czt:
            flags=(['-fprofile-generate','-fprofile-update=atomic'] if mode=='generate'
                   else ['-fprofile-use','-Werror=coverage-mismatch'])
            argv[1:1]=flags
        result.append(argv)
    return result


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['generate','use']);parser.add_argument('output',type=Path)
    args=parser.parse_args();out=args.output.resolve()
    root=Path(__file__).resolve().parents[1]
    receipt_path=root/'reports/2026_10_01_arm_glrt_missing_diagnosis/build.json'
    receipt=json.loads(receipt_path.read_text());commands=recipes(receipt,out,args.mode)
    sources={Path(a[a.index('-c')+1]) for a in commands if '-c' in a}
    source_root=next(p.parent for p in sources if p.name=='native_glrt.c')
    sources.update(p for p in source_root.rglob('*') if p.is_file())
    manifest={'parent_receipt_sha256':sha(receipt_path),'sources':{str(p):sha(p) for p in sorted(sources)}}
    if args.mode=='generate':
        out.mkdir(parents=True,exist_ok=False);(out/'objects').mkdir()
        (out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    else:
        if manifest!=json.loads((out/'source-manifest.json').read_text()):raise ValueError('source changed since training')
        for argv in commands:
            if '-c' in argv and '-fprofile-use' in argv:
                profile=Path(argv[argv.index('-o')+1]).with_suffix('.gcda')
                if not profile.is_file() or not profile.stat().st_size:raise ValueError('missing profile: '+str(profile))
    log=[]
    for argv in commands:
        result=subprocess.run(argv,capture_output=True,text=True,env={**os.environ,'TMPDIR':'/var/tmp'})
        log.append({'argv':argv,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        (out/(args.mode+'-build.json')).write_text(json.dumps(log,indent=2)+'\n')
        if result.returncode:raise RuntimeError(result.stderr)
    print(out/'leo-native-glrt-bench')


if __name__=='__main__':main()
