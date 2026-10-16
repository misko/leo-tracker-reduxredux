exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
f=json.loads((root/'track_seed_fit.json').read_text());assert f['audit']['accepted']
v=np.array(f['fit']['vector']);n=np.array(f['fit']['nuisance'])
terms=model.evaluate_joint(v,n)[3];best=terms.responsibilities.argmax(axis=1);associated=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
correction=model.original.correction(v,n[:model.clock_count]);shifts=v[7]+zero_sum_basis(len(nums))@v[8:]
pred=predict_orbits(bank,obs,prior,v[:2],shifts,derivatives=False)[0];r=circular(obs.measured_hz[:,None]-correction[:,None]-pred)
s=json.loads((root/'track_seed_result.json').read_text());s['associated_fraction']=float(associated.mean());s['associated_rms_hz']=float(np.sqrt(np.mean(r[np.arange(len(best)),best][associated]**2)))
for t,path in zip(s['tracks'],['/tmp/rx1-ch2-170-190','/tmp/rx1-ch2-50-75','/tmp/rx1-ch4-40-100']):
 rows=np.load(path+'/arrays.npz')['rows']
 if '50–75' in t['track']:rows=rows[np.isin(obs.times_s[rows],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
 k=int(np.argmin(np.mean(r[rows]**2,axis=0)));t.update(best_satellite=nums[k],rms_hz=float(np.sqrt(np.mean(r[rows,k]**2))),offset_hz=float(np.mean(r[rows,k])),centered_rms_hz=float(np.std(r[rows,k])),timing_s=float(shifts[k]))
(root/'track_seed_report.json').write_text(json.dumps(s,indent=2)+'\n')
result['track_seed']=s;arrays['track_seed_assigned_residual']=np.where(associated,abs(r[np.arange(len(best)),best]),np.inf)
fig=Figure(figsize=(13,5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2);x=np.arange(4)
for key,color,delta,label in [('original','#D55E00',-.26,'Original · Hugging Face'),('space_track','#0072B2',0,'Full rerun · Space-Track'),('track_seed','#009E73',.26,'Space-Track + inspected-track seed')]:
 d=result[key];values=[d['associated_fraction']]+[t['associated']/t['count'] for t in d['tracks']];bars=axes[0].bar(x+delta,values,.25,color=color,label=label)
 for b,val in zip(bars,values):axes[0].text(b.get_x()+b.get_width()/2,val+.015,f'{val:.0%}',ha='center',fontsize=8)
 rr=np.sort(arrays[key+'_assigned_residual']);finite=np.isfinite(rr);axes[1].step(rr[finite],np.arange(1,finite.sum()+1)/len(rr),where='post',color=color,label=label)
axes[0].set_xticks(x,['All observations','CH2 170–190 s','CH2 50–75 s','CH4 40–100 s'],rotation=15);axes[0].set(ylim=(0,1.1),ylabel='Fraction associated',title='Same 4,797 observations')
axes[1].set(xscale='log',xlim=(1,1000),ylim=(0,1),xlabel='Absolute frequency residual (Hz)',ylabel='Fraction of all observations',title='Unassociated observations stay in denominator')
for ax in axes:ax.grid(alpha=.2);ax.legend(fontsize=8)
fig.suptitle('Space-Track rerun and local-optimization diagnostic\nGreen uses inspected tracks for initialization: in-sample evidence, not position-accuracy validation',fontsize=12)
fig.savefig(root/'track_seed_comparison.png',dpi=160)
print(json.dumps(s,indent=2))
