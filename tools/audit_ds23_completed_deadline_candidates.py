"""Fresh native replay of tentative deadline candidates before geographic scoring."""

from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import signal
import numpy as np

import inventory_ds23_completed_deadline_candidates as inventory
import run_ds23_dbg01_iteration_013 as current
from probe_ds23_owner_reentry import fine_view
from ds23_frequency_events import make_event_problem,attach_event_predictive
from audit_ds23_family_cavity import density
from probe_ds23_frequency_events import summary
from probe_ds23_reentry_family_cavity import assert_curved_gate_replay,assert_linear_gate_replay
from leo.analysis.research.retained_track_likelihood import profile
from run_algo01_ds23_sample import read,write,sha

OUT=inventory.OUT/'fresh_audit'


def one(selection):
    case=selection['case'];signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('120s deadline candidate replay cap')));signal.alarm(120)
    result=dict(case=case,all_passed=False,checks=[])
    try:
        current.configure();d=current.engine.current_setup(case);source=inventory.SOURCE/'reentry'/(case+'.json')
        if sha(source)!=selection['source_sha256']:raise ValueError('frozen deadline source changed')
        record=read(source);trial=record['trials'][selection['tentative_selected_index']];node=trial['node'];mask=np.asarray(trial['mask'],bool)
        if mask.shape!=d['keep'].shape or np.any(d['keep']&~mask):raise ValueError('deadline candidate drops original calibration')
        positions={r['component']:k for k,r in enumerate(node['seed']['rows'])}
        for row,sl,alias in zip(d['base'].rows,d['base'].slices,d['base'].alias,strict=True):
            if d['keep'][sl].any():
                k=positions[row['component']]
                if node['seed']['rows'][k]['candidate_index']!=row['candidate_index'] or node['aliases'][k]!=int(alias):raise ValueError('deadline candidate relabels original calibration')
        labels=sorted({r['candidate_index'] for r in node['seed']['rows']})
        if not np.allclose(np.asarray(trial['means']),d['all_means'][labels],rtol=0,atol=1e-12):raise ValueError('deadline prior means do not match current causal context')
        changed=dict(d,scan=fine_view(d['scan']),node=node,keep=mask,means=np.asarray(trial['means']),arms=trial['arms']);coverage={}
        for arm,saved in trial['arms'].items():
            p=make_event_problem(changed['scan'],node,mask,arm,np.asarray(saved['phase_reference']),d['powers'],changed['means'],d['model'],[]);attach_event_predictive(p,d['entries'],d['powers']);x=np.asarray(saved['endpoint_east_north_km']);c=p.calculate(x)
            delta=c['negative_twice_elbo']-saved['negative_twice_elbo']
            if abs(delta)>1e-5:raise ValueError('deadline completed endpoint does not replay')
            independent=density(changed,p,x,changed['means'],d['entries']);replay=summary(p,x,d['entries']);assert_curved_gate_replay(saved['gates'],replay['gates'])
            for old,new,e,sl in zip(saved['linear_gates'],replay['linear_gates'],d['entries'],p.linear_slices,strict=True):
                raw=c['linear_raw_prediction_residual_hz'][sl];terms=profile(raw,np.zeros(len(raw)),*p.scan.white[e['track_index']],bias_sigma=300.)
                assert_linear_gate_replay(old,new,dict(rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0])))
            baseline=current.engine.baseline.inventory(d,arm);old_build=current.engine.baseline.build;current.engine.baseline.build=lambda *_:p
            try:coverage[arm]=current.engine.baseline.inventory(changed,arm)
            finally:current.engine.baseline.build=old_build
            lost=set(baseline['accepted_observation_ids'])-set(coverage[arm]['accepted_observation_ids'])
            if lost:raise ValueError('deadline completed candidate loses original accepted IDs')
            result['checks'].append(dict(arm=arm,objective_difference=delta,original_IDs_preserved=True,**independent))
        result.update(all_passed=True,coverage=coverage,source_sha256=sha(source),trial_index=selection['tentative_selected_index'])
    except Exception as exc:
        import traceback
        result.update(error=repr(exc),traceback=traceback.format_exc())
    finally:signal.alarm(0)
    write(OUT/(case+'.json'),result);print(case,'fresh replay',result['all_passed'],result.get('error',''),flush=True);return dict(case=case,all_passed=result['all_passed'])


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve native deadline replay')
    source=inventory.OUT/'RF_inventory.json';frozen=read(source);eligible=[r for r in frozen['rows'] if r['eligible_pending_fresh_audit']]
    write(OUT/'protocol.json',dict(cases=[r['case'] for r in eligible],source_sha256=sha(Path(__file__)),RF_inventory_sha256=sha(source),
        workers=2,per_case_wall_seconds=120,no_new_fit_or_GPS_or_error_ranked_selection=True,
        original_current_mask_labels_aliases_priors_and_all_associated_IDs_must_be_preserved=True,
        saved_endpoint_expected_density_dense_prediction_and_original_gates_replayed=True,
        any_failure_retains_original_incumbent_explicitly=True))
    with ProcessPoolExecutor(max_workers=2) as pool:rows=list(pool.map(one,eligible))
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,all_passed=all(r['all_passed'] for r in rows),no_geographic_scoring=True))


if __name__=='__main__':main()
