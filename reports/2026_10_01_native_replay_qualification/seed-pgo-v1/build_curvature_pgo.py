"""Strict ordinary/generate/use builds of the unchanged curvature or grid tracker."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'native/adaptive/tracking/research/curvature_tracks'


def compilation_sources(component):
    if component=='curvature':return [SOURCE/n for n in ['curvature_tracks.cpp','curvature_tracks_cli.cpp']]
    if component=='grid':return [ROOT/'native/adaptive/tracking/tracking.cpp',ROOT/'native/adaptive/tracking/research/grid_trial.cpp']
    raise ValueError('invalid tracker component')


def commands(output,mode,compiler,component='curvature'):
    if mode not in ('control','generate','use'):raise ValueError('invalid build mode')
    common=['-std=c++17','-O3','-g','-Wall','-Wextra','-Wpedantic','-Werror',
            '-fno-fast-math','-ffp-contract=off','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard']
    profile={'control':[],'generate':['-fprofile-generate','-fprofile-update=atomic'],
             'use':['-fprofile-use','-Werror=coverage-mismatch']}[mode]
    sources=compilation_sources(component)
    objects=[output/'objects'/(source.stem+'.o') for source in sources]
    recipes=[[compiler,*common,*profile,'-c',str(source),'-o',str(obj)] for source,obj in zip(sources,objects)]
    recipes.append([compiler,*common,*profile,*map(str,objects),'-static-libstdc++','-static-libgcc','-o',str(output/mode)])
    return recipes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['control','generate','use']);p.add_argument('output',type=Path)
    p.add_argument('--component',choices=['curvature','grid'],default='curvature')
    a=p.parse_args();out=a.output.resolve()
    compiler=os.environ.get('CXX','/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-g++')
    sources=compilation_sources(a.component)+[ROOT/'native/adaptive/tracking/tracking.hpp']
    sources+=([SOURCE/n for n in ['curvature_tracks.hpp','test_curvature_tracks.cpp']] if a.component=='curvature' else
              [ROOT/'native/adaptive/tracking'/n for n in ['hough_bin.hpp','tracking_cli.cpp']])
    manifest={'compiler':compiler,'component':a.component,'sources':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}}
    if a.mode=='control':
        out.mkdir();(out/'objects').mkdir();(out/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    elif manifest!=json.loads((out/'source-manifest.json').read_text()):raise ValueError('sources or compiler changed since control')
    if (out/a.mode).exists() or (out/(a.mode+'-build.json')).exists():raise ValueError('preserve existing build')
    if a.mode=='use':
        for source in compilation_sources(a.component):
            path=out/'objects'/(source.stem+'.gcda')
            if not path.is_file() or not path.stat().st_size:raise ValueError('missing profile: '+str(path))
    log=[]
    for argv in commands(out,a.mode,compiler,a.component):
        result=subprocess.run(argv,capture_output=True,text=True,env={**os.environ,'TMPDIR':'/var/tmp'})
        log.append({'argv':argv,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        (out/(a.mode+'-build.json')).write_text(json.dumps(log,indent=2)+'\n')
        if result.returncode:raise RuntimeError(result.stderr)
    print(out/a.mode)


if __name__=='__main__':main()
