"""Saved-context endpoint replay: zero prior/position refits, native alias coordinates."""
import argparse
from contextlib import contextmanager
from pathlib import Path
import sys
import numpy as np
import scipy.optimize as optimize
from position import HERE,REPO,read,write,sha

RECOVERY=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
sys.path[:0]=[str(RECOVERY),str(REPO/'src'),str(REPO/'tools'),'/tmp/algo03-feasible-deps']
import algo02_scan as algo
import recovery
from leo.analysis.research.retained_track_likelihood import PERIOD

def context_from_saved(root,case):
    """Read the saved selected model directly; validation performs no fitting."""
    root=Path(root);saved=read(root/'family_cavity/position'/(case+'.json'))
    assert saved['status']=='complete'
    selected=saved['selected'] if saved['accepted'] else None
    algo.bind_run_directory(root);scan=algo.load_scan(root,case)
    d=dict(case=case,scan=scan,node=selected['node'] if selected else saved['baseline_node'],
        keep=np.asarray(saved['original_mask'],bool),powers=np.asarray(saved['powers']),model=saved['model'],
        means=np.asarray(selected['means'] if selected else saved['baseline_means']),
        entries=selected['entries'] if selected else saved['baseline_entries'],
        arms=saved['policy_arms'],observations=read(root/case/'observations.json'))
    for element in scan.elements.values():
        provenance=element['provenance']
        assert max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])<=scan.receipt['cutoff_utc_ns']
    history=root/'causal_phase_history'/(case+'.json')
    forecast=read(history.with_name(case+'_forecast.json'))
    model,qualified=algo.validate_history(read(history),forecast,scan,sha(history))
    for key in ('shrinkage','multiplier','nu'):assert d['model'][key]==model[key],key
    assert all(r['validation_time_ns']<=scan.receipt['cutoff_utc_ns'] for r in forecast['transitions'])
    return d

@contextmanager
def forbid_refits():
    """Reject optimization, including aliases imported before this guard."""
    calls=[];originals=[]
    targets=[(recovery,n) for n in ('context','qualify','refit','constrained')]
    targets += [(algo,n) for n in ('history_fit','infer_algo02')]
    targets += [(optimize,n) for n in ('minimize','minimize_scalar','least_squares','differential_evolution','dual_annealing','basinhopping','shgo','direct','fmin') if hasattr(optimize,n)]
    forbidden={id(getattr(m,n)):m.__name__+'.'+n for m,n in targets}
    def reject(label):
        def blocked(*args,**kwargs):
            calls.append(label)
            raise RuntimeError('postprocessing attempted forbidden refit: '+label)
        return blocked
    # Scientific modules may hold ``from scipy.optimize import minimize`` aliases.
    modules=list(sys.modules.values())
    explicit={id(m) for m,n in targets}
    try:
        for module in modules:
            filename=getattr(module,'__file__','') or ''
            if id(module) not in explicit and not filename.startswith((str(REPO),'/srv/bulk/leo/research/')):continue
            for name,value in list(vars(module).items()):
                label=forbidden.get(id(value))
                if label:
                    originals.append((module,name,value));setattr(module,name,reject(label))
        yield calls
    finally:
        for module,name,value in reversed(originals):setattr(module,name,value)

def mapping(d,arm):
    p=recovery.build(d,arm,d['arms'][arm]['phase_reference'])
    observations={o['observation_id']:o for o in d['observations']};out={}
    for row,index,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
        track=p.scan.tracks[index]
        for oid,value,active in zip(track['observation_ids'],track['values'],p.keep[sl],strict=True):
            if not active:continue
            assert oid not in out
            out[oid]=dict(role='curved',norad=int(p.scan.norads[row['candidate_index']]),alias_lift=round((float(value)-observations[oid]['measured_cfo_hz'])/PERIOD)+int(alias))
    for entry in d['entries']:
        track=d['scan'].tracks[entry['track_index']]
        values=dict(zip(track['observation_ids'],track['values'],strict=True))
        for oid in entry['observation_ids']:
            assert oid not in out
            out[oid]=dict(role='predictive',norad=int(p.scan.norads[entry['candidate_index']]),alias_lift=round((float(values[oid])-observations[oid]['measured_cfo_hz'])/PERIOD)+int(entry['alias']))
    return out,p

