"""Reconstruct a cold-trained correction on original observation metadata only."""
import hashlib,json,os
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.application.shared_orbit_replay import selected_model
from leo.application.channel_group_refinement import objective
from leo.analysis.shared_scan_model import SharedScanObjective,donor_state
from leo.analysis.channel_group_calibration import project_calibration_seed
from leo.analysis.sequential_group_calibration import SequentialShift,fixed_shift_objective,freeze_sequential_calibration
from leo.contracts.regional_position import PositionObservations,RegionalPrior
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import zero_sum_basis,circular
from leo.analysis.hard60_score import predict_orbits

root=Path(os.environ.get('THREE_TRACK_COLD_ROOT','/tmp/three-track-investigation/cold-target-excluded-v1'))
new=json.loads((root/'output/terminal.json').read_text());assert new['state']=='complete'
derivation=json.loads((root/'derivation.json').read_text())
parent=Path('/srv/bulk/leo/fast-scan-tracking-inputs/fast-9571943d3dccdf4f327e1346d1bf34b8.json').read_bytes()
assert hashlib.sha256(parent).hexdigest()==derivation['parent_input_sha256']
source=load_input(json.loads(parent));origin=source.timing.first_sample_estimate_utc_ns
derived_path=root/('target-excluded-input.json' if (root/'target-excluded-input.json').exists() else 'training-input.json')
derived=derived_path.read_bytes()
assert hashlib.sha256(derived).hexdigest()==derivation['derived_input_sha256']
cold_source=load_input(json.loads(derived));prepared,nodes=prepare_views(cold_source);cold_obs=prepared['all'].observations
assert prepared['all'].start_utc_ns==origin
stages={}
for binding in new['stage_receipts']:
    p=Path(binding['path']);payload=p.read_bytes();assert 'sha256:'+hashlib.sha256(payload).hexdigest()==binding['sha256'];stages[p.stem]=json.loads(payload)
winners={}
for p in project_scanner_candidates(source):
    old=winners.get(p.source_group_id)
    if old is None or (-p.margin,p.candidate_rank,p.candidate_id)<(-old.margin,old.candidate_rank,old.candidate_id):winners[p.source_group_id]=p
points=sorted(winners.values(),key=lambda p:(p.support_center_utc_ns,p.source_group_id))
obs=PositionObservations(tuple(p.source_group_id for p in points),np.array([(p.support_center_utc_ns-origin)/1e9 for p in points]),np.array([p.measured_cfo_hz for p in points]),np.array([p.actual_rf_hz for p in points]),np.array([p.receiver_id for p in points]),np.array([p.channel for p in points]),np.array([p.margin for p in points]))
held_rows=derivation.get('excluded_original_rows',derivation.get('withheld_original_rows'))
assert len(obs.times_s)==4797 and len(cold_obs.times_s)==4797-len(held_rows)
removed=set(obs.window_ids)-set(cold_obs.window_ids)
assert removed=={points[i].source_group_id for i in held_rows}
prior=RegionalPrior(**new['provenance']['prior'])
archive=TleArchiveReader(Path('/var/lib/leo/tle'));snapshot=next(s for s in archive.list_snapshots() if s.digest==new['provenance']['tle_sha256'])
cat=parse_element_sets(archive.read(snapshot));lookup={int(num):i for i,num in enumerate(cat.satellite_numbers)};nums=new['candidate_numbers']
bank,_=build_regional_bank(cat,[lookup[num] for num in nums],origin,cold_obs,prior)
order={int(num):i for i,num in enumerate(bank.numbers)};bank=bank.select([order[num] for num in nums])
cold_model,fit,cold_audit=selected_model({'all':SimpleNamespace(observations=cold_obs)},bank,prior,np.array(new['provenance']['clock_nodes_s']),new,stages)
selected=new['selection']['source'];selection=stages['source-selection']
if selected=='B-all':
    joint=objective(SimpleNamespace(observations=cold_obs),bank,prior,nodes)
    _,shift,_,_,_=donor_state(joint,stages[f"B-{selection['B_index']}"]['result']['fit'])
else:
    high=stages[selected+'-high']['result']['fit'];shift=SequentialShift(tuple(high['group_receivers']),np.array(high['group_offsets_hz']))
v=np.array(fit['vector']);old_n=np.array(fit['nuisance'])
cal=freeze_sequential_calibration(cold_model.original,dict(vector=v,nuisance=old_n[:cold_model.clock_count]),shift)
target_correction=cal.predict(obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5)
joint=objective(SimpleNamespace(observations=obs),bank,prior,nodes)
raw=fixed_shift_objective(joint.base,shift)
projection=project_calibration_seed(raw,target_correction-raw.baseline)
v[2:7]=projection['coefficients'][:5]
n=np.r_[projection['coefficients'][5:],old_n[cold_model.clock_count:]]
model=SharedScanObjective(raw,shift)
transport_error=float(np.max(abs(model.original.correction(v,n[:model.clock_count])-target_correction)))
assert transport_error<1e-6
pred=predict_orbits(bank,obs,prior,v[:2],v[7]+zero_sum_basis(len(nums))@v[8:],derivatives=False)[0]
proof=dict(qualified_cold_background=True,cold_audit=cold_audit,training_observations=len(cold_obs.times_s),full_observations=len(obs.times_s),removed_source_group_count=len(removed),selected_candidate_count=len(nums),position=new['position'],calibration_transport_maximum_error_hz=transport_error,projection_rms_hz=projection['rms_hz'],parent_input_sha256=derivation['parent_input_sha256'],derived_input_sha256=derivation['derived_input_sha256'])
(root/'cold_context_transport.json').write_text(json.dumps(proof,indent=2)+'\n')
