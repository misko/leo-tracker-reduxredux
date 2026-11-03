"""Training-only coherent identities with one shared RX1 offset/drift adjustment."""
import os
if os.environ.get('THREE_TRACK_ALTERNATE_DONOR'):
    exec(open('/tmp/three_track_alternate_donor_context.py').read())
else:
    exec(open('/tmp/three_track_cold_context.py').read())
import time
from scipy.optimize import minimize
from leo.analysis.regional_position_bootstrap import observation_subset

started=time.monotonic();fold=os.environ['THREE_TRACK_COLD_FOLD']
point_override=os.environ.get('THREE_TRACK_COHERENT_POINT')
if point_override:
    point=np.array([float(x) for x in point_override.split(',')]);assert point.shape==(2,) and np.linalg.norm(point)<=prior.radius_km
    v[:2]=point
full,_=build_regional_bank(cat,[lookup[num] for num in new['provenance']['full_candidate_numbers']],origin,obs,prior)
correction=model.original.correction(v,n[:model.clock_count])
families=[];sig=125.;time_center=125.;time_scale=100.
grid=np.linspace(-5,5,201)
for target in derivation['targets']:
    rows=np.array(target['training_rows']);assert np.all(obs.receiver[rows]==0) and np.all(obs.channel[rows]<=4)
    sub=observation_subset(obs,rows);x=(sub.times_s-time_center)/time_scale
    y=obs.measured_hz[rows]-correction[rows]
    count=len(rows);sum_x=x.sum();sum_xx=x@x
    linear=[];cross=[];square=[];valid=[]
    for shift_s in grid:
        prediction,visible,_,_=predict_orbits(full,sub,prior,v[:2],np.full(len(full.numbers),shift_s),derivatives=False)
        residual=circular(y[:,None]-prediction)
        linear.append(residual.sum(axis=0));cross.append(x@residual);square.append(np.sum(residual*residual,axis=0));valid.append(visible.all(axis=0))
    square=np.array(square).ravel();valid=np.array(valid).ravel()
    fixed=square/sig**2+np.repeat((grid/2)**2,len(full.numbers));fixed[~valid]=np.inf
    families.append(dict(target=target,count=count,sum_x=sum_x,sum_xx=sum_xx,
                         linear=np.array(linear).ravel(),cross=np.array(cross).ravel(),fixed=fixed))

def scores(family,coeff):
    a,b=coeff
    return family['fixed']+(-2*a*family['linear']-2*b*family['cross']+family['count']*a*a+2*a*b*family['sum_x']+b*b*family['sum_xx'])/sig**2

def loss(coeff):
    # Prior and bounds are common to every candidate and both temporal folds.
    return float(sum(np.min(scores(f,coeff)) for f in families)+(coeff[0]/4000)**2+(coeff[1]/2000)**2)

best=np.array([0.,0.]);best_value=loss(best);width=np.array([8000.,4000.])
for level in range(4):
    center=best.copy()
    for a in np.linspace(max(-8000,center[0]-width[0]),min(8000,center[0]+width[0]),17):
        for b in np.linspace(max(-4000,center[1]-width[1]),min(4000,center[1]+width[1]),17):
            candidate=np.array([a,b]);value=loss(candidate)
            if value<best_value:best=candidate;best_value=value
    width/=4
opt=minimize(loss,best,method='Nelder-Mead',bounds=[(-8000,8000),(-4000,4000)],options=dict(maxiter=300,xatol=1e-6,fatol=1e-6))
if opt.fun<best_value:best=opt.x;best_value=float(opt.fun)
records=[]
for family in families:
    sc=scores(family,best);index=int(np.argmin(sc));shift_index,k=divmod(index,len(full.numbers));shift_s=float(grid[shift_index]);satellite=int(full.numbers[k])
    # Runner-up must be a different satellite, not a neighboring timing grid cell.
    by_identity=sc.reshape(len(grid),-1).min(axis=0);others=by_identity.copy();others[k]=np.inf
    record=dict(track=family['target']['track'],satellite=satellite,timing_s=shift_s,
                training_score=float(sc[index]),other_identity_score_gap=float(others.min()-sc[index]))
    for phase in ['training','test']:
        rows=np.array(family['target'][phase+'_rows']);sub=observation_subset(obs,rows)
        prediction=predict_orbits(full.select([k]),sub,prior,v[:2],np.array([shift_s]),derivatives=False)[0][:,0]
        adjustment=best[0]+best[1]*(sub.times_s-time_center)/time_scale
        residual=circular(obs.measured_hz[rows]-correction[rows]-prediction-adjustment)
        record[phase+'_rms_hz']=float(np.sqrt(np.mean(residual**2)))
        record[phase+'_residual_hz']=residual.tolist()
    record['passes_training_gate']=record['training_rms_hz']<=375 and record['other_identity_score_gap']>=20
    records.append(record)
suffix='' if not os.environ.get('THREE_TRACK_ALTERNATE_DONOR') else '_B_'+os.environ['THREE_TRACK_ALTERNATE_DONOR']
if point_override:suffix+='_point_'+point_override.replace(',','_')
result=dict(qualification='Three predeclared coherent track groups, one identity per group. Identities, grid timing and shared RX1 lower-band offset/drift correction selected on training observations only. Full regional bank, cold position and other calibration frozen. No original full-scan initialization or candidate-specific exception. Test measurements evaluated only after all parameters selected. This is not blind track extraction or a position-accuracy result.',fold=fold,derived_input_sha256=derivation['derived_input_sha256'],candidate_count=len(full.numbers),offset_hz=float(best[0]),drift_hz_s=float(best[1]/time_scale),time_center_s=time_center,offset_prior_sigma_hz=4000,drift_prior_sigma_hz_s=20,offset_bound_hz=8000,drift_bound_hz_s=40,training_objective=best_value,optimizer_success=bool(opt.success),elapsed_seconds=time.monotonic()-started,tracks=records)
result['position_chart_km']=v[:2].tolist();result['position_override']=bool(point_override)
path=root/('coherent_receiver_search'+suffix+'.json');path.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({**result,'tracks':[{k:v for k,v in r.items() if 'residual_hz' not in k} for r in records]},indent=2),flush=True)
