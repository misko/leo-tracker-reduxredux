"""Frozen cohort and exact incumbent reconstruction for bounded recovery trials."""
from pathlib import Path
import json, gzip, hashlib, copy, os
import numpy as np

ROOT=Path(__file__).resolve().parent
RELEASE=Path(__file__).resolve().parents[2]

ARMS=('c0','fitted_c')
POLICIES={'48h_15s':(48,15,False),'72h_15s':(72,15,False),
          '72h_30s':(72,30,False),'72h_30s_recency':(72,30,True)}

def read(p):return json.loads(Path(p).read_text())
def write(p,z):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp-'+str(os.getpid()))
    tmp.write_text(json.dumps(z,indent=2,allow_nan=False,default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v))+'\n')
    tmp.replace(p)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def reconstruct(z):
    from diagnose_all_large_tracks import context
    from predictive_new_family import NewFamily
    from ds23_frequency_events import make_event_problem,attach_event_predictive
    from probe_ds23_frequency_events import cached
    from debug_fast_graph_unassociated import memberships
    inv=read(z['inventory_path']);d=context(inv);sel=z['selected'];gap=z['gap_selected']
    entries=list(d['entries']);families=[];saved={};conditional=[];protocol={}
    if sel:
        if sel['kind'] in ('new_family','shared_family'):
            path=Path(sel['trial']);protocol=read(path/'protocol.json')
            for source in protocol.get('inactive_fragment_sources',[]):
                from inactive_graph_fragment import validated_inactive_context
                d,_=validated_inactive_context(d,inv,Path(source))
            for source in protocol.get('graph_bundle_sources',[]):
                from predictive_graph_bundle import validated_bundle_context
                d,_=validated_bundle_context(d,inv,Path(source))
            if protocol.get('measurement_refinements'):raise ValueError('Unsupported modified measurement incumbent')
            if sel['kind']=='new_family':
                saved=read(path/'new_family.json')['arms'];pr=protocol['family_prior']
                families=[NewFamily(d['scan'],protocol['targets'],d['model'],phase_step=pr['phase_step_s'],
                    phase_limit_s=pr.get('phase_limit_s',15),allow_uncalibrated_label=True)]
            else:
                saved=read(path/'target_0.json')['arms'];entries+=protocol['targets']
                if protocol.get('conditional_satellite_refresh'):conditional=[t['candidate_index'] for t in protocol['targets']]
                if protocol.get('shared_satellite_refresh'):raise ValueError('Unsupported marginal shared refresh')
        elif sel['kind']=='joint':
            for a in ARMS:
                matches=[Path(k).parent for k in sel.get('source_receipts',{}) if k.endswith('/joint-'+a+'/result.json')]
                path=matches[0] if len(matches)==1 else Path(z['recovery_path'])/'joint'/('joint-'+a)
                saved[a]=read(path/'result.json');protocol=read(path/'protocol.json')
            families=[NewFamily(d['scan'],t,d['model'],phase_step=protocol['phase_step_s'],allow_uncalibrated_label=True)
                      for t in protocol['targets']]
        else:raise ValueError('Unsupported selected kind '+sel['kind'])
    if gap:
        if sel:raise ValueError('Gap selected over separately recovered family requires explicit composition')
        from algo05_gap_stage import gap_context
        from native_predictive_branch import validated_native_source
        path=Path(gap['path']);protocol=read(path/'protocol.json')
        for r in protocol['annotation_receipts']:
            folder=Path(r['path']);d,_=gap_context(d,inv,validated_native_source(folder),read(folder/'result.json')['track_id'])
        saved=read(path/'target_0.json')['arms'];entries+=protocol['targets']
        conditional=[t['candidate_index'] for t in protocol['targets']]
    d['entries']=entries
    def factory(arm,reference):
        kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
        p=make_event_problem(d['scan'],d['node'],d['keep'],arm,reference,d['powers'],d['means'],d['model'],[],**kw)
        attach_event_predictive(p,entries,d['powers'])
        if conditional:
            from conditional_satellite_refresh import attach_conditional_satellite_refresh
            attach_conditional_satellite_refresh(p,entries,d['powers'],conditional)
        cached(p);return p
    checks={};problems={}
    for a in ARMS:
        row=saved.get(a);oldp,oldx=d['problems'][a]
        p=factory(a,np.asarray(row['phase_reference'])) if row else oldp
        x=np.asarray(z['baseline_arms'][a]['endpoint_east_north_km'])
        expected=row.get('incumbent_objective',row['negative_twice_elbo']) if row else z['baseline_arms'][a]['negative_twice_elbo']
        delta=float(p.calculate(x)['negative_twice_elbo']-expected)
        if abs(delta)>1e-4:raise ValueError(f'{a} objective replay mismatch {delta}')
        predictive_score=0.
        if len(families)==1:predictive_score=families[0].evaluate(p,x,d['powers'],entries)
        elif len(families)==2:
            from probe_joint_predictive_families import joint_inputs
            from leo.analysis.research.joint_predictive_families import two_family_phase_evidence
            predictive_score=two_family_phase_evidence(*joint_inputs(families,p,x,d['powers'],entries))['negative_twice_log_density']
        full_delta=float(p.calculate(x)['negative_twice_elbo']+predictive_score-z['baseline_arms'][a]['negative_twice_elbo'])
        if abs(full_delta)>1e-4:raise ValueError(f'{a} full selected likelihood replay mismatch {full_delta}')
        from inactive_graph_fragment import original_graph_view
        _,_,ids,owners=memberships(original_graph_view(p,protocol.get('original_graph_count',len(p.scan.index))),x,entries)
        for f in families:
            for e in f.entries:
                if set(e['observation_ids'])&set(owners):raise ValueError('Duplicate incumbent addition')
                owners.update({o:e['norad'] for o in e['observation_ids']})
        if any(owners.get(o)!=n for o,n in z['baseline_owners'][a].items()):
            expected_owners=z['baseline_owners'][a]
            raise ValueError(f'{a} incumbent ownership replay mismatch: replay={len(owners)}, saved={len(expected_owners)}, missing={len(set(expected_owners)-set(owners))}, extra={len(set(owners)-set(expected_owners))}, changed={[(o,owners.get(o),n) for o,n in expected_owners.items() if owners.get(o)!=n][:3]}')
        checks[a]=dict(incumbent_core_objective_difference=delta,full_selected_likelihood_difference=full_delta,associated_points=len(z['baseline_owners'][a]),
                       incidental_unpublished_extensions_not_adopted=len(set(owners)-set(z['baseline_owners'][a])),
                       selected_kind=sel['kind'] if sel else ('gap_conditional' if gap else 'baseline'))
        problems[a]=(p,x)
    d.update(problems=problems,factory=factory,families=families,replay_checks=checks)
    return d


def configure(root, policy):
    global ROOT, POLICIES
    ROOT = Path(root).resolve()
    POLICIES = {policy: POLICIES[policy]}
