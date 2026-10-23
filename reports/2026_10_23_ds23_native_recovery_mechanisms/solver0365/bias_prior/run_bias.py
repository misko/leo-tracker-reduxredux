"""Native-only path offset-prior variance diagnostic, never calibration."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_solver as s
import numpy as np
import signal,time
import ds23_frequency_events as events
from ds23_predictive_linear import predictive_residual as original_predictive_residual
from ds23_frozen_precision import conditional_gaussian
OUT=Path(__file__).resolve().parent

def predictive_with_bias(raw,design,curved_gram,sigma,groups,bias_sigmas):
    y,u=np.asarray(raw,float),np.asarray(design,float);g=np.asarray(groups)
    gram=np.asarray(curved_gram,float);root=np.linalg.cholesky(gram)
    uncertainty=np.linalg.solve(root,u.T).T
    sigmas=np.asarray(bias_sigmas,float)
    if len(sigmas)!=int(g.max())+1:raise ValueError('one declared bias prior per whole path required')
    biases=np.zeros((len(y),len(sigmas)));biases[np.arange(len(y)),g]=sigmas[g]
    features=np.column_stack((uncertainty,biases))
    return conditional_gaussian(y,features,np.asarray(sigma,float),np.ones(len(y)),np.ones(len(y)),np.ones(features.shape[1]),1.)

def configure(entries,parent_entries,native_sigma):
    original={e['component'] for e in parent_entries}
    sigmas=[300. if e['component'] in original else float(native_sigma) for e in entries]
    changed=[e['component'] for e in entries if e['component'] not in original]
    assert all(k.startswith('GRAPH_PATH_persistent5s_') for k in changed)
    def predictive(raw,design,curved_gram,sigma,groups,bias_sigma=300.):
        assert bias_sigma==300.
        return predictive_with_bias(raw,design,curved_gram,sigma,groups,sigmas)
    events.predictive_residual=predictive
    return dict(entry_bias_sigmas_hz=sigmas,changed_components=changed,
                original_components=[e['component'] for e in parent_entries])

def replay300(d,kind,primary):
    return {a:s.replay(d,kind,(a,fit)) for a,fit in primary['arms'].items()}

def main():
    protocol=dict(cases=['DS23-0259','DS23-0041','DS23-0272'],arms=['c0','fitted_c'],native_bias_sigmas_hz=[300,600,3000],
        fit='ordinary cold [0,0], zero phase references, 5x48 Gauss Newton',seconds_cap_per_fit=180,
        original_predictive_path_bias_sigma_hz=300,
        frozen='curved model, calibration normal equations, observations, candidate IDs, aliases, gates and phase budgets',
        hypothesis='new native whole-path mean mismatch; offset uncertainty diagnostic with shared predictive covariance retained',
        interpretation='600 predeclared variance diagnostic not promoted; 3000 mean-uninformative extreme diagnostic only; no GPS selection')
    s.write(OUT/'protocol.json',protocol);result=dict(protocol=protocol,cases=[])
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180 second fit cap')))
    for case in protocol['cases']:
        d,kind,primary,frozen,selected=s.setup(case);parent=frozen['ordinary_graph']
        record=dict(case=case,entries=d['entries'],parent_entries=parent['entries'],selected_paths=selected,fits=[],replay={})
        configure(d['entries'],parent['entries'],300);record['replay']=replay300(d,kind,primary)
        result['cases'].append(record);s.write(OUT/'results.json',result)
        for sigma in protocol['native_bias_sigmas_hz']:
            config=configure(d['entries'],parent['entries'],sigma)
            for arm in protocol['arms']:
                signal.alarm(180);start=time.monotonic()
                try:
                    fit=s.exp.ordinary(d,kind,arm)
                    cov=s.exp.paths.coverage(d,kind,arm,fit)
                    preserves=set(parent['coverage'][arm]['accepted_observation_ids'])<=set(cov['accepted_observation_ids'])
                    qualified=bool(s.qualifies(fit) and preserves)
                    p=s.exp.paths.build(d,kind,arm,fit['phase_reference']);x=np.asarray(fit['endpoint_east_north_km'])
                    state=p.curved_calculate(x)
                    # Evaluate every endpoint under the unchanged sigma300 full-mask model.
                    configure(d['entries'],parent['entries'],300)
                    p=s.exp.paths.build(d,kind,arm,fit['phase_reference'])
                    common=s.snapshot(p,x,d['entries'])
                    configure(d['entries'],parent['entries'],sigma)
                    row=dict(arm=arm,native_bias_sigma_hz=sigma,configuration=config,summary=fit,coverage=cov,
                        original_parent_ids_preserved=preserves,qualified=qualified,common_sigma300=common,
                        curved_calibration_coefficient=state['coefficient'],seconds=time.monotonic()-start)
                except TimeoutError as exc:row=dict(arm=arm,native_bias_sigma_hz=sigma,status='timeout',error=str(exc))
                finally:signal.alarm(0)
                record['fits'].append(row);s.write(OUT/'results.json',result)
                print(case,sigma,arm,row.get('summary',{}).get('minimum_gate_slack'),row.get('seconds'),flush=True)
    events.predictive_residual=original_predictive_residual
if __name__=='__main__':main()
