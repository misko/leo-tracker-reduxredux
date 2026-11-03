"""Replay accepted spatial means and quadrature from stored RF score nodes."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np

from ds23_frequency_events import make_event_problem, attach_event_predictive
from ds23_spatial_score_integration import score_integral
from probe_ds23_frequency_events import cached, summary
from probe_ds23_synthetic_known_nuisance import setup, SOURCE
from run_ds23_spatial_score_mean_validation import OUT
from run_ds23_combined_recovery_full import ARMS, valid
from run_algo01_ds23_sample import ROOT, read, write, sha


def replay_case(case, site):
    saved = read(OUT/(case+'.json'))
    scan,node,mask,powers,means,hyper,entries,truth,baseline=setup(case,site)
    if saved['status']!='complete': raise ValueError('spatial mean trial incomplete')
    rows=[]; pair={}
    for arm in ARMS:
        r=saved['arms'][arm]; mean_arm=r['mean_arm']; endpoint=np.asarray(mean_arm['endpoint_east_north_km'])
        p=make_event_problem(scan,node,mask,arm,np.asarray(mean_arm['phase_reference']),powers,means,hyper,[])
        attach_event_predictive(p,entries,powers); cached(p)
        fresh=summary(p,endpoint,entries); fresh['final_phase_change_s']=mean_arm['final_phase_change_s']; pair[arm]=fresh
        objective_delta=float(fresh['negative_twice_elbo']-mean_arm['negative_twice_elbo'])
        if abs(objective_delta)>1e-6 or fresh['linear_calibration_max_difference']!=0:
            raise ValueError('spatial mean objective or curved calibration failed replay')
        for key in ('gates','linear_gates'):
            a=fresh[key]['tracks'] if key=='gates' else fresh[key]
            b=mean_arm[key]['tracks'] if key=='gates' else mean_arm[key]
            if [(t['component'],t['compatible']) for t in a]!=[(t['component'],t['compatible']) for t in b]:
                raise ValueError('original gate booleans failed replay')
        anchor=np.asarray(baseline['arms'][arm]['endpoint_east_north_km'])
        for label in ('coarse','fine'):
            stored=r[label]; lookup={tuple(np.round(n['position'],10)):n['score'] for n in stored['nodes']}
            replayed=score_integral(lambda x:lookup[tuple(np.round(x,10))], anchor,
                np.asarray(r['local_covariance_km2']), stored['order'])
            np.testing.assert_allclose(replayed['mean'],stored['mean'],rtol=0,atol=1e-12)
            if abs(replayed['log_relative_mass']-stored['log_relative_mass'])>1e-12:
                raise ValueError('spatial integration did not reproduce stored score nodes')
        rows.append(dict(case=case,arm=arm,baseline_error_km=r['baseline_error_km'],
            mean_error_km=mean_arm['synthetic_position_error_km'], RF_objective_replay_difference=objective_delta,
            position_shift_from_mode_km=float(np.linalg.norm(endpoint-anchor)),
            numerical_mean_change_5_to_9_km=r['mean_change_km'],
            score_node_quadrature_replayed=True, RF_node_values_not_all_independently_recomputed=True))
    if saved['paired_accepted']!=(all(r['numerically_qualified'] for r in saved['arms'].values()) and valid(pair)):
        raise ValueError('paired acceptance failed replay')
    return rows


def main():
    protocol=read(OUT/'protocol.json'); evaluation=read(OUT/'evaluation.json')
    if evaluation['completed']!=len(protocol['cases']): raise ValueError('incomplete spatial comparison')
    for name,expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=expected: raise ValueError('spatial inference implementation changed')
    rows=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(replay_case,c,protocol['site_by_case'][c]) for c in protocol['cases']]):
            rows.extend(f.result())
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,arm in zip(axes,ARMS,strict=True):
        selected=[r for r in rows if r['arm']==arm]
        base=np.array([r['baseline_error_km'] for r in selected]); trial=np.array([r['mean_error_km'] for r in selected])
        order=np.argsort(base)
        ax.bar(np.arange(len(base)),1000*(trial-base)[order],color=np.where((trial-base)[order]<0,'#197c91','#c44c31'))
        ax.axhline(0,color='black',lw=.7); ax.grid(axis='y',alpha=.2)
        ax.set(title=arm,xlabel='Synthetic case, ordered by baseline error',ylabel='Error change, spatial mean minus mode (m)')
    fig.suptitle('Local score integration changes errors by metres, not the required hundreds of metres\n20 fixed synthetic templates · unchanged observations and causal priors · not real-data accuracy')
    fig.tight_layout(); fig.savefig(OUT/'spatial_mean_error_changes.png',dpi=175); plt.close(fig)
    write(OUT/'independent_replay_audit.json',dict(rows=rows,replayed_endpoint_arms=len(rows),
        maximum_RF_replay_difference=max(abs(r['RF_objective_replay_difference']) for r in rows),
        protocol_sha256=sha(OUT/'protocol.json'),evaluation_sha256=sha(OUT/'evaluation.json'),
        audit_source_sha256=sha(Path(__file__)),
        limitation='Quadrature was replayed from saved node scores; endpoint objectives/gates were recomputed. This is a local generalized score measure, not a calibrated full regional posterior.',
        real_DS23_accuracy_gain=False))
    print('SPATIAL_MEAN_AUDIT_COMPLETE',len(rows),'endpoint arms',flush=True)


if __name__=='__main__': main()
