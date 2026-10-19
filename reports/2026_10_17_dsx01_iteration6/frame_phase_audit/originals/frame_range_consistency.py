exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from leo.analysis.regional_position_score import observer,LIGHT_KM_S
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
f=json.loads((root/'timing_prior_compressed_0p5s.json').read_text());v=np.array(f['fit']['vector']);n=np.array(f['fit']['nuisance']);sh=v[7]+zero_sum_basis(len(nums))@v[8:];terms=model.evaluate_joint(v,n)[3];best=terms.responsibilities.argmax(axis=1);a=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability;probes={(p.visit_index,p.receiver_id,p.probe_index):p for p in source.probes};fs=source.sample_rate_hz;period=fs/750;site=observer(prior,v[:2])[0];groups=[]
lower=np.array(json.loads((root/'late_track_extension.json').read_text())['selected_rows']);groups.append(('69522 RX1 CH2',lower,69522))
for num,rx,ch,start,end in [(69522,0,5,170,200),(69522,0,8,170,200),(100168,1,3,150,210),(60372,1,1,90,170),(59326,1,2,170,300)]:
 ix=np.flatnonzero(a&(best==nums.index(num))&(obs.receiver==rx)&(obs.channel==ch)&(obs.times_s>=start)&(obs.times_s<=end))
 if len(ix)>=10:groups.append((f'{num} RX{rx+1} CH{ch}',ix,num))
records=[]
for label,rows,num in groups:
 t=[];phase=[]
 for i in rows:
  point=points[i];probe=probes[(point.visit_index,point.receiver_id,point.probe_index)];c=next(c for c in probe.candidates if c.candidate_rank==point.candidate_rank);counter=probe.valid_start_counter-source.timing.session_start_device_sample_counter+probe.probe_start_ms*fs//1000;epoch=c.integer_epoch_sample+c.fractional_epoch_offset_samples;t.append(counter/fs+epoch/fs);phase.append((((counter*750)%fs)/750+epoch)%period)
 t=np.array(t);phase=np.unwrap(np.array(phase)*2*np.pi/period)*period/(2*np.pi);k=nums.index(num);q=t+sh[k];position=np.column_stack([np.interp(q,bank.nodes_s,bank.position_km[k,:,j]) for j in range(3)]);delay=np.linalg.norm(position-site,axis=1)/LIGHT_KM_S*fs;x=np.column_stack([np.ones(len(t)),t-t.mean()]);obs_curve=phase-x@np.linalg.lstsq(x,phase,rcond=None)[0];range_curve=delay-x@np.linalg.lstsq(x,delay,rcond=None)[0];physical_error=obs_curve-range_curve;reversed_error=obs_curve+range_curve
 records.append(dict(label=label,count=len(t),time_span_s=float(np.ptp(t)),observed_quadratic_curvature_samples_s2=float(2*np.polyfit(t-t.mean(),phase,2)[0]),range_quadratic_curvature_samples_s2=float(2*np.polyfit(t-t.mean(),delay,2)[0]),positive_range_rms_samples=float(np.sqrt(np.mean(physical_error**2))),negative_range_rms_samples=float(np.sqrt(np.mean(reversed_error**2))),times_s=t.tolist(),observed_detrended_samples=obs_curve.tolist(),range_detrended_samples=range_curve.tolist()))
(root/'frame_range_consistency.json').write_text(json.dumps(dict(qualification='Descriptive modulo-frame phase versus geometric range, at first detected frame epoch; separate constant and linear drift removed. No claim that transmitted frame epochs are fixed.',records=records),indent=2)+'\n');print(json.dumps([{k:v for k,v in r.items() if not isinstance(v,list)} for r in records],indent=2))
fig=Figure(figsize=(12,4.5),layout='constrained');FigureCanvasAgg(fig);axs=fig.subplots(1,2)
for ax,r in zip(axs,records[:2]):
 ax.plot(r['times_s'],r['observed_detrended_samples'],'o',ms=4,label='Observed frame phase');ax.plot(r['times_s'],r['range_detrended_samples'],label='+ geometric delay');ax.plot(r['times_s'],-np.array(r['range_detrended_samples']),label='− geometric delay (diagnostic)');ax.set(title=r['label'],xlabel='Time (s)',ylabel='After removing constant + linear drift (samples)');ax.legend(fontsize=8);ax.grid(alpha=.2)
fig.suptitle('Frame epochs cannot yet be treated as an uncorrected propagation-delay observable');fig.savefig(root/'frame_range_consistency.png',dpi=160)
