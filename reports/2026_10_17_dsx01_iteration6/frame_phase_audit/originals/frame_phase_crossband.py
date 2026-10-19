exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
f=json.loads((root/'timing_prior_compressed_0p5s.json').read_text());v=np.array(f['fit']['vector']);n=np.array(f['fit']['nuisance']);terms=model.evaluate_joint(v,n)[3];b=terms.responsibilities.argmax(axis=1);a=terms.responsibilities[np.arange(len(b)),b]>terms.clutter_probability;k=nums.index(69522);lower=np.array(json.loads((root/'late_track_extension.json').read_text())['selected_rows']);upper=np.flatnonzero(a&(b==k)&(obs.receiver==0)&(obs.channel>=5)&(obs.times_s>=170)&(obs.times_s<=225));probes={(p.visit_index,p.receiver_id,p.probe_index):p for p in source.probes};period=source.sample_rate_hz/750;records=[];fig=Figure(figsize=(11,4.5),layout='constrained');FigureCanvasAgg(fig);ax=fig.subplots()
for label,rows in [('CH2',lower)]+[(f'CH{ch}',upper[obs.channel[upper]==ch]) for ch in [5,6,8]]:
 if len(rows)<3:continue
 phase=[]
 for i in rows:
  point=points[i];probe=probes[(point.visit_index,point.receiver_id,point.probe_index)];candidate=next(c for c in probe.candidates if c.candidate_rank==point.candidate_rank);counter=probe.valid_start_counter-source.timing.session_start_device_sample_counter+probe.probe_start_ms*source.sample_rate_hz//1000
  phase.append((((counter*750)%source.sample_rate_hz)/750+candidate.integer_epoch_sample+candidate.fractional_epoch_offset_samples)%period)
 phase=np.unwrap(np.array(phase)*2*np.pi/period)*period/(2*np.pi);t=obs.times_s[rows];coef=np.polyfit(t-185,phase,2);rr=phase-np.polyval(coef,t-185);records.append(dict(channel=label,count=len(rows),times_s=t.tolist(),phase_samples=phase.tolist(),quadratic_coefficients=coef.tolist(),slope_at_185_samples_s=float(coef[1]),curvature_samples_s2=float(2*coef[0]),fit_rms_samples=float(np.sqrt(np.mean(rr**2)))))
 ax.scatter(t,phase-np.polyval(coef,185-185),s=18,label=label)
ax.set(xlabel='Time (s)',ylabel='Unwrapped frame phase, centered at fitted t=185 s (samples)',title='A second observable: frame timing across bands\nA separate constant phase offset is removed from each channel');ax.grid(alpha=.2);ax.legend();fig.savefig(root/'frame_phase_crossband.png',dpi=160)
(root/'frame_phase_crossband.json').write_text(json.dumps(dict(frame_period_samples=period,records=records,qualification='Modulo-frame epochs reconstructed from integer hardware counters. Per-channel quadratic fits are descriptive; no timestamp or sample-rate correction applied.'),indent=2)+'\n');print(json.dumps([{k:v for k,v in r.items() if k not in ['times_s','phase_samples']} for r in records],indent=2))
