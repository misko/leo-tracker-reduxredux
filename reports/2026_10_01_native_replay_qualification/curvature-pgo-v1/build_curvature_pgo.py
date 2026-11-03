"""Strict ordinary/generate/use builds of the unchanged curvature tracker."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'native/adaptive/tracking/research/curvature_tracks'


def commands(output,mode,compiler):
    if mode not in ('control','generate','use'):raise ValueError('invalid build mode')
    common=['-std=c++17','-O3','-g','-Wall','-Wextra','-Wpedantic','-Werror',
            '-fno-fast-math','-ffp-contract=off','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard']
    profile={'control':[],'generate':['-fprofile-generate','-fprofile-update=atomic'],
             'use':['-fprofile-use','-Werror=coverage-mismatch']}[mode]
    objects=[output/'objects'/(name+'.o') for name in ['curvature_tracks','curvature_tracks_cli']]
    recipes=[[compiler,*common,*profile,'-c',str(SOURCE/(obj.stem+'.cpp')),'-o',str(obj)] for obj in objects]
    recipes.append([compiler,*common,*profile,*map(str,objects),'-static-libstdc++','-static-libgcc','-o',str(output/mode)])
    return recipes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['control','generate','use']);p.add_argument('output',type=Path)
    a=p.parse_args();out=a.output.resolve()
    compiler=os.environ.get('CXX','/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-g++')
    sources=[SOURCE/n for n in ['curvature_tracks.cpp','curvature_tracks.hpp','curvature_tracks_cli.cpp','test_curvature_tracks.cpp']]+[ROOT/'native/adaptive/tracking/tracking.hpp']
    manifest={'compiler':compiler,'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}}
    if a.mode=='control':
        out.mkdir();(out/'objects').mkdir();(out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    elif manifest!=json.loads((out/'source-manifest.json').read_text()):raise ValueError('sources or compiler changed since control')
    if (out/a.mode).exists() or (out/(a.mode+'-build.json')).exists():raise ValueError('preserve existing build')
    if a.mode=='use':
        for name in ['curvature_tracks','curvature_tracks_cli']:
            path=out/'objects'/(name+'.gcda')
            if not path.is_file() or not path.stat().st_size:raise ValueError('missing profile: '+str(path))
    log=[]
    for argv in commands(out,a.mode,compiler):
        result=subprocess.run(argv,capture_output=True,text=True,env={**os.environ,'TMPDIR':'/var/tmp'})
        log.append({'argv':argv,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        (out/(a.mode+'-build.json')).write_text(json.dumps(log,indent=2)+'\n')
        if result.returncode:raise RuntimeError(result.stderr)
    print(out/a.mode)


if __name__=='__main__':main()
