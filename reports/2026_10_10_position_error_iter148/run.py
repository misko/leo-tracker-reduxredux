"""Explicit bounded slice using unchanged123 continuation; import is inert."""
import sys
import argparse
import json
from ports import HERE,PARENT,ROOT,adapter

def preflight(plan):
    from ports import sha
    for group in ('source_sha256','input_sha256'):
        for name,expected in plan[group].items():
            if sha(ROOT/name)!=expected:raise ValueError('source/input changed: '+name)

def transformed_source(source):
    replacements=[('choices=("native", "fixed")','choices=("native", "zero")'),('from retained_adapter import continue_branch',''),('HERE = Path(__file__).resolve().parent','HERE = EXPERIMENT_HERE'),('if __name__ == "__main__":\n    main()','')]
    for old,new in replacements:
        if source.count(old)!=1:raise ValueError('123 source shape changed: '+old)
        source=source.replace(old,new)
    return source

def main():
    parser=argparse.ArgumentParser(add_help=False)
    parser.add_argument('--protocol',default=str(HERE/'protocol.json'))
    args,_=parser.parse_known_args()
    preflight(json.loads(open(args.protocol).read()))
    # Load123 runner into a report-owned environment. Only branch labels and
    # destinations change; stage budgets, claims, admission and fitting do not.
    source=transformed_source((PARENT/'run.py').read_text())
    namespace=dict(__name__='run123_for148',__file__=str(PARENT/'run.py'),EXPERIMENT_HERE=HERE,continue_branch=adapter().continue_branch)
    exec(compile(source,str(PARENT/'run.py'),'exec'),namespace)
    namespace['main']()

if __name__=='__main__':main()
