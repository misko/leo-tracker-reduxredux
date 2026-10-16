exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from dataclasses import replace
import leo.analysis.shared_scan_model as module
from leo.application.shared_fast_position import plain
f=json.loads((root/'timing_prior_compressed_0p5s.json').read_text());assert f['audit']['accepted'];v=np.array(f['fit']['vector']);n=np.array(f['fit']['nuisance']);model.score=replace(model.score,relative_sigma_s=.5)
comparison=json.loads((root/'late_explanation_comparison.json').read_text());delta=next(r for r in comparison if r['mode']=='time' and r['split']=='seed_to_extension')['parameters']['extra_timing_s']
original_predict=module.predict_orbits;original_elevation=module.elevation_geometry
def adjusted(observations):return replace(observations,times_s=observations.times_s+delta*((observations.receiver==0)&(observations.channel<=4)))
def scoped(fn,bank,observations,prior,point,shifts,*args,**kwargs):
 result=fn(bank,observations,prior,point,shifts,*args,**kwargs);indices=np.flatnonzero(np.asarray(bank.numbers)==69522)
 if not len(indices):return result
 k=int(indices[0]);other=fn(bank.select([k]),adjusted(observations),prior,point,np.asarray(shifts)[[k]],*args,**kwargs);out=[]
 for old,new in zip(result,other):
  if old is None:out.append(None);continue
  value=old.copy();value[:,k,...]=new[:,0,...];out.append(value)
 return tuple(out)
def predict(*args,**kwargs):return scoped(original_predict,*args,**kwargs)
def elevation(*args,**kwargs):return scoped(original_elevation,*args,**kwargs)
def summary(vv,nn):
 e=model.evaluate_joint(vv,nn);terms=e[3];b=terms.responsibilities.argmax(axis=1);a=terms.responsibilities[np.arange(len(b)),b]>terms.clutter_probability;sh=vv[7]+zero_sum_basis(len(nums))@vv[8:];p=module.predict_orbits(bank,obs,prior,vv[:2],sh,derivatives=False)[0];r=circular(obs.measured_hz[:,None]-model.original.correction(vv,nn[:model.clock_count])[:,None]-p)
 out=dict(objective=float(e[0]),nll=float(terms.nll),associated=int(a.sum()),associated_rms_hz=float(np.sqrt(np.mean(r[np.arange(len(b)),b][a]**2))),tracks=[])
 for name,path,num in [('late_ch2','/tmp/rx1-ch2-170-190',69522),('early_ch2','/tmp/rx1-ch2-50-75',69433),('ch4','/tmp/rx1-ch4-40-100',69333)]:
  ix=np.load(path+'/arrays.npz')['rows']
  if name=='early_ch2':ix=ix[np.isin(obs.times_s[ix],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
  k=nums.index(num);out['tracks'].append(dict(name=name,count=len(ix),associated=int(a[ix].sum()),intended_satellite=num,intended_matches=int(np.sum(a[ix]&(b[ix]==k))),intended_rms_hz=float(np.sqrt(np.mean(r[ix,k]**2)))))
 out['upper_69522_matches']=int(np.sum(a&(b==nums.index(69522))&(obs.receiver==0)&(obs.channel>=5)&(obs.times_s>=170)&(obs.times_s<=225)))
 return out
initial=summary(v,n);module.predict_orbits=predict;module.elevation_geometry=elevation
try:
 patched=summary(v,n);print(json.dumps(dict(before=initial,patched=patched,delta_s=delta)),flush=True)
 fit=module.bounded_shared_fit(model,v,n,local_center=v[:2],local_radius_km=25)
 (root/'scoped_timing_fit.json').write_text(json.dumps(dict(qualification='Research-only fixed satellite/receiver/band timing-shaped correction selected using original 27 target points. Not production model or verified clock correction.',delta_s=delta,**plain(fit)),indent=2)+'\n')
 result=dict(before=initial,patched=patched,delta_s=delta,audit=plain(fit['audit']))
 if fit.get('fit'):result['after']=summary(np.array(fit['fit']['vector']),np.array(fit['fit']['nuisance']))
 (root/'scoped_timing_result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
finally:module.predict_orbits=original_predict;module.elevation_geometry=original_elevation
