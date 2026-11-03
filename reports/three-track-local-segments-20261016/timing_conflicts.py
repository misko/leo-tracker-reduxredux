"""Training-only audit of candidate timing and competing support in a cold fit."""
import argparse
from dataclasses import asdict
import hashlib,json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from evaluate import observations
from leo.cli.shared_fast_position import load_input
from leo.application.shared_orbit_replay import selected_model
from leo.analysis.regional_position_bootstrap import observation_subset
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import circular,zero_sum_basis
from leo.analysis.hard60_score import predict_orbits
from leo.contracts.regional_position import RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--attempt',type=Path,required=True);p.add_argument('--tle-root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);args=p.parse_args()
if args.output.exists():raise FileExistsError('Use a new diagnostic namespace')
terminal=json.loads((args.attempt/'output/terminal.json').read_text())
if terminal['state']!='complete':raise ValueError('Accepted cold endpoint required')
derivation=json.loads((args.attempt/'derivation.json').read_text());payload=(args.attempt/'training-input.json').read_bytes()
if hashlib.sha256(payload).hexdigest()!=derivation['derived_input_sha256']:raise ValueError('Training bytes differ')
source=load_input(json.loads(payload));obs=observations(source);stages={}
for binding in terminal['stage_receipts']:
    path=Path(binding['path']);data=path.read_bytes()
    if 'sha256:'+hashlib.sha256(data).hexdigest()!=binding['sha256']:raise ValueError('Stage bytes differ')
    stages[path.stem]=json.loads(data)
prior=RegionalPrior(**terminal['provenance']['prior']);archive=TleArchiveReader(args.tle_root)
snapshot=next(s for s in archive.list_snapshots() if s.digest==terminal['provenance']['tle_sha256'])
catalogue=parse_element_sets(archive.read(snapshot));lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
numbers=terminal['candidate_numbers'];bank,_=build_regional_bank(catalogue,[lookup[n] for n in numbers],
    source.timing.first_sample_estimate_utc_ns,obs,prior)
order={int(n):i for i,n in enumerate(bank.numbers)};bank=bank.select([order[n] for n in numbers])
model,fit,checked=selected_model(dict(all=SimpleNamespace(observations=obs)),bank,prior,
    np.array(terminal['provenance']['clock_nodes_s']),terminal,stages)
if not checked['accepted']:raise ValueError('Cold endpoint failed strict replay')
v=np.array(fit['vector']);n=np.array(fit['nuisance']);(evaluation,details)=model.evaluate_details(v,n)
terms=evaluation[3];timings=v[7]+zero_sum_basis(len(numbers))@v[8:]
correction=model.original.correction(v,n[:model.clock_count]);grid=np.linspace(-20,20,801)
held=set(derivation['withheld_original_rows'])
mapping={r:i for i,r in enumerate(r for r in range(derivation['original_observations']) if r not in held)}
hypotheses=dict(early_ch2=69433,ch4=69333,late_ch2=69522);results=[]
fig=Figure(figsize=(13,4.2),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,3)
for ax,target in zip(axes,derivation['targets']):
    number=hypotheses[target['track']];k=numbers.index(number)
    rows=np.array([mapping[r] for r in target['training_rows']]);subset=observation_subset(obs,rows)
    rms=[]
    for timing in grid:
        prediction=predict_orbits(bank.select([k]),subset,prior,v[:2],np.array([timing]),derivatives=False)[0][:,0]
        error=circular(subset.measured_hz-correction[rows]-prediction)
        rms.append(float(np.sqrt(np.mean(error**2))))
    best=int(np.argmin(rms));learned=float(timings[k])
    predicted=predict_orbits(bank.select([k]),subset,prior,v[:2],np.array([learned]),derivatives=False)[0][:,0]
    current_rms=float(np.sqrt(np.mean(circular(subset.measured_hz-correction[rows]-predicted)**2)))
    selected=np.argmax(terms.responsibilities,axis=1)
    assigned=(selected==k)&(terms.responsibilities[:,k]>terms.clutter_probability)
    support=[]
    for rx,ch in sorted(set(zip(obs.receiver[assigned],obs.channel[assigned]))):
        ix=np.flatnonzero(assigned&(obs.receiver==rx)&(obs.channel==ch))
        support.append(dict(receiver=int(rx),channel=int(ch),count=len(ix),
            time_min_s=float(obs.times_s[ix].min()),time_max_s=float(obs.times_s[ix].max()),
            posterior_mass=float(terms.responsibilities[ix,k].sum()),
            residual_rms_hz=float(np.sqrt(np.mean(terms.residual_hz[ix,k]**2)))))
    result=dict(track=target['track'],hypothesis=number,training_count=len(rows),
        learned_global_timing_s=learned,learned_detection_probability=float(details['detection_probability'][k]),
        target_rms_at_learned_timing_hz=current_rms,
        target_posterior_mass=float(terms.responsibilities[rows,k].sum()),
        assigned_training_points_elsewhere=int(np.sum(assigned&~np.isin(np.arange(len(assigned)),rows))),
        training_rms_profile_timing_s=float(grid[best]),training_rms_profile_hz=rms[best],
        timing_grid_s=grid.tolist(),training_rms_grid_hz=rms,learned_timing_support=support)
    results.append(result)
    ax.plot(grid,rms,color='#167f9b',label='Target training carrier RMS')
    ax.scatter([learned],[current_rms],color='#c17728',marker='x',s=70,label='Learned global timing')
    ax.axvline(grid[best],ls=':',color='gray',label='Training RMS minimum')
    ax.axhline(375,ls='--',color='#999999',lw=.8)
    ax.set(yscale='log',xlabel='Single candidate orbit timing (s)',ylabel='Target training RMS (Hz)',
           title=f"{target['track']} · hypothesis {number}")
    ax.grid(alpha=.2);ax.legend(fontsize=7)
fig.suptitle('Global candidate timing can fit other observations while missing a clean target\n'
             'Calibration and position frozen; training-only diagnostic, not an orbit or timestamp correction')
args.output.mkdir(parents=True,exist_ok=False);fig.savefig(args.output/'timing_profiles.png',dpi=170)
result=dict(scope='Training-only descriptive audit. The three candidate numbers are forward-consistent hypotheses, not independently verified labels. A separate per-target timing profile is not a recovered pipeline assignment and does not identify the physical source of the disagreement. Other assigned points are conditional on the same global model, not independently identified spacecraft.',
    terminal_sha256=hashlib.sha256((args.attempt/'output/terminal.json').read_bytes()).hexdigest(),
    derived_input_sha256=derivation['derived_input_sha256'],score=asdict(model.score),cold_audit=checked,results=results)
(args.output/'diagnostic.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps([dict(track=r['track'],learned_tau=r['learned_global_timing_s'],target_train_rms=r['target_rms_at_learned_timing_hz'],profile_tau=r['training_rms_profile_timing_s'],profile_rms=r['training_rms_profile_hz'],q=r['learned_detection_probability'],elsewhere=r['assigned_training_points_elsewhere'],support=r['learned_timing_support']) for r in results],indent=2),flush=True)
