from pathlib import Path
code=Path('/tmp/rx2_counterpart_replay.py').read_text()
old="score,details=continuous_glrt_score(samples,source.sample_rate_hz,anchor=candidate.integer_epoch_sample,offset=candidate.fractional_epoch_offset_samples,conditioning_cfo_hz=expected,edge=probe.edge)"
new="""control_trials=[]
  for displacement in [0,137,503,997,1499]:
   anchor=(candidate.integer_epoch_sample+displacement)%round(source.sample_rate_hz/750)
   score,details=continuous_glrt_score(samples,source.sample_rate_hz,anchor=anchor,offset=candidate.fractional_epoch_offset_samples,conditioning_cfo_hz=expected,edge=probe.edge)
   control_trials.append(dict(displacement_samples=displacement,margin=score.margin,exact_score=score.exact_score,frequency_error_hz=float(circular(score.tracking_cfo_hz-expected))))
  score,details=continuous_glrt_score(samples,source.sample_rate_hz,anchor=candidate.integer_epoch_sample,offset=candidate.fractional_epoch_offset_samples,conditioning_cfo_hz=expected,edge=probe.edge)"""
assert old in code
code=code.replace(old,new).replace("rec=dict(row=i,", "rec=dict(control_trials=control_trials,row=i,")
code=code.replace("'rx2_counterpart_alias_corrected.json'", "'rx2_guidance_negative_controls.json'")
exec(compile(code,__file__,'exec'))
trials=[dict(row=r['row'],**trial) for r in out for trial in r['control_trials']]
summary={str(displacement):dict(trials=sum(t['displacement_samples']==displacement for t in trials),margin_pass=sum(t['displacement_samples']==displacement and t['margin']>=.025 for t in trials),margin_and_frequency_pass=sum(t['displacement_samples']==displacement and t['margin']>=.025 and abs(t['frequency_error_hz'])<1000 for t in trials),maximum_margin=max(t['margin'] for t in trials if t['displacement_samples']==displacement)) for displacement in [0,137,503,997,1499]}
(root/'rx2_guidance_control_summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
