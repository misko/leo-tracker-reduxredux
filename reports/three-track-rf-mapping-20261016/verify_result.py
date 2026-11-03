"""Reconstruct one RF-hypothesis fit and its actual classifier without fitting."""
import argparse,hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-coordinate-timing-20261016'))
sys.path.insert(0,str(HERE.parent/'three-track-joint-band-recalibration-20261016'))
from run import context
from evaluate import audit,observations,classify_frozen_endpoint
from band_transport import freeze
from rf_mapping import remap
from leo.application.channel_group_refinement import objective
from leo.analysis.shared_scan_model import SmoothVisibilityModel
from leo.cli.shared_fast_position import load_input

p=argparse.ArgumentParser(description=__doc__)
for key in ['attempt','result','input','tle-root','output']:p.add_argument('--'+key,type=Path,required=True)
p.add_argument('--mode',choices=['recorded','static-9750','static-10600'],required=True);args=p.parse_args()
if args.output.exists():raise FileExistsError('Use a new verification receipt')
d=json.loads(args.result.read_text());ctx=context(args)
for name,sha in d['source_sha256'].items():
    if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=sha:raise ValueError('Executed RF source differs')
row=next(r for r in d['cases'] if r['mode']==args.mode)
if not row['profile']['complete'] or not row['audit']['accepted']:raise ValueError('Complete accepted RF case required')
selected=min((r for r in d['cases'] if r['audit']['accepted']),key=lambda r:(r['audit']['objective'],r['mode']))['mode']
if selected!=d['training_selected_mapping']:raise ValueError('Training mapping selection differs')
obs=remap(ctx.obs,d['recorded_targets'],args.mode)
joint=objective(SimpleNamespace(observations=obs),ctx.bank,ctx.prior,ctx.nodes)
model=SmoothVisibilityModel(joint,np.ones(len(obs.times_s),bool));checked=audit(model,row['fit'],row['options'])
if not checked['accepted']:raise ValueError('RF endpoint fails strict replay')
for key in ['objective','nll','stationarity']:
    if abs(checked[key]-row['audit'][key])>1e-7:raise ValueError('RF endpoint numerical audit differs')
frozen,fit,shift,transport=freeze(model,row['fit'])
payload=args.input.read_bytes()
if hashlib.sha256(payload).hexdigest()!=ctx.derivation['parent_input_sha256']:raise ValueError('Original data differs')
full=remap(observations(load_input(json.loads(payload))),d['recorded_targets'],args.mode)
classification=classify_frozen_endpoint(frozen,fit,shift,full,ctx.derivation,ctx.nodes)
for before,after in zip(row['pipeline_classification']['tracks'],classification['tracks']):
    for key in ['track','training_satellite','training_label_supported','test_matches_training_satellite','test_count']:
        if before[key]!=after[key]:raise ValueError('RF classifier decisions differ')
    if before['test_rms_hz'] is None:
        if after['test_rms_hz'] is not None:raise ValueError('Missing RF estimate changed')
    elif abs(before['test_rms_hz']-after['test_rms_hz'])>1e-6:raise ValueError('RF held RMS differs')
receipt=dict(mode=args.mode,result_sha256=hashlib.sha256(args.result.read_bytes()).hexdigest(),audit=checked,
    prediction_transport=transport,training_selection_reproduced=True,classifier_decisions_reproduced=True,result='passed')
args.output.parent.mkdir(parents=True,exist_ok=True)
with args.output.open('x') as stream:json.dump(receipt,stream,indent=2);stream.write('\n')
print(json.dumps(receipt),flush=True)
