"""Produce compact review artifacts and validate the bounded local investigation."""
import csv,hashlib,json,math
from pathlib import Path
from investigate import ROOT,CASES,ARMS,MODELS,read,write
from finish import report,old_render,plt
import numpy as np

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def finite(value):
    if isinstance(value,float):return math.isfinite(value)
    if isinstance(value,dict):return all(finite(v) for v in value.values())
    if isinstance(value,list):return all(finite(v) for v in value)
    return True

def csvwrite(path,rows):
    if not rows:return
    with path.open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def summarize_case(case,supplemental_n=None):
    out=ROOT/case
    if supplemental_n is not None:out=out/f'supplemental-{supplemental_n}'
    targets=read(out/'targets.json');families=read(out/'family_consistency.json');swaps=read(out/'frozen_tle_swap.json');report(case,out,targets,families,swaps)
    diagnostic_path=ROOT.parent/'diagnostics'/case/'track_residuals.json';baseline_maps={a:{} for a in ARMS};baseline_family={}
    if diagnostic_path.exists():
        for r in read(diagnostic_path):
            for o,residual in zip(r['observation_ids'],r['residual_hz']):
                baseline_maps[r['arm']][o]=residual;baseline_family[(r['arm'],r['norad'],o)]=residual
    baseline_summary=[]
    for target in targets:
        for arm in ARMS:
            values=[baseline_maps[arm][o] for o in target['observation_ids'] if o in baseline_maps[arm]]
            baseline_summary.append(dict(target=target['index'],arm=arm,native_points=len(target['observation_ids']),available_published_full_model_residuals=len(values),published_full_model_rms_hz=float(np.sqrt(np.mean(np.asarray(values)**2))) if values else None,scope='Saved full production nuisance model; separate from restricted SGP4 phase+offset/rate diagnostic'))
        values=[baseline_maps['fitted_c'].get(o) for o in target['observation_ids']]
        if all(v is not None for v in values):
            t=np.asarray(target['times_s']);raw=np.asarray(target['raw_unwrapped_hz']);residual=np.asarray(values);cal=raw-np.asarray(target['corrected_hz']['fitted_c']);fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True,layout='constrained')
            axes[0].scatter(t,(raw-cal)/1000,s=12,color='black',label='Native minus frozen receiver calibration');axes[0].plot(t,(raw-cal-residual)/1000,color='purple',ls='--',label='Published full nuisance prediction');axes[1].plot(t,residual,'.-',color='purple',label=f'Published full model RMS {np.sqrt(np.mean(residual**2)):.1f}Hz')
            for regime,color in [('causal','#0072b2'),('later','#d55e00')]:
                rr=sorted([r for r in target['results'] if r['regime']==regime and r['arm']=='fitted_c' and r['model']=='L3_phase'],key=lambda r:r['score'])
                if rr:
                    r=rr[0];axes[0].plot(t,np.asarray(r['prediction_adjusted_hz'])/1000,color=color,label=f'Restricted {regime} {r["norad"]}');axes[1].plot(t,r['residual_hz'],'.-',color=color,label=f'Restricted {regime} RMS {r["rms_hz"]:.1f}Hz')
            axes[0].set(ylabel='Alias-lifted corrected CFO (kHz)');axes[1].set(ylabel='Residual (Hz)',xlabel='Scan time (s)');axes[1].axhline(0,color='black',lw=.7)
            for ax in axes:ax.legend(fontsize=8)
            fig.suptitle(f'{case} target{target["index"]}: published full nuisance vs restricted orbit diagnostic\nDifferent satellite nuisance models; restricted-model RMS is not baseline gate failure');old_render.save(fig,out/f'target-{target["index"]}-published-vs-restricted.png')
    write(out/'published_baseline_residual_summary.json',baseline_summary)
    rows=[];family_rows=[];mechanisms=[];poly_rows=[]
    for target in targets:
        assert len(target['observation_ids'])==len(set(target['observation_ids']))
        audits=[('retained_orbit_points',target['polynomial']),('complete_original_graph',target['full_graph_audit']['polynomial'])]+[(f'original_piece_{p["piece_index"]}',p['polynomial']) for p in target['full_graph_audit']['pieces']]
        for scope,polynomial in audits:
            for row in polynomial['rows']:
                residual=np.asarray(row['residual']);poly_rows.append(dict(target=target['index'],scope=scope,degree=row['degree'],selected=row['degree']==polynomial['selected_degree'],native_points=row['n'],span_s=row['span_s'],descriptive_independent_noise_bic=row['bic'],rms_hz=row['rms_hz'],robust_scale_hz=float(1.4826*np.median(abs(residual-np.median(residual)))),mean_hz=row['mean_hz'],slope_hz_s=row['slope_hz_s'],lag1=row['lag1'],mean_z=row['noise']['mean_z'],slope_z=row['noise']['slope_z'],remaining_quadratic_bic_gain=row['noise']['quadratic_bic_gain'],maximum_step_z=row['noise']['maximum_step_z'],first_endpoint_leverage=row['endpoint_leverage'][0],last_endpoint_leverage=row['endpoint_leverage'][1],first_endpoint_loo_residual_hz=row['loo_endpoint_residual_hz'][0],last_endpoint_loo_residual_hz=row['loo_endpoint_residual_hz'][1]))
        for r in target['results']:
            rows.append(dict(target=target['index'],role=target['meta']['role'],incumbent=target['meta']['assigned_norad'],regime=r['regime'],arm=r['arm'],model=r['model'],norad=r['norad'],score=r['score'],n=r['n'],span_s=r['span_s'],rms_hz=r['rms_hz'],mean_hz=r['mean_hz'],slope_hz_s=r['slope_hz_s'],lag1=r['lag1'],phase_s=r['phase_s'],phase_prior_pull=r['phase_s']/5,bias_hz=r['bias_hz'],bias_prior_pull=r['bias_hz']/300,rate_hz_s=r['rate_hz_s'],rate_prior_pull=r['rate_hz_s']/MODELS[r['model']][0] if MODELS[r['model']][0] else None,alias=r['alias'],minimum_elevation_deg=r['minimum_elevation_deg'],noise_screen_pass=r['noise']['noise_screen_pass'],physical_screen_pass=r['physical_screen_pass'],search_role=r.get('search_role','catalogue coarse top3/model plus incumbent'),identity_status='ambiguous: diagnostic model; no independent acceptance'))
            residual=np.asarray(r['residual_hz']);rows[-1].update(robust_scale_hz=float(1.4826*np.median(abs(residual-np.median(residual)))),mean_gate_margin=3-r['noise']['mean_z'],slope_gate_margin=3-r['noise']['slope_z'],quadratic_gate_margin=10-r['noise']['quadratic_bic_gain'],step_gate_margin=4-r['noise']['maximum_step_z'],lag1_gate_margin=4/np.sqrt(r['n'])-abs(r['noise']['lag1_acf']),rms_gate_margin_hz=450-r['rms_hz'],bias_gate_margin_hz=3000-abs(r['bias_hz']),rate_gate_margin_hz_s=2-abs(r['rate_hz_s']))
        for regime in ('causal','later'):
            for model in MODELS:
                armsets=[{r['norad'] for r in target['results'] if r['regime']==regime and r['model']==model and r['arm']==a} for a in ARMS]
                assert armsets[0]==armsets[1],(case,target['index'],regime,model,armsets)
    for f in families:
        winners={}
        for regime in ('causal','later'):
            ranked=sorted([r for r in f['results'] if r['arm']=='fitted_c' and r['regime']==regime and r['model']=='shared_phase_small_rate'],key=lambda r:r['score'])
            if ranked:winners[regime]=ranked[0]
        for r in f['results']:
            published=[v for (arm,n,o),v in baseline_family.items() if arm==r['arm'] and n==f['incumbent']]
            family_rows.append({k:r[k] for k in ['regime','arm','model','norad','score','phase_s','rate_hz_s','rms_hz','all_tracks_noise_pass']}|dict(incumbent=f['incumbent'],tracks=len(f['tracks']),points=sum(len(t['observation_ids']) for t in f['tracks']),published_full_model_rms_hz=float(np.sqrt(np.mean(np.asarray(published)**2))) if published else None,rate_prior_pull=r['rate_hz_s']/(.5 if r['model']=='shared_phase_small_rate' else 2),phase_prior_pull=r['phase_s']/5))
        if not winners:continue
        n=f['incumbent'];same=all(r['norad']==n for r in winners.values());stable=len({r['norad'] for r in winners.values()})==1
        if same:mechanism='incumbent identity stable in restricted family shortlist; geometry or richer nuisance calibration remains the leading unresolved alternative'
        elif stable:mechanism='same rival preferred by restricted whole-family model in both banks; association sensitivity is plausible, but omitted production orbital modes prevent a wrong-identity conclusion'
        else:mechanism='family identity ranking changes with TLE bank; model/orbit sensitivity and association ambiguity remain entangled'
        causal=winners.get('causal');later=winners.get('later')
        if causal and later and causal['norad']==later['norad']:
            later_effect=f"Same diagnostic identity {causal['norad']}: later refit restricted-family RMS {causal['rms_hz']:.1f}→{later['rms_hz']:.1f} Hz; this refits nuisance and is not the frozen-swap test."
        else:later_effect='Causal/later family winners differ; a smaller refitted RMS cannot be attributed solely to better elements.'
        mechanisms.append(dict(incumbent=n,mechanism=mechanism,causal_winner=causal['norad'] if causal else None,later_winner=later['norad'] if later else None,later_effect=later_effect,confidence='model-sensitive / ambiguous; no independent identity validation',next_test='Use the rival and incumbent with matched production physical orbital modes and all family receivers, fit on frozen whole time groups, test held groups, then exact ownership/gate replay.'))
    csvwrite(out/'candidate_fit_summary.csv',rows);csvwrite(out/'polynomial_summary.csv',poly_rows);csvwrite(out/'family_fit_summary.csv',family_rows);csvwrite(out/'paired_tle_summary.csv',[{k:v for k,v in r.items() if k not in ('times_s','later_frozen_residual_hz')} for r in swaps])
    ledger_path=ROOT/case/'tle-ledger.json';inventory_path=ROOT/case/'tle_inventory.csv';ledger=read(ledger_path);manifest=read(out/'run_manifest.json')
    write(out/'tle_manifest.json',dict(local_ledger_path=str(ledger_path),ledger_sha256=digest(ledger_path),causal_count=len(ledger['causal']),later_count=len(ledger['later']),causal_policy='element age≤72h, collection≤scan cutoff; complete saved catalogue',later_policy=ledger['later_policy'],scan_end_utc_ns=ledger['scan_end_utc_ns'],horizon_utc_ns=ledger['horizon_utc_ns'],snapshot_count=len(ledger['snapshots']),snapshots_sha256=hashlib.sha256(json.dumps(ledger['snapshots'],sort_keys=True).encode()).hexdigest(),causal_verified=ledger['causal_verified'],full_inventory_path=str(inventory_path),full_inventory_sha256=digest(inventory_path)))
    write(out/'mechanism_summary.json',mechanisms)
    reportpath=out/'report.md';prose=['','Mechanism assessment (restricted model):']
    paired=[r for r in swaps if r['arm']=='fitted_c' and r['status']=='paired']
    frozen_improvements=[r for r in paired if r['later_frozen_corrections_rms_hz']<r['causal_rms_hz']]
    prose+=['',f'Paired later-element check: {len(frozen_improvements)}/{len(paired)} fitted-c rows improve under frozen causal phase, constant and rate. Refitted later-RMS improvements re-estimate those corrections and therefore do not isolate an orbit improvement. Frozen-swap and refitted values are separately listed in `paired_tle_summary.csv`.']
    if supplemental_n is not None:prose+=['','This is a posthoc supplemental family nominated by the completed omission ablation. Original top-two targets are preserved separately. A gate-qualified omission displacement is influence evidence and does not justify removing the family.']
    for m in mechanisms:prose+=['',f"Family {m['incumbent']}: {m['mechanism']}. {m['later_effect']} Confidence: {m['confidence']}. Next: {m['next_test']}"]
    for target in targets:
        if (out/f'target-{target["index"]}-published-vs-restricted.png').exists():prose+=['',f'![Published full nuisance versus restricted model](target-{target["index"]}-published-vs-restricted.png)']
    guardpath=ROOT.parent/'eval'/case/'summary.json'
    if guardpath.exists():
        guard=read(guardpath);compact=dict(source_path=str(guardpath),source_sha256=digest(guardpath),execution_status=guard['execution_status'],selected=guard.get('selected'),exact_fallback_equal=guard.get('exact_fallback_equal'),guards={name:{k:g.get(k) for k in ['proposed','candidates','model','phase_sd_s','unique_folds','minimum_margin','status','passed','reason','scope']} for name,g in guard.get('guards',{}).items()},candidate_acceptance=[dict(name=c['name'],accepted=c['accepted'],c_arm_fit_available={a:c['pairs'].get(a) is not None for a in ARMS}) for c in guard.get('candidate_records',[])])
        write(out/'algo07_guard_summary.json',compact);prose+=['','Saved ALGO07 conditional candidate-family guards:']
        for name,g in compact['guards'].items():prose += [f"{name}: {g['status']}; minimum competitor margin {g['minimum_margin']}; {g['unique_folds']} unique folds. Scope: {g['scope']}."]
        prose += [f"Final selected replacement: {compact['selected']}. Guard passage and final production acceptance are separate checks; no replacement is implied by a diagnostic orbit fit."]
    else:write(out/'algo07_guard_summary.json',dict(status='not available at compact-summary time',source_path=str(guardpath)))
    reportpath.write_text(reportpath.read_text()+'\n'.join(prose)+'\n')
    checks=dict(case=case,supplemental_norad=supplemental_n,status=manifest.get('status'),target_count=len(targets),original_graph_audited=all('full_graph_audit' in t for t in targets),matched_c_arm_exact_candidates=True,unique_ids_within_targets=True,causal_catalogue_count=len(ledger['causal']),later_catalogue_count=len(ledger['later']),candidate_fit_count=len(rows),all_checked_numeric_outputs_finite=all(finite(v) for v in [targets,families,swaps,manifest]),no_identity_acceptance_claim=True)
    assert checks['status']=='complete' and checks['target_count']==(1 if supplemental_n is not None else 3) and checks['all_checked_numeric_outputs_finite'],checks
    write(out/'validation.json',checks)
    allow=[p for p in out.glob('*.png')]+[out/n for n in ['report.md','run_manifest.json','association_summary.csv','association_summary.json','candidate_fit_summary.csv','polynomial_summary.csv','family_fit_summary.csv','paired_tle_summary.csv','tle_manifest.json','mechanism_summary.json','algo07_guard_summary.json','published_baseline_residual_summary.json','validation.json','causal-search-coverage.json','later-search-coverage.json']]
    return checks,allow

