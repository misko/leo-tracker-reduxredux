exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from leo.analysis.regional_position_bootstrap import observation_subset
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from scipy.optimize import minimize_scalar
f=json.loads((root/'timing_prior_compressed_0p5s.json').read_text());v=np.array(f['fit']['vector']);n=np.array(f['fit']['nuisance'])
corr=model.original.correction(v,n[:model.clock_count]);sh=v[7]+zero_sum_basis(len(nums))@v[8:]
pp=predict_orbits(bank,obs,prior,v[:2],sh,derivatives=False)[0]
phase=json.loads((root/'frame_phase_crossband.json').read_text())
allnums=new['provenance']['full_candidate_numbers'];full,_=build_regional_bank(cat,[lookup[num] for num in allnums],origin,obs,prior)
groups=[]
for rec in phase['records']:
    channel=int(rec['channel'][2:]);rows=np.flatnonzero((obs.receiver==0)&(obs.channel==channel)&np.isin(obs.times_s,rec['times_s']))
    assert len(rows)==rec['count']
    if channel==2:continue
    if channel==6:
        groups.extend([('CH6 before 210 s',rows[obs.times_s[rows]<210]),('CH6 after 210 s',rows[obs.times_s[rows]>=210])])
    else:groups.append((rec['channel'],rows))
out=[]
for label,rows in groups:
    sub=observation_subset(obs,rows);yy=obs.measured_hz[rows]-corr[rows];base=circular(yy-pp[rows,nums.index(69522)])
    scores=np.full(len(full.numbers),np.inf);timings=np.zeros(len(full.numbers))
    for timing in np.linspace(-5,5,201):
        pred,vis,_,_=predict_orbits(full,sub,prior,v[:2],np.full(len(full.numbers),timing),derivatives=False)
        rr=circular(yy[:,None]-pred);ss=np.mean(rr*rr,axis=0);ss[~vis.all(axis=0)]=np.inf;take=ss<scores;scores[take]=ss[take];timings[take]=timing
    refined=[]
    for k in np.argsort(scores)[:10]:
        one=full.select([int(k)])
        def loss(timing):
            prediction,visible,_,_=predict_orbits(one,sub,prior,v[:2],np.array([timing]),derivatives=False)
            if not visible.all():return float('inf')
            return float(np.mean(circular(yy-prediction[:,0])**2))
        opt=minimize_scalar(loss,bounds=(max(-5,timings[k]-.06),min(5,timings[k]+.06)),method='bounded')
        refined.append(dict(satellite=int(full.numbers[k]),timing_s=float(opt.x),rms_hz=float(np.sqrt(opt.fun))))
    refined.sort(key=lambda item:item['rms_hz'])
    out.append(dict(group=label,count=len(rows),times_s=sub.times_s.tolist(),baseline_69522_residuals_hz=base.tolist(),baseline_69522_rms_hz=float(np.sqrt(np.mean(base**2))),baseline_69522_mean_hz=float(np.mean(base)),best_candidates=refined[:5]))
    print(json.dumps(out[-1]),flush=True)
dest=Path('/tmp/frame-band-identity-20261016');dest.mkdir(exist_ok=True)
(dest/'carrier_identity_checks.json').write_text(json.dumps(dict(qualification='Groups are existing model-assigned 69522 points from the published phase figure. Re-searching their CFO against all 1035 candidates is conditional evidence, not independent identity validation. Position/calibration frozen from compressed timing-prior fit. Timing-only candidate search +/-5s, no added per-channel frequency offset.',candidate_count=len(full.numbers),groups=out),indent=2)+'\n')
fig=Figure(figsize=(12,4.5),layout='constrained');FigureCanvasAgg(fig);axes=fig.subplots(1,2)
for r in out:
    ax=axes[1] if r['group'].startswith('CH6') else axes[0]
    ax.plot(r['times_s'],r['baseline_69522_residuals_hz'],'o-',ms=4,lw=.6,label=r['group'])
for ax in axes:
    ax.axhline(0,color='gray',lw=.7);ax.set(xlabel='Time from scan origin (s)',ylabel='Carrier residual to 69522 (Hz)');ax.grid(alpha=.2);ax.legend(fontsize=8)
axes[0].set_title('CH5 and CH8: calibrated carrier evidence')
axes[1].set_title('CH6: carrier residual across the phase step');axes[1].axvspan(209.242395709,211.723735999,color='orange',alpha=.12)
fig.suptitle('Frame phase and RF carrier must be checked separately\nExisting assigned points; fixed calibration and orbit timing; no additional corrections')
fig.savefig(dest/'carrier_identity_checks.png',dpi=180)
