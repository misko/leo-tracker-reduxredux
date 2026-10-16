from pathlib import Path
code=Path('/tmp/replay_late_cfo.py').read_text()
code=code.replace("from leo.analysis.starlink.glrt_refinement_prototype import continuous_glrt_score", "from leo.analysis.starlink.glrt_refinement_prototype import continuous_glrt_score\nimport leo.analysis.starlink.pilot_methods as pilot_module\noriginal_take=pilot_module.fractional_take")
old="score,details=continuous_glrt_score(samples,source.sample_rate_hz,anchor=candidate.integer_epoch_sample,offset=candidate.fractional_epoch_offset_samples,conditioning_cfo_hz=candidate.fractional_tracking_cfo_hz,edge=probe.edge)"
new="""scale_trials=[]
  for ppm in [-5000,-2000,-1000,-500,-200,-100,-50,0,50,100,200,500,1000,2000,5000]:
   epsilon=ppm*1e-6
   def warped_take(values,positions,**kwargs):
    frame_period=source.sample_rate_hz/750
    anchor=candidate.integer_epoch_sample+candidate.fractional_epoch_offset_samples
    frame=np.floor((positions-anchor)/frame_period).astype(int)
    local=positions-anchor-np.rint(frame*frame_period)
    return original_take(values,positions+epsilon*(local-33.5*11),**kwargs)
   pilot_module.fractional_take=warped_take
   try:
    score,details=continuous_glrt_score(samples,source.sample_rate_hz,anchor=candidate.integer_epoch_sample,offset=candidate.fractional_epoch_offset_samples,conditioning_cfo_hz=candidate.fractional_tracking_cfo_hz,edge=probe.edge)
    frequency=candidate.fractional_tracking_cfo_hz+circular(score.tracking_cfo_hz-candidate.fractional_tracking_cfo_hz)
    scale_trials.append(dict(ppm=ppm,exact_score=score.exact_score,margin=score.margin,physical_cfo_hz=float(frequency/(1+epsilon)),physical_cfo_change_hz=float(frequency/(1+epsilon)-candidate.fractional_tracking_cfo_hz)))
   finally:pilot_module.fractional_take=original_take
  score,details=continuous_glrt_score(samples,source.sample_rate_hz,anchor=candidate.integer_epoch_sample,offset=candidate.fractional_epoch_offset_samples,conditioning_cfo_hz=candidate.fractional_tracking_cfo_hz,edge=probe.edge)"""
assert old in code;code=code.replace(old,new).replace("rec=dict(row=i,", "rec=dict(scale_trials=scale_trials,row=i,")
code=code.replace("'late_cfo_raw_replay.json'", "'late_within_frame_scale.json'").replace("print(json.dumps(rec),flush=True)", "print(json.dumps(dict(time_s=rec['time_s'],best_scale=max(scale_trials,key=lambda t:t['exact_score']),zero_scale=next(t for t in scale_trials if t['ppm']==0))),flush=True)")
exec(compile(code,__file__,'exec'))
