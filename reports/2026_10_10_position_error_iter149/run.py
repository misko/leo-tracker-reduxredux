"""Preparation-only explicit runner; no import-time numerical work."""
import argparse
import importlib.util
import json
from pathlib import Path
from handoff import recovery_port

HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'2026_10_10_position_error_iter148'

def preflight(plan):
    import hashlib
    root=HERE.parents[1]
    for group in ('source_sha256','input_sha256'):
        for name,expected in plan[group].items():
            if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:raise ValueError('source/input changed: '+name)

def recovery_source(source):
    old='recover=backend["recovered_region"],'
    if source.count(old)!=1:raise ValueError('123 recovery source shape changed')
    return source.replace(old,'recover=RECOVERY_PORT(backend, "fitted-c" if args.branch == "native" else "zero-c"),')

def main():
    import sys
    sys.path.insert(0,str(PREVIOUS))
    spec=importlib.util.spec_from_file_location('wrapper148_for149',PREVIOUS/'run.py')
    wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
    parser=argparse.ArgumentParser(add_help=False);parser.add_argument('branch',choices=('native','zero'));parser.add_argument('--protocol',default=str(HERE/'protocol.json'));args,_=parser.parse_known_args()
    plan=json.loads(Path(args.protocol).read_text());wrapper.preflight(plan)
    source=wrapper.transformed_source((wrapper.PARENT/'run.py').read_text())
    source=recovery_source(source)
    namespace=dict(__name__='run123_for149',__file__=str(wrapper.PARENT/'run.py'),EXPERIMENT_HERE=HERE,continue_branch=wrapper.adapter().continue_branch,RECOVERY_PORT=recovery_port)
    exec(compile(source,str(wrapper.PARENT/'run.py'),'exec'),namespace);namespace['main']()

if __name__=='__main__':main()
