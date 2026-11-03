"""Project a cold-training free/fixed band endpoint onto evaluation metadata."""
exec(open('/tmp/three_track_cold_context.py').read())
from leo.analysis.frozen_group_calibration import freeze_group_calibration
from leo.analysis.shared_scan_model import SmoothVisibilityModel
variant=os.environ['THREE_TRACK_BAND_VARIANT'];arm=os.environ['THREE_TRACK_BAND_ARM']
suffix='' if os.environ.get('THREE_TRACK_BAND_PASS','1')=='1' else '_pass2'
saved=json.loads((root/f'refine_band_contrast_{variant}_{arm}{suffix}.json').read_text());assert saved['audit']['accepted']
assert saved['derived_input_sha256']==derivation['derived_input_sha256']
fit=saved['fit'];v=np.array(fit['vector']);old_n=np.array(fit['nuisance'])
if variant=='free':
    training_joint=objective(SimpleNamespace(observations=cold_obs),bank,prior,nodes)
    count=len(training_joint.initial_nuisance)
    cal=freeze_group_calibration(training_joint,dict(vector=v,nuisance=old_n[:count]))
    shift=SequentialShift(tuple(training_joint.frame.receivers),old_n[training_joint.clock_count:count])
    tail=old_n[count:]
else:
    cal=freeze_sequential_calibration(cold_model.original,dict(vector=v,nuisance=old_n[:cold_model.clock_count]),shift)
    tail=old_n[cold_model.clock_count:]
target_correction=cal.predict(obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5)
joint=objective(SimpleNamespace(observations=obs),bank,prior,nodes)
raw=fixed_shift_objective(joint.base,shift)
projection=project_calibration_seed(raw,target_correction-raw.baseline)
v[2:7]=projection['coefficients'][:5];n=np.r_[projection['coefficients'][5:],tail]
model=SharedScanObjective(raw,shift)
assert np.max(abs(model.original.correction(v,n[:model.clock_count])-target_correction))<1e-6
