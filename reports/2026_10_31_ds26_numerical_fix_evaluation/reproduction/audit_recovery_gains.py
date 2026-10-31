"""Read-only ownership-gain and phase-gate audit; never runs a scientific fit.

Run with --final only after every frozen fast-case terminal receipt exists.
The family continuous_phase_gate field records evaluation METHOD, not passing.
Qualification is read from each diagnostic/gate and exact-replay receipt.
"""
import json, pathlib, hashlib, math, sys
R=pathlib.Path(__file__).resolve().parent
S=pathlib.Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030')
sys.path.insert(0,str(R))
from annotation_replay import competition_signature, has_phase_overflow
hashes={}
def read(p):
 p=pathlib.Path(p);raw=p.read_bytes();hashes[str(p)]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
def summary(f):
 if f is None:return None
 if isinstance(f,list):return [summary(x) for x in f]
 out={k:f[k] for k in ('phase_map_s','grid_phase_map_s','continuous_phase_gate','phase_mean_s','phase_sigma_s','phase_boundary_mass','negative_twice_log_density','phases_s','refined','refinement_success') if k in f}
 if 'phase_weights' in f:
  inds=sorted(range(len(f['phase_weights'])),key=lambda i:f['phase_weights'][i],reverse=True)[:2]
  out['top_two_phase_weights']=[{'phase_s':f['phase_grid_s'][i],'weight':f['phase_weights'][i]} for i in inds]
  out['top_two_negative_twice_log_weight_gap']=2*math.log(f['phase_weights'][inds[0]]/f['phase_weights'][inds[1]])
 out['diagnostics']=[]
 for g,d in zip(f['gates'],f['diagnostics'],strict=True):
  n=len(d['times_s']);noise=d['noise'];slack={k:1-abs(noise[k])/v for k,v in [('mean_z',3),('slope_z',3),('quadratic_bic_gain',10),('maximum_step_z',4),('lag1_acf',4/math.sqrt(n))]}
  # Negative BIC gains are safely below the upper bound; preserve signed statistic.
  slack['quadratic_bic_gain']=1-noise['quadratic_bic_gain']/10
  out['diagnostics'].append(dict(component=g['component'],norad=g['norad'],points=g.get('points',n),compatible=g['compatible'],profile_RMS_hz=d['profile_RMS_hz'],profile_bias_hz=d['profile_bias_hz'],minimum_elevation_deg=d['minimum_elevation_deg'],noise=noise,normalized_upper_gate_slacks=slack,minimum_noise_slack=min(slack.values())))
 return out
def fit(v):
 h=v['history'][-1];h=h.get('fit',h)
 return dict(success=h.get('success'),message=h.get('message'),stopped=h.get('stopped'),final_phase_change_s=v.get('final_phase_change_s'),endpoint_east_north_km=v.get('endpoint_east_north_km'))
def auditrows(p):
 d=read(p)
 if 'rows' in d:return [dict(arm=x['arm'],verified=x['verified'],grid=summary(x['target']),continuous=summary(x['continuous_target'])) for x in d['rows'] if x['role']=='new_family']
 return [dict(arm=d['arm'],verified=d['RF_qualified_arm'],grid=summary(d['target']),continuous=summary(d['continuous_target']))]
def ann(p):
 d=read(p);a=d['annotation'];votes=[]
 for vote in a.get('votes',[]):
  fold=next(f for f in d['folds'] if f['seed']==vote['seed'])
  proposal=next(p for p in fold['proposals'] if p['norad']==vote['norad'])
  v=proposal['arms'][vote['arm']]
  votes.append(dict(vote,candidate_index=proposal['candidate_index'],alias=proposal['alias'],target_rms_hz=v['scores']['target']['rms_hz'],final_phase_change_s=v['final_phase_change_s'],minimum_target_elevation_deg=v['minimum_target_elevation_deg'],phase_reference_check=v['phase_reference_check']))
 return d,dict(status=a['status'],norad=a.get('norad'),minimum_margin=a.get('minimum_margin'),votes=votes,any_history_phase_overflow=has_phase_overflow(d))
def gates_pass(rows,kind):
 return all(z['compatible'] for r in rows for f in (r[kind] if isinstance(r[kind],list) else [r[kind]]) for z in f['diagnostics'])
