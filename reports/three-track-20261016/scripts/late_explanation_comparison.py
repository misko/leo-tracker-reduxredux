exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from scipy.optimize import minimize_scalar
from leo.analysis.regional_position_bootstrap import observation_subset
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
f=json.loads((root/'timing_prior_compressed_0p5s.json').read_text());v=np.array(f['fit']['vector']);n=np.array(f['fit']['nuisance']);corr=model.original.correction(v,n[:model.clock_count]);sh=v[7]+zero_sum_basis(len(nums))@v[8:];k=nums.index(69522);one=bank.select([k]);ext=json.loads((root/'late_track_extension.json').read_text());rows=np.array(ext['selected_rows']);seed=np.isin(rows,ext['seed_rows']);sub=observation_subset(obs,rows);y=obs.measured_hz[rows]-corr[rows];base=predict_orbits(one,sub,prior,v[:2],np.array([sh[k]]),derivatives=False)[0][:,0];res=circular(y-base);d=base/(sub.rf_hz/1e9)+v[6];out=[]
for mode in ['offset','time','scale_offset']:
 for split in ['all','seed_to_extension','early_to_late','late_to_early']:
  train=np.ones(len(rows),bool) if split=='all' else seed if split=='seed_to_extension' else sub.times_s<=np.median(sub.times_s)
  if split=='late_to_early':train=~train
  test=train if split=='all' else ~train
  if mode=='time':
   def residual(timing):return circular(y-predict_orbits(one,sub,prior,v[:2],np.array([timing]),derivatives=False)[0][:,0])
   def loss(timing):return np.mean(residual(timing)[train]**2)
   grid=np.linspace(-5,5,101);start=grid[np.argmin([loss(t) for t in grid])];opt=minimize_scalar(loss,bounds=(max(-5,start-.15),min(5,start+.15)),method='bounded');rr=residual(opt.x);params=dict(total_timing_s=float(opt.x),extra_timing_s=float(opt.x-sh[k]))
  else:
   x=np.ones((len(rows),1)) if mode=='offset' else np.column_stack([d,np.ones(len(rows))]);coef=np.linalg.lstsq(x[train],res[train],rcond=None)[0];rr=res-x@coef;params=dict(offset_hz=float(coef[-1]),rf_delta_mhz=float(coef[0]*1000) if mode=='scale_offset' else 0)
  out.append(dict(mode=mode,split=split,parameters=params,parameter_count=2 if mode=='scale_offset' else 1,train_rms_hz=float(np.sqrt(np.mean(rr[train]**2))),test_rms_hz=float(np.sqrt(np.mean(rr[test]**2))),residuals_hz=rr.tolist()))
(root/'late_explanation_comparison.json').write_text(json.dumps(out,indent=2)+'\n')
fig=Figure(figsize=(11,4.5),layout='constrained');FigureCanvasAgg(fig);ax=fig.subplots();x=np.arange(4)
for mode,delta,label in [('offset',-.25,'One frequency offset'),('time',0,'One extra timing shift'),('scale_offset',.25,'RF scale + frequency offset')]:
 vals=[r['test_rms_hz'] for r in out if r['mode']==mode];ax.bar(x+delta,vals,.24,label=label)
 for xx,val in zip(x+delta,vals):ax.text(xx,val+4,f'{val:.0f}',ha='center',fontsize=8)
ax.set_xticks(x,['All 38 points','Seed → extension','Early → late','Late → early']);ax.set(ylabel='Frequency RMS (Hz)',title='Same points and splits: competing corrections for late CH2');ax.legend();ax.grid(axis='y',alpha=.2);fig.savefig(root/'late_explanation_comparison.png',dpi=160)
print(json.dumps([{k:v for k,v in r.items() if k!='residuals_hz'} for r in out],indent=2))