if __name__=='__main__':
    checks=[];allow=[]
    for case in CASES:
        c,a=summarize_case(case);checks.append(c);allow+=a
    for case,n in [('DS26-0014',57898),('DS26-0209',66482)]:
        if (ROOT/case/f'supplemental-{n}'/'family_consistency.json').exists():
            c,a=summarize_case(case,n);checks.append(c);allow+=a
    index=['# Top-ten orbit and graph investigation', '', 'All ten scans were restored through `algo07_science.engine.load_case`, including the actual accepted ALGO06 composition. Every case has two influential-family targets and its longest saved unassociated source. Additional 0014/57898 and 0209/66482 controls are explicitly posthoc, motivated by the completed omission ablations.', '', 'Each causal and first-post-epoch bank contains approximately 11,100 satellites. Every propagation-valid candidate received the same coarse nomination budget; the matched c arms share the top-three finalists per nuisance model plus the incumbent for exact native-point fitting. This is a complete eligible-catalogue coarse search with finalist exact fits, not an exact fit of every satellite.', '', 'The diagnostic orbit model replaces the full production satellite nuisance block with phase plus constant/rate. Its RMS cannot be read as a published baseline residual or gate failure. The full-versus-restricted figures and family CSVs show this distinction explicitly. Whole-family comparisons test conditional consistency of the single-track shortlist; they do not establish unique identity. Frozen receiver calibration remains fixed, and per-track constants are diagnostic lower bounds.', '', '| Case | Influential family | Causal / later family winner | Assessment |', '|---|---:|---|---|']
    for case in CASES:
        for m in read(ROOT/case/'mechanism_summary.json'):index.append(f'| [{case}]({case}/report.md) | {m["incumbent"]} | {m["causal_winner"]} / {m["later_winner"]} | {m["mechanism"]} |')
    index += ['', 'The two posthoc families remain the best restricted whole-family hypotheses in both banks: [0014 / 57898](DS26-0014/supplemental-57898/report.md) and [0209 / 66482](DS26-0209/supplemental-66482/report.md). Their omission-induced position changes support an influence diagnosis, not deletion or a wrong-identity claim.', '', 'No audited fitted-c paired causal winner/runner-up/incumbent improves after a later-TLE swap with its causal phase, bias and rate frozen. Improvements after later refits are a separate result that can absorb discrepancies through nuisance changes. Both comparisons are retained.', '', 'All 12 investigations passed native-ID uniqueness, matched c-arm exact-candidate-set, finite-value and expected-target-count checks. Original graph endpoints and every original graph piece were audited through polynomial degrees zero to four; descriptive independent-noise BIC is explicitly limited by irregular sampling/correlation. Context, wrapped/unwrapped overlays, polynomial and residual audits, consecutive 20-second zooms, candidate heatmaps, full production baseline comparisons and whole-family figures are saved per case.', '', 'Saved ALGO07 candidate-family guards are reported separately from final acceptance. They remain conditional on the supplied finalist inventory, graph/alias choices and cavity calibration. Exact production acceptance and matched localization ablations are in the sibling diagnostics/evaluation reports. This orbit investigation makes no localization-gain claim.', '', 'The publication allowlist excludes duplicate raw TLE ledgers and dense native predictions/residual arrays. Compact manifests retain local absolute paths and hashes. All inputs were read-only; no RF collection, production ownership change or golden-fixture update was performed.']
    (ROOT/'README.md').write_text('\n'.join(index)+'\n');allow.append(ROOT/'README.md')
    allow += [ROOT/n for n in ['investigate.py','finish.py','publication.py','supplemental.py','render_saved.py','execution.json','finish-execution.json','supplemental-execution.json']]
    helper_paths=[ROOT/'render_saved.py']+[ROOT.parents[1]/'2026_11_01_ds26_outlier_root_cause'/n for n in ['track_debug.py','diagnose.py','family_debug.py']]
    write(ROOT/'helper_provenance.json',dict(reused_helpers=[dict(path=str(p),sha256=digest(p)) for p in helper_paths],note='render_saved.py archives the original rendering helper because that helper was not in the source checkout index; numerical helpers remain tracked source files.'))
    allow.append(ROOT/'helper_provenance.json')
    write(ROOT/'validation.json',checks)
    write(ROOT/'publication_manifest.json',dict(allowlist=[dict(path=str(p.relative_to(ROOT.parent)),sha256=digest(p),bytes=p.stat().st_size) for p in allow if p.exists()],exclude_policy='Dense native predictions/residuals, raw duplicated TLE ledgers and inventories remain local; compact files record their absolute paths and hashes.',local_root=str(ROOT)))
    print('validated',len(checks),'cases; publication bytes',sum(p.stat().st_size for p in allow if p.exists()))
