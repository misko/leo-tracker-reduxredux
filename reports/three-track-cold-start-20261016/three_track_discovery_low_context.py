"""Use a ranked cold-discovery low-band calibration, without a final B donor."""
exec(open('/tmp/three_track_cold_context.py').read())
from leo.analysis.frozen_group_calibration import freeze_group_calibration
index=int(os.environ['THREE_TRACK_DISCOVERY_LOW_RANK']);assert 0<=index<3
eligible=[(key,row) for key,row in stages.items() if key.startswith('discovery-point:') and row['fits'].get('low',{}).get('converged')]
eligible.sort(key=lambda pair:(pair[1]['fits']['low']['objective'],pair[1]['east_km'],pair[1]['north_km']))
key,row=eligible[index];point_fit=row['fits']['low']
full_bank,_=build_regional_bank(cat,[lookup[num] for num in new['provenance']['full_candidate_numbers']],origin,cold_obs,prior)
point_bank=full_bank.select(row['satellite_indices'])
assert list(map(int,point_bank.numbers))==row['catalogue_numbers']
point_model=objective(prepared['low'],point_bank,prior,nodes)
assert len(point_fit['vector'])==point_model.size
calibration=freeze_group_calibration(point_model,point_fit)
correction=calibration.predict(obs.times_s,obs.rf_hz,obs.receiver,obs.channel>=5)
v=np.array(point_fit['vector']);n=np.empty(0)
model=SimpleNamespace(clock_count=0,original=SimpleNamespace(correction=lambda vv,nn:correction))
proof=dict(scope='Research candidate search under one low-band discovery calibration. The entire discovery fit is cold-trained; held probe groups absent. Calibration is extrapolated only as needed for lower-band target observations. No final fit or strict shared-source acceptance implied.',rank=index,stage=key,position_chart_km=v[:2].tolist(),low_training_objective=point_fit['objective'],derived_input_sha256=derivation['derived_input_sha256'])
(root/f'discovery_low_rank_{index}_context.json').write_text(json.dumps(proof,indent=2)+'\n')
