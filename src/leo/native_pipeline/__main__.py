"""python -m leo.native_pipeline run PLAN.json OUTPUT_DIRECTORY"""
import argparse
import json
from pathlib import Path

from .evaluation import evaluate
from .runner import finite_json, run, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    execute = sub.add_parser('run')
    execute.add_argument('plan', type=Path)
    execute.add_argument('output', type=Path)
    score = sub.add_parser('evaluate')
    for name in ('observations','sources','tracks','reference-observations',
                 'reference-sources','reference-tracks','settings','output'):
        score.add_argument('--'+name, type=Path, required=True)
    score.add_argument('--exclude-reference', type=int, action='append', default=[])
    args = parser.parse_args()
    if args.command == 'run':
        result = run(args.plan,args.output)
        print(json.dumps({'status':result['status'], 'stages':len(result['stages'])}))
    else:
        if args.output.exists():
            parser.error('evaluation output already exists')
        result = evaluate(args.observations,args.sources,args.tracks,args.reference_observations,
                          args.reference_sources,args.reference_tracks,finite_json(args.settings),
                          args.exclude_reference)
        write_json(args.output,result)
        print(json.dumps(result['summary']))


if __name__ == '__main__':
    main()
