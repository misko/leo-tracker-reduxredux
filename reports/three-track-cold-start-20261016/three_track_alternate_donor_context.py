"""Transport a cold-only alternate donor endpoint onto evaluation metadata."""
exec(open('/tmp/three_track_cold_context.py').read())
index=int(os.environ['THREE_TRACK_ALTERNATE_DONOR'])
saved=json.loads((root/f'alternate_B_{index}_shared.json').read_text())
assert saved['derived_input_sha256']==derivation['derived_input_sha256']
endpoint=saved['result'];assert endpoint['audit']['accepted']
training_joint=objective(SimpleNamespace(observations=cold_obs),bank,prior,nodes)
raw,shift,_,_,_=donor_state(training_joint,stages[f'B-{index}']['result']['fit'])
cold_model=SharedScanObjective(raw,shift)
from leo.analysis.shared_scan_model import audit_endpoint
cold_audit=audit_endpoint(cold_model,endpoint['fit'],endpoint['options']);assert cold_audit['accepted']
v=np.array(endpoint['fit']['vector']);old_n=np.array(endpoint['fit']['nuisance'])
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
proof=dict(alternate_donor_index=index,training_observations=len(cold_obs.times_s),withheld_source_groups_absent=True,calibration_transport_maximum_error_hz=transport_error,cold_audit=cold_audit,derived_input_sha256=derivation['derived_input_sha256'])
(root/f'alternate_B_{index}_transport.json').write_text(json.dumps(proof,indent=2)+'\n')