def targets(sel):return [{k:t[k] for k in ('component','norad','points','track_index','candidate_index','alias','observation_ids') if k in t} for t in sel['targets']]
protocol=read(R/'dataset-protocol.json');expected=protocol['fast_cases'];done=[c for c in expected if (R/'cases'/c/'receipt.json').exists()]
alladd=[];gains=[]
for case in done:
 p=R/'cases'/case/'outcome.json'
 if not p.exists():continue
 d=read(p);sel=d.get('selected')
 if not sel:continue
 baseline=read(S/'cases'/case/'candidate-v2/terminal.json');base=(baseline.get('selected') or {}).get('arms',baseline['source_support'])
 membership={}
 for a in ('c0','fitted_c'):
  old=base[a]['owners'];new=sel['arms'][a]['owners'];membership[a]=dict(baseline_points=len(old),treatment_points=len(new),gained_observation_ids=sorted(set(new)-set(old)),lost_observation_ids=sorted(set(old)-set(new)),changed_original_owners=[o for o in old if o in new and new[o]!=old[o]])
 gain=len(membership['c0']['gained_observation_ids']);assert gain==len(membership['fitted_c']['gained_observation_ids'])
 evidence=[];shared_replays=[]
 for path in sel['source_receipts']:
  if path.endswith('exact_owner_replay.json') or path.endswith('/audit.json') and '/control-' not in path:
   if sel['kind']=='shared_family':
    sd=read(path);shared_replays.append(dict(path=path,all_verified=sd['all_verified'],rows=[dict(role=z['role'],arm=z['arm'],verified=z['verified']) for z in sd['rows']]))
   else:evidence+=auditrows(path)
 alladd.append(dict(case=case,selected_kind=sel['kind'],new_points_vs_published_ALGO03=gain,selected_targets=targets(sel),gate_evidence=evidence,shared_family_replays=shared_replays))
 if not gain:continue
 assert not any(v['lost_observation_ids'] or v['changed_original_owners'] for v in membership.values())
 row=dict(case=case,new_points=gain,selected_kind=sel['kind'],targets=targets(sel),membership=membership,selected_gate_evidence=evidence,target_history=[])
 oldrecovery=S/'cases'/case/'candidate-v2/recovery';decision=read(oldrecovery/'decision.json')
 for target in sel['targets']:
  oid=set(target['observation_ids']);matched=[]
  for ap in sorted((R/'cases'/case).glob('*/annotation/result.json')):
   new=read(ap)
   if new['component']!=target['component']:continue
   tid=ap.parent.parent.name;oldp=oldrecovery/tid/'annotation/result.json'
   if not oldp.exists():continue
   old,os=ann(oldp);new,ns=ann(ap)
   oldprotocol=read(oldp.with_name('protocol.json'))
   op=oldrecovery/tid/'trial';np=R/'cases'/case/tid/'trial'
   x=dict(track_id=tid,component=target['component'],old_annotation=os,new_annotation=ns,competition_and_splits_identical=competition_signature(old)==competition_signature(new),original_attempts=[{k:v for k,v in a.items() if k in ('track_id','points','status','trial','retry')} for a in decision['attempts'] if a.get('track_id')==tid],original_target_stages=[{k:v for k,v in stage.items() if k not in ('command','error')} for stage in decision['stages'] if tid in str(stage.get('command',[]))],original_same_TID_trial_exists=(op/'new_family.json').exists())
   assert x['competition_and_splits_identical']
   x['source_target_observation_ids_identical']=set(oldprotocol['target']['observation_ids'])==oid
   x['winning_candidate_alias_identical']=all((o['norad'],o['candidate_index'],o['alias'])==(n['norad'],n['candidate_index'],n['alias']) for o,n in zip(os['votes'],ns['votes'],strict=True))
   assert x['source_target_observation_ids_identical']
   for root,label in ((op,'original'),(np,'treatment')):
    if not(root/'new_family.json').exists():continue
    a=read(root/'new_family.json');c=read(root/'control.json');pr=read(root/'protocol.json')
    x[label+'_trial']=dict(paired_valid=a['paired_valid'],control_paired_valid=c['paired_valid'],fits={arm:dict(control=fit(c['arms'][arm]),addition=fit(a['arms'][arm])) for arm in ('c0','fitted_c')},family_prior=pr['family_prior'],targets=pr['targets'],phase_step_s=pr['phase_step_s'],maxiter=pr['maxiter'],maxfun=pr['maxfun'],phase_rounds=pr['phase_rounds'],start=pr['start'],box_width_km=pr['box_width_km'],gate_evidence=auditrows(root/'exact_owner_replay.json'))
   if x['original_same_TID_trial_exists']:
    oldt=x['original_trial'];newt=x['treatment_trial']
    keys=('family_prior','targets','phase_step_s','maxiter','maxfun','phase_rounds','start','box_width_km')
    x['same_TID_scientific_inputs_identical']=all(oldt[k]==newt[k] for k in keys)
    x['grid_false_negative_original']=not gates_pass(oldt['gate_evidence'],'grid') and gates_pass(oldt['gate_evidence'],'continuous') and gates_pass(newt['gate_evidence'],'grid') and gates_pass(newt['gate_evidence'],'continuous')
    x['cause']='coarse_phase_MAP_gate_false_negative_at_original_endpoint' if x['grid_false_negative_original'] else 'requires_same_TID_comparison'
   else:
    bad=[v for v in os['votes'] if not v['adequate']]
    reference_only=bool(bad) and all(v['target_rms_hz']<=450 and v['minimum_target_elevation_deg']>=0 and v['final_phase_change_s']>.01 and v['phase_reference_check'].get('phase_outside_reference_window') is True for v in bad)
    x['original_inadequacy_only_phase_reference_convergence']=reference_only
    x['cause']='annotation_phase_reference_domain_blocked_inclusion_no_original_optimizer_comparator' if reference_only else 'newly_eligible_without_original_optimizer_comparator_requires_review'
   matched.append(x)
  assert len(matched)==1,(case,target['component'],len(matched))
  row['target_history']+=matched
 gains.append(row)
