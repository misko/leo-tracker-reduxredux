import json
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

root=Path('/tmp/three-track-investigation/space-track-pipeline-rerun')
dest=Path('/tmp/frame-band-identity-20261016');dest.mkdir(exist_ok=True)
d=json.loads((root/'frame_phase_crossband.json').read_text())
ch6=next(r for r in d['records'] if r['channel']=='CH6')
t=np.array(ch6['times_s']);phase=np.array(ch6['phase_samples']);x=t-210;h=(t>=210).astype(float)
models=[]
for name,design in [('quadratic',np.column_stack([x*x,x,np.ones(len(x))])),('quadratic_plus_step',np.column_stack([x*x,x,np.ones(len(x)),h])),('quadratic_plus_step_and_rate',np.column_stack([x*x,x,np.ones(len(x)),h,h*x]))]:
    coef=np.linalg.lstsq(design,phase,rcond=None)[0];rr=phase-design@coef;sse=float(rr@rr)
    models.append(dict(name=name,coefficients=coef.tolist(),rms_samples=float(np.sqrt(np.mean(rr**2))),max_residual_samples=float(np.max(abs(rr))),bic=float(len(t)*np.log(sse/len(t))+len(coef)*np.log(len(t))),residuals_samples=rr.tolist()))
pre=t<210;precoef=np.polyfit(x[pre],phase[pre],2);forecast_residual=phase-np.polyval(precoef,x)
out=dict(qualification='Descriptive phase-step test at the user-specified 210s boundary. Phase was already unwrapped from integer sample counters. No satellite identity or RF-frequency change is inferred from this fit alone.',sample_rate_hz=2500000,models=models,pre_turning_time_s=float(210-precoef[1]/(2*precoef[0])),pre_fit_rms_samples=float(np.sqrt(np.mean(forecast_residual[pre]**2))),post_minus_pre_forecast_samples=forecast_residual[~pre].tolist(),step_bracket_s=[float(t[pre].max()),float(t[~pre].min())])
(dest/'ch6_phase_step.json').write_text(json.dumps(out,indent=2)+'\n')
fig=Figure(figsize=(12,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
axes[0].plot(t,phase,'o',label='Measured CH6 frame phase');dense=np.linspace(t.min(),t.max(),500)
axes[0].plot(dense,np.polyval(precoef,dense-210),label='Pre-210s quadratic extrapolation')
stepfit=models[1]['coefficients'];xx=dense-210
axes[0].plot(dense,stepfit[0]*xx**2+stepfit[1]*xx+stepfit[2]+stepfit[3]*(dense>=210),'--',label='One quadratic + one phase step')
axes[0].set(xlabel='Time from scan origin (s)',ylabel='Unwrapped frame phase (samples)',title='CH6 phase around 210 s');axes[0].legend(fontsize=8)
axes[1].plot(t,forecast_residual,'o-');axes[1].axhline(0,color='gray',lw=.7);axes[1].set(xlabel='Time from scan origin (s)',ylabel='Measured minus pre-210s fit (samples)',title='A phase step versus smooth curvature')
for ax in axes:ax.axvspan(*out['step_bracket_s'],color='orange',alpha=.12);ax.grid(alpha=.2)
fig.savefig(dest/'ch6_phase_step.png',dpi=180)
print(json.dumps(out,indent=2))
