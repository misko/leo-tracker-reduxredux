"""Bounded cold-training shared refinement of an existing, unselected B donor."""
exec(open('/tmp/three_track_cold_context.py').read())
import sys,time
from leo.analysis.shared_scan_model import bounded_shared_fit
index=int(sys.argv[1]);assert 0<=index<5
donor=stages[f'B-{index}']['result'];assert donor['audit']['accepted']
training_joint=objective(SimpleNamespace(observations=cold_obs),bank,prior,nodes)
raw,alternate_shift,v0,n0,error=donor_state(training_joint,donor['fit'])
alternate_model=SharedScanObjective(raw,alternate_shift)
n0=np.r_[n0,alternate_model.initial_nuisance[alternate_model.base_nuisance_count:]]
started=time.monotonic()
result=bounded_shared_fit(alternate_model,v0,n0,local_center=donor['options']['local_center'])
record=dict(qualification='Existing B donor and all training observations only; original cold held probe groups remain absent. Same 60s shared fitter, 65s total allowance and original strict audit. No target candidate identities or target corrections supplied.',donor_index=index,cold_root=str(root),training_observations=len(cold_obs.times_s),derived_input_sha256=derivation['derived_input_sha256'],donor_transport_maximum_error_hz=error,elapsed_seconds=time.monotonic()-started,result=result)
from leo.application.shared_fast_position import plain
path=root/f'alternate_B_{index}_shared.json';path.write_text(json.dumps(plain(record),indent=2)+'\n')
print(json.dumps(dict(path=str(path),elapsed_seconds=record['elapsed_seconds'],audit=result.get('audit'))),flush=True)
