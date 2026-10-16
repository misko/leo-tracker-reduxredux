from pathlib import Path
code = Path('/tmp/scoped_timing_refit.py').read_text().split('initial=summary(v,n);')[0]
code = code.replace('((observations.receiver==0)&(observations.channel<=4))', '(observations.channel<=4)')
exec(compile(code, '/tmp/scoped_timing_refit.py', 'exec'))
final = json.loads((root/'shared_band_timing_fit.json').read_text())
assert final['audit']['accepted']
v = np.array(final['fit']['vector']); n = np.array(final['fit']['nuisance'])
module.predict_orbits = predict; module.elevation_geometry = elevation
try:
    e, details = model.evaluate_details(v, n)
    terms = e[3]
    sh = v[7] + zero_sum_basis(len(nums)) @ v[8:]
    p = module.predict_orbits(bank, obs, prior, v[:2], sh, derivatives=False)[0]
    residual = circular(obs.measured_hz[:,None] - model.original.correction(v,n[:model.clock_count])[:,None] - p)
    replay = json.loads((root/'extended_late_cfo_raw_replay.json').read_text())
    replay_by_row = {r['row']: r for r in replay['records']}
    out=[]
    for name,path,num in [('late_ch2','/tmp/rx1-ch2-170-190',69522),('early_ch2','/tmp/rx1-ch2-50-75',69433),('ch4','/tmp/rx1-ch4-40-100',69333)]:
        ix=np.load(path+'/arrays.npz')['rows']
        if name=='early_ch2': ix=ix[np.isin(obs.times_s[ix],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
        k=nums.index(num)
        for row in ix:
            order=np.argsort(terms.responsibilities[row])[::-1][:3]
            best=int(order[0]); associated=bool(terms.responsibilities[row,best]>terms.clutter_probability[row])
            record=dict(track=name,row=int(row),time_s=float(obs.times_s[row]),margin=float(obs.margin[row]),intended=num,intended_residual_hz=float(residual[row,k]),intended_probability=float(terms.responsibilities[row,k]),clutter_probability=float(terms.clutter_probability[row]),associated=associated,best=nums[best],exception=not(associated and best==k),top=[dict(satellite=nums[int(j)],residual_hz=float(residual[row,j]),probability=float(terms.responsibilities[row,j])) for j in order])
            sigma=float(np.broadcast_to(details['sigma_hz'], (len(obs.times_s),))[row])
            weight=float(details['visibility_weight'][row,k]); q=float(details['detection_probability'][k]); pdet=weight*q
            odds=pdet/(1-pdet)
            ratio=odds/(sigma*np.sqrt(2*np.pi))/(model.score.clutter_rate/(1/4.4e-6))
            record.update(sigma_hz=sigma,detection_probability=q,visibility_weight=weight,clutter_crossover_absolute_residual_hz=float(sigma*np.sqrt(2*np.log(ratio))) if ratio>1 else None)
            if int(row) in replay_by_row:
                change=float(replay_by_row[int(row)]['change_hz'])
                record.update(continuous_cfo_change_hz=change,continuous_cfo_intended_residual_hz=float(circular(residual[row,k]+change)))
            if best!=k:
                other_p=float(details['visibility_weight'][row,best]*details['detection_probability'][best])
                other_odds=other_p/(1-other_p)
                record.update(competitor_detection_probability=float(details['detection_probability'][best]),competitor_to_intended_detection_odds_ratio=other_odds/odds,competitor_to_intended_frequency_density_ratio=float(np.exp(-.5*(residual[row,best]**2-residual[row,k]**2)/sigma**2)))
            out.append(record)
    result=dict(qualification='Fixed saved experimental fit; per-point association and clutter audit, no refit.',points=out,exceptions=[r for r in out if r['exception']])
    (root/'three_track_exception_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['exceptions'],indent=2),flush=True)
finally:
    module.predict_orbits=original_predict; module.elevation_geometry=original_elevation