def audit_job(job):
    root=Path(job['root']);case=job['case'];row=dict(job)
    receipts=[read(p) for p in (root/'read_receipts').glob('*.json')]
    denied=[p for r in receipts for p in r['denied_paths']]
    reads=sorted({p for r in receipts for p in r['read_paths']})
    assert not denied
    assert not any('gps' in Path(p).name.lower() or 'oracle' in Path(p).name.lower() for p in reads)
    qnap=[p for p in reads if Path(p).is_relative_to('/mnt/qnap01')];assert not qnap
    row.update(read_receipt_count=len(receipts),denied_paths=denied,qnap_read_paths=qnap,native_IQ_not_requested=True,read_paths=reads,read_audit_complete=len(receipts)>=3)
    if row['status']!='complete':
        row['endpoint_available']=False
        return row
    assert len(receipts)>=3 and row['seconds']<=240
    d=context_from_saved(root,case)
    maps={};problems={}
    for arm in ('c0','fitted_c'):maps[arm],problems[arm]=mapping(d,arm)
    assert maps['c0']==maps['fitted_c']
    a,b=problems['c0'],problems['fitted_c']
    assert np.array_equal(a.keep,b.keep) and np.array_equal(a.alias,b.alias) and a.labels==b.labels
    assert np.array_equal(a.point_noise,b.point_noise) and np.array_equal(a.scan.norads,b.scan.norads)
    members={arm:recovery.membership(d,arm,d['arms'][arm]) for arm in ('c0','fitted_c')}
    for key in ('curved_observation_ids','predictive_observation_ids'):assert members['c0'][key]==members['fitted_c'][key]
    added=set(read(root/case/'research_input_receipt.json')['added_native_observation_ids'])
    row['arms']={}
    for arm,m in members.items():
        saved=d['arms'][arm]
        row['arms'][arm]=dict(endpoint_latlon=saved['endpoint_latlon'],endpoint_east_north_km=saved['endpoint_east_north_km'],RMS_hz=saved['RMS_hz'],negative_twice_elbo=saved['negative_twice_elbo'],objective_replay_difference=m['objective_replay_difference'],likelihood_points=m['likelihood_points'],curved_points=m['curved_points'],predictive_points=m['predictive_points'],accepted_GLRT_count=m['associated'],total_GLRT_count=m['total_GLRT'],accepted_fraction=m['associated']/m['total_GLRT'],native_added_count=len(added),added_curved_ids=sorted(added&set(m['curved_observation_ids'])),added_predictive_ids=sorted(added&set(m['predictive_observation_ids'])),added_accepted_ids=sorted(added&set(m['accepted_observation_ids'])),accepted_observation_ids=m['accepted_observation_ids'],postfit_only_observation_ids=m['postfit_only_observation_ids'],active_curved_norads=m['active_curved_norads'])
    row.update(endpoint_available=True,matched_c_likelihood_IDs_candidate_labels_aliases_noise=True,likelihood_native_identity=maps['c0'])
    return row

def main(manifest_path):
    manifest=read(manifest_path)
    assert manifest['all_attempts_terminal'] and manifest['coherent_handoff_sealed']
    for path,h in manifest['protected_hashes'].items():assert sha(path)==h,path
    assert manifest['protected_hashes'][str(Path(__file__).resolve())]==sha(__file__)
    for path in manifest['terminal_seals']:
        seal=read(path);assert seal['all_terminal']
        assert not seal.get('denied_paths',seal.get('denied_reads',[]))
        for p,h in seal.get('output_sha256',seal.get('terminal_output_hashes',{})).items():assert sha(p)==h,p
    protocol=HERE/'endpoint_export_v2_protocol.json'
    write(protocol,dict(manifest_sha256=sha(manifest_path),source_sha256=sha(__file__),tests_sha256=sha(HERE/'test_export_endpoints_v2.py'),no_GPS_reference_or_scoring=True,saved_context_only=True,forbidden_refits=['prior qualification','position/prior refit','scipy optimizers and imported aliases'],native_predictive_lift='round((graph_value-native_CFO)/PERIOD)+entry_alias',terminal_seals={str(p):sha(p) for p in manifest['terminal_seals']}))
    with forbid_refits() as calls:rows=[audit_job(job) for job in manifest['jobs']]
    assert not calls
    write(HERE/'endpoint_packet.json',dict(schema='DS24-frozen-coherent-endpoint-packet/v2',export_protocol_sha256=sha(protocol),all_attempts_terminal=True,geographic_evaluation_performed=False,no_new_position_or_prior_optimization=True,forbidden_refit_call_count=len(calls),frequency_fit_and_position_accuracy_separate=True,predictive_and_curved_aliases_in_native_coordinates=True,rows=rows,comparison_aliases=manifest.get('comparison_aliases',[])))
    print(dict(rows=len(rows),complete=sum(r['status']=='complete' for r in rows),forbidden_refit_call_count=len(calls),geographic_evaluation_performed=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args();main(a.manifest)