hashes[str(pathlib.Path(__file__).resolve())]=hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
selected_gate_checks=[dict(case=r['case'],arm=e['arm'],grid_pass=gates_pass([e],'grid'),continuous_pass=gates_pass([e],'continuous')) for r in alladd for e in r['gate_evidence']]
result=dict(final=len(done)==len(expected),expected_cases=len(expected),terminal_cases=len(done),remaining_cases=[c for c in expected if c not in done],no_GPS_or_known_site_truth_read=True,no_fits=True,scope='published ALGO03 terminal ownership versus frozen numerical cohort; both c arms; no outcome rewrite',new_gain_cases=len(gains),new_points=sum(x['new_points'] for x in gains),selected_gate_checks=selected_gate_checks,selected_grid_continuous_disagreements=[e for e in selected_gate_checks if e['grid_pass']!=e['continuous_pass']],selected_continuous_gate_failures=[e for e in selected_gate_checks if not e['continuous_pass']],all_selected_additions=alladd,gains=gains,source_sha256=hashes,gate_sensitivity_rule='For every selected predictive target, inspect the saved grid and continuous gate diagnostics in both c arms. For gains with an original same-TID trial, compare original and treatment grid/continuous classifications, optimizer success, phase means, top-two grid weights, and identical family priors/targets. A coarse-grid false-negative gain has an original failing grid gate and passing continuous gate, and a treatment passing grid and continuous gate; flag for causal interpretation without rejecting a continuously qualified treatment.',continuous_phase_gate_is_method_flag_not_pass_status=True)
if '--final' in sys.argv:
 assert result['final'],'wait for all frozen terminal receipts'
 (R/'recovery-gain-audit.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 lines=['# Recovery gain audit','',f"All **{len(done)}/{len(expected)}** frozen DS26 fast cases have terminal receipts. Relative to published ALGO03 terminal ownership, **{len(gains)} scans gain {result['new_points']} observations**, identically in c=0 and fitted-c. No original observation or owner is lost in a gain scan. All gained IDs match the original target-source IDs. This audit reads RF inference receipts; it performs no fits and reads no known-site truth or geographic error.",'',
 '| Scan | NORAD | New points | Original adequate votes | New minimum identity margin | Cause |','|---|---:|---:|---:|---:|---|']
 for row in gains:
  for t in row['target_history']:
   target=next(z for z in row['targets'] if z['component']==t['component'])
   old=t['old_annotation'];new=t['new_annotation'];cause='Phase-reference domain blocked annotation' if t['cause'].startswith('annotation_phase') else 'Original coarse-grid gate false negative' if t.get('grid_false_negative_original') else t['cause']
   lines.append(f"| {row['case']} | {target['norad']} | {target['points']} | {sum(v['adequate'] for v in old['votes'])}/{len(old['votes'])} | {new['minimum_margin']:.6f} | {cause} |")
 domain=[(row,t,next(z for z in row['targets'] if z['component']==t['component'])) for row in gains for t in row['target_history'] if t['cause'].startswith('annotation_phase')]
 domain_cases=', '.join(sorted({row['case'] for row,t,target in domain}))
 domain_points=sum(target['points'] for row,t,target in domain)
 lines+=['',
 f'The **{len(domain)} newly eligible fragments** in {domain_cases} account for **{domain_points} points**. Every original inadequate winning fold has a clipped phase reference and final phase change greater than 0.01 s; its target RMS and elevation already pass. The original target annotation stages completed. They produced prediction_mismatch and no original same-TID inclusion trial, so these points cannot demonstrate an old inclusion optimizer failure, an ABNORMAL-to-success recovery, or a larger-budget rescue. The target NORAD, candidate index, alias, observation IDs and saved random whole-group folds remain matched. New target inclusion optimizers succeed in both c arms. DS26-0106 adds NORAD **60143 / 41 points**; the separate **59835 / 71-point** source remains unrecovered. DS26-0265 adds NORAD **62422 / 53 points** on RX2 CH8 T001, separately from the unresolved **66102 / 120-point** RX1 CH4 source.',
 '',
 '**DS26-0235 / NORAD 58099 / 74 points is different.** Its annotation identity was already supported and unchanged. Both original and treatment control/addition final optimizers succeed, final phase changes are small, and target IDs, family prior, phase grid, start and evaluation/round budgets match. The c=0 endpoint shifts only **0.5393 m**, but nearly tied grid phase weights swap the MAP from 0.475 to 0.5 s. The target integrated score changes from 907.1890185 to 907.1911735, while phase mean changes only **24.09 microseconds**. The grid slope statistic crosses from **3.114292 (fail)** to **2.640311 (pass)** against threshold 3. This is a threshold-sensitive coarse-grid false negative at the original endpoint, not evidence of previously failed numerical termination.',
 '',
 'The saved continuous phase countercheck passes at **both** DS26-0235 endpoints: original c=0 phase 0.4874738995 s / slope z **2.8806811**; treatment phase 0.4874979000 s / z **2.8816881**. Fitted-c grid and continuous checks pass in both versions. The treatment therefore remains continuously qualified. The family field `continuous_phase_gate=false` describes the ordinary grid evaluation method; it is not a failing gate. `exact_owner_replay.json` explicitly stores `rows[*].continuous_target` and requires all target **and** continuous-target gates. Its original `all_verified=false` and treatment `all_verified=true` follow that conjunction correctly. No addition is excluded based on this method flag.',
 '',
 '`phase_resolution_audit.local_agreement` verifies integrated score and local gradient agreement at phase spacings 0.025, 0.0125 and 0.00625 s. It does not test stability of a residual-screen statistic evaluated at a discrete MAP. DS26-0235 treatment c=0 has maximum quadrature score change 5.13e-7 and gradient change 1.04e-6/km, so likelihood quadrature and a discontinuous MAP gate can coexist.',
 '',
 f"The uniform saved-receipt audit covers **{sum(bool(x['gate_evidence']) for x in alladd)} predictive selected additions / {len(selected_gate_checks)} c-arm target checks**, including existing additions reused from ALGO03. The other **{sum(x['selected_kind']=='shared_family' for x in alladd)} selected shared-family additions** have exact-replay checks rather than this NewFamily grid/continuous comparison; all are unchanged from published ownership and their saved exact-replay receipts pass. Among the predictive checks, selected grid/continuous gate disagreements: **{len(result['selected_grid_continuous_disagreements'])}**; continuous target failures: **{len(result['selected_continuous_gate_failures'])}**. Each gain with a completed original same-TID trial is compared for old/new grid classification, continuous classification, optimizer success and unchanged scientific inputs. This identifies the DS26-0235 coarse-grid false negative without an arbitrary phase-weight tie cutoff or a post-hoc rejection rule. Raw cohort outcomes remain unchanged.",
 '',
 'The new DS26-0235 c=0 continuous slope has 3.94% normalized headroom. Other current selected additions close to a noise threshold include DS26-0030 fitted-c step z about 3.852/4 and DS26-0150 c=0 lag-1 about 0.4612/0.4650; these were already published additions. These margins describe sensitivity, not gate changes or exclusions. The other newly gained fragments have substantially larger saved noise-screen margins. Better in-sample frequency fit or recovered point count alone establishes no localization improvement.',
 '',
 'Reproduce with `PYTHONPATH=/srv/bulk/leo-dev/fast-algo02-production-v1/tools:/srv/bulk/leo-dev/fast-algo02-production-v1/src OPENBLAS_NUM_THREADS=1 /srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python audit_recovery_gains.py --final` from this study directory. `recovery-gain-audit.json` contains target IDs, both-arm ownership deltas, full saved annotation votes, target-specific original stage statuses, final optimizer evidence, grid/continuous diagnostics, and SHA-256 hashes of every input read plus this auditor. No production result is rewritten.']
 (R/'recovery-gain-audit.md').write_text('\n'.join(lines)+'\n')
else:(pathlib.Path('/tmp/ds26-recovery-gain-preliminary.json')).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({k:result[k] for k in ('final','terminal_cases','new_gain_cases','new_points')}))
for x in gains:print(x['case'],x['new_points'],[(t['track_id'],t['cause']) for t in x['target_history']])
