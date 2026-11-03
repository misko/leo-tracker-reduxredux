"""Frozen cohort and exact incumbent reconstruction for bounded recovery trials."""
from pathlib import Path
import json, gzip, hashlib, copy, os
import numpy as np

ROOT=Path(__file__).resolve().parent
RELEASE=Path('/srv/bulk/leo-dev/fast-algo02-production-v1')
INVENTORY=RELEASE/'reports/2026_10_31_algo05_promotion/residuals'
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

def prepare():
    rows=json.load(gzip.open(INVENTORY/'all-residual-fragments.json.gz','rt'))
    selected={z['case']:z['selected'] for z in read(INVENTORY/'selections.json')}
    idx={z['case']:z for z in read('/srv/bulk/leo/research/ds27-algo04-20261031/analysis-index.json')['cases']}
    cohort=[]
    for case in sorted({r['case'] for r in rows}):
        local=[r for r in rows if r['case']==case]
        inv=read(local[0]['inventory_path']);native=Path(inv['job']['root'])/inv['job']['case']
        if case.startswith('DS26'):
            b=read('/srv/bulk/leo/research/ds26-confident-recovery-20261031/baselines/'+case+'.json')
            proof=read(b['source']);arms=b['arms'];owners=b['owners']
            baseline_source=b['source']
        else:
            from importlib.util import spec_from_file_location,module_from_spec
            spec=spec_from_file_location('rank',RELEASE/'reports/2026_10_31_algo05_promotion/reproduction/rank_native_residuals.py')
            rank=module_from_spec(spec);spec.loader.exec_module(rank)
            term=read(idx[case]['terminal_path']);proof=term['candidate'] if term['decision']=='ALGO04_additive' else term['incumbent']
            arms=proof['selected']['arms'] if proof.get('selected') else proof['baseline']['arms']
            owners={a:rank.published_owners(term,a) for a in ARMS};baseline_source=idx[case]['terminal_path']
        if selected[case]:
            arms=read(Path(selected[case]['path'])/'target_0.json')['arms']
            owners={a:arms[a]['proposed_owners'] for a in ARMS}
        # Geometry-only selection, fixed before any candidate fit or GPS scoring.
        eligible=[r for r in local if r['points']>=20 and r['duration_s']>=15 and
                  not(set(r['observation_ids']) & (set(owners['c0'])|set(owners['fitted_c'])))]
        eligible.sort(key=lambda r:(-r['duration_s'],-r['points'],r['fragment_id']))
        z=dict(case=case,inventory_path=local[0]['inventory_path'],recovery_path=local[0]['recovery_path'],
               native_path=str(native),scan_receipt=read(native/'receipt.json'),selected=proof.get('selected'),
               gap_selected=selected[case],baseline_arms=arms,baseline_owners=owners,
               baseline_source=baseline_source,baseline_sha256=digest(baseline_source),
               targets=eligible[:3],eligible_targets=len(eligible))
        write(ROOT/'inputs'/(case+'.json'),z)
        cohort.append(dict(case=case,targets=len(z['targets']),eligible_targets=len(eligible),
                           cutoff_utc_ns=z['scan_receipt']['cutoff_utc_ns'],
                           origin_utc_ns=z['scan_receipt']['origin_utc_ns']))
    write(ROOT/'protocol.json',dict(cohort=cohort,unavailable=read(INVENTORY/'sources.json')['unavailable'],
          variants=POLICIES,maximum_targets_per_scan=3,minimum_points=20,minimum_span_s=15,
          target_ranking='duration, points, stable fragment identity; no position error input',
          search='complete causal catalogue at published RF endpoint; bounded shortlist, no NORAD whitelist',
          calibration='preserve selected current ALGO05 incumbent',
          validation_seeds=[20261031,94721,4081],validation='random 12-second target blocks, 2-second guards; conditional on incumbent and graph',
          local_position_budget=dict(phase_rounds=3,evaluations_per_round=100,box_width_km=25),
          maximum_joint_new_families=2,maximum_position_proposals_per_scan_policy=1,
          phase_sigma_search_s=5,constant_sigma_search_hz=300,rate_sigma_search_hz_s=.5,
          identity_margin_minimum=10,noise_search_hz=150,causal_only=True,GPS_inference=False,
          published_inference_reused=True,scope='bounded conditional recovery, not cold-start full RF pipeline rerun'))
    print('Prepared',len(cohort),'scans',sum(z['targets'] for z in cohort),'targets',flush=True)

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

if __name__=='__main__':prepare()
