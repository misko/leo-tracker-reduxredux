"""Independently replay a completed coordinate-search endpoint, without refitting."""
import argparse,hashlib,json
from pathlib import Path
from run import context
from evaluate import audit,observations,classify_frozen_endpoint
from leo.cli.shared_fast_position import load_input

p=argparse.ArgumentParser(description=__doc__)
for key in ['attempt','tle-root','input','result','output']:p.add_argument('--'+key,type=Path,required=True)
args=p.parse_args()
if args.output.exists():raise FileExistsError('Use a new verification receipt')
result=json.loads(args.result.read_text());ctx=context(args)
if not result['profile']['complete'] or not result['audit']['accepted']:raise ValueError('Complete accepted result required')
for name,digest in result['source_sha256'].items():
    if hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()!=digest:raise ValueError('Executed source differs')
checked=audit(ctx.model,result['fit'],result['options'])
if not checked['accepted']:raise ValueError('Replayed endpoint rejected')
for key in ['objective','nll','stationarity']:
    if abs(checked[key]-result['audit'][key])>1e-7:raise ValueError('Endpoint numerical audit differs')
data=args.input.read_bytes()
if hashlib.sha256(data).hexdigest()!=ctx.derivation['parent_input_sha256']:raise ValueError('Original input differs')
classification=classify_frozen_endpoint(ctx.model,result['fit'],ctx.shift,observations(load_input(json.loads(data))),ctx.derivation,ctx.nodes)
for before,after in zip(result['pipeline_classification']['tracks'],classification['tracks']):
    for key in ['track','training_satellite','training_label_supported','test_count','test_matches_training_satellite','test_matches_forward_hypothesis']:
        if before[key]!=after[key]:raise ValueError('Classifier decision differs')
    if before['test_rms_hz'] is None:
        if after['test_rms_hz'] is not None:raise ValueError('Missing estimate changed')
    elif abs(before['test_rms_hz']-after['test_rms_hz'])>1e-6:raise ValueError('Held RMS differs')
receipt=dict(result_sha256=hashlib.sha256(args.result.read_bytes()).hexdigest(),audit=checked,
    classifier_decisions_reproduced=True,result='passed')
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
print(json.dumps(receipt),flush=True)
