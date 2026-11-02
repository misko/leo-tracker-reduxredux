"""Render saved fits, graph audits, paired swaps and family consistency controls."""
import argparse,csv,hashlib,sys
from pathlib import Path
import numpy as np
from investigate import *
import family_debug as old_family
import render_saved as old_render
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def enrich(d,targets):
    for target in targets:
        tr=d['scan'].tracks[target['meta']['track_index']];t=np.asarray(tr['times']);y=np.asarray(tr['values']);pieces=[]
        for k,piece in enumerate(tr['pieces']):
            use=(t>=piece['start_s']-1e-6)&(t<=piece['end_s']+1e-6)
            if sum(use)>=6:pieces.append(dict(piece_index=k,start_s=piece['start_s'],end_s=piece['end_s'],native_n=int(sum(use)),polynomial=legacy.polynomial(t[use],y[use])))
        target['full_graph_audit']=dict(times_s=t,raw_unwrapped_hz=y,observation_ids=tr['observation_ids'],retained_indices=target['meta']['indices'],polynomial=legacy.polynomial(t,y),pieces=pieces,excluded_from_orbit_audit_ids=[o for k,o in enumerate(tr['observation_ids']) if k not in set(target['meta']['indices'])],exclusion_reason='published native owner/retention mask; all original graph points preserved here')

def paired_swaps(d,z,targets,ledger):
    rows=[]
    for target in targets:
        pair_ids=set()
        for arm in ARMS:
            rr=sorted([r for r in target['results'] if r['regime']=='causal' and r['model']=='L3_phase' and r['arm']==arm],key=lambda r:r['score']);pair_ids.update(r['norad'] for r in rr[:2])
        for n in sorted(pair_ids):
            if str(n) not in ledger['later'] or any(r['regime']=='later' and r['model']=='L3_phase' and r['norad']==n for r in target['results']):continue
            nums,bank,failed=legacy.bank_for({str(n):ledger['later'][str(n)]},z['scan_receipt']['origin_utc_ns'])
            exact,coverage=fit_matched(np.asarray(target['times_s']),{a:np.asarray(y) for a,y in target['corrected_hz'].items()},target['rf_hz']/11.5e9,nums,bank,{a:x for a,(p,x) in d['problems'].items()},n,target['phase0'])
            target['results'] += [dict(r,regime='later',search_role='extra paired causal-winner/runner-up refit') for r in exact]
        for arm in ARMS:
            rr=sorted([r for r in target['results'] if r['regime']=='causal' and r['model']=='L3_phase' and r['arm']==arm],key=lambda r:r['score'])
            if not rr:continue
            identities={r['norad'] for r in rr[:2]}
            if target['meta']['assigned_norad'] is not None:identities.add(target['meta']['assigned_norad'])
            for n in sorted(identities):
                causal=next((r for r in rr if r['norad']==n),None);post=ledger['later'].get(str(n))
                if causal is None or post is None:
                    rows.append(dict(target=target['index'],arm=arm,norad=n,status='missing_causal_exact_fit' if causal is None else 'missing_later_element'));continue
                nums,bank,failed=legacy.bank_for({str(n):post},z['scan_receipt']['origin_utc_ns'])
                t=np.array(target['times_s']);f,e=paired_phase_frequency(bank,t,np.zeros(len(t),int),np.array([causal['phase_s']]),*latlon(d['problems'][arm][1]));f=f*target['rf_hz']/11.5e9
                residual=np.asarray(target['corrected_hz'][arm])+causal['alias']*PERIOD-f-causal['bias_hz']-causal['rate_hz_s']*(t-t.mean())
                later=next((r for r in target['results'] if r['regime']=='later' and r['model']=='L3_phase' and r['arm']==arm and r['norad']==n),None)
                rows.append(dict(target=target['index'],arm=arm,norad=n,status='paired',causal_rms_hz=causal['rms_hz'],later_frozen_corrections_rms_hz=float(np.sqrt(np.mean(residual**2))),later_refitted_rms_hz=later['rms_hz'] if later else None,causal_phase_s=causal['phase_s'],later_refitted_phase_s=later['phase_s'] if later else None,times_s=t,later_frozen_residual_hz=residual))
    return rows

def family(d,z,targets,ledger,out):
    result=[];pp=np.linspace(-30,30,301)
    for target in targets:
        n=target['meta']['assigned_norad']
        if n is None:continue
        entries=[];seen=set()
        for i,tr in enumerate(d['scan'].tracks):
            use=np.array([z['baseline_owners']['fitted_c'].get(o)==n and o not in seen for o in tr['observation_ids']])
            if not use.any():continue
            seen.update(o for o,u in zip(tr['observation_ids'],use) if u);entries.append((i,use))
        if not entries:continue
        t=np.concatenate([d['scan'].tracks[i]['times'][use] for i,use in entries]);group=np.concatenate([np.full(sum(use),k) for k,(i,use) in enumerate(entries)]);q=np.concatenate([np.full(sum(use),d['scan'].tracks[i]['rf_hz']/11.5e9) for i,use in entries])
        nominees={n}
        for regime in ('causal','later'):
            rr=sorted([r for r in target['results'] if r['regime']==regime and r['arm']=='fitted_c' and r['model']=='L3_phase'],key=lambda r:r['score']);nominees.update(r['norad'] for r in rr[:3])
        metadata=[dict(index=k,key=d['scan'].tracks[i]['key'],receiver=d['scan'].tracks[i]['receiver'],channel=d['scan'].tracks[i]['channel'],times_s=d['scan'].tracks[i]['times'][use],observation_ids=[o for o,u in zip(d['scan'].tracks[i]['observation_ids'],use) if u]) for k,(i,use) in enumerate(entries)]
        family_rows=[]
        for regime in ('causal','later'):
            available={str(v):ledger[regime][str(v)] for v in nominees if str(v) in ledger[regime]};nums,bank,failed=legacy.bank_for(available,z['scan_receipt']['origin_utc_ns'])
            for arm,(p,x) in d['problems'].items():
                state=p.state(x);values=np.concatenate([(tr['values']-d['scan'].hardware(tr,state['beta'])-tr['rf_hz']/11.5e9*d['scan'].rx_basis[i]@state['smooth'][tr['receiver']-1])[use] for i,use in entries for tr in [d['scan'].tracks[i]]])
                for j,v in enumerate(nums):
                    bb=dict(time_s=bank['time_s'],position_km=np.broadcast_to(bank['position_km'][j],(len(pp),*bank['position_km'][j].shape)),velocity_km_s=np.broadcast_to(bank['velocity_km_s'][j],(len(pp),*bank['velocity_km_s'][j].shape)))
                    f,e=paired_phase_frequency(bb,np.tile(t,len(pp)),np.repeat(np.arange(len(pp)),len(t)),pp,*latlon(x));f=f.reshape(len(pp),-1)*q;e=e.reshape(len(pp),-1)
                    for model,rate in [('shared_phase_small_rate',.5),('shared_phase_rate_discrepancy',2.)]:
                        score,res,coef,aliases=old_family.marginal_curves(values-f,t,q,group,np.ones(len(t),bool),rate);score=np.where(e.min(axis=1)>=0,score+(pp/5)**2,np.inf)
                        if not np.isfinite(score).any():continue
                        k=int(np.argmin(score));per=[]
                        for g in range(len(entries)):
                            use=group==g;per.append(dict(index=g,**legacy.residual_stats(t[use],res[k,use])))
                        family_rows.append(dict(regime=regime,arm=arm,model=model,norad=int(v),score=float(score[k]),phase_s=float(pp[k]),rate_hz_s=float(coef[k,-1]*rate),offsets_hz=coef[k,:-1]*300,aliases=aliases[k],per_track=per,rms_hz=float(np.sqrt(np.mean(res[k]**2))),all_tracks_noise_pass=all(r['noise']['noise_screen_pass'] for r in per),residual_hz=res[k],times_s=t,group=group))
        item=dict(incumbent=n,tracks=metadata,results=family_rows,nominees=sorted(nominees),scope='Conditional family consistency of shortlist nominated on longest track; one shared phase/rate, per-track constant priors (300Hz), fixed saved calibration/position. Per-track offsets are diagnostic lower bounds. No independent validation, shared receiver calibration, or acceptance claim.')
        result.append(item);write(out/f'family-{n}.json',item)
        fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
        for col,regime in enumerate(('causal','later')):
            rows=sorted([r for r in family_rows if r['regime']==regime and r['arm']=='fitted_c' and r['model']=='shared_phase_small_rate'],key=lambda r:r['score'])
            for r in rows[:2]:
                for g in range(len(entries)):
                    use=np.asarray(r['group'])==g;axes[0,col].plot(np.asarray(r['times_s'])[use],np.asarray(r['residual_hz'])[use],'.-',ms=2,label=str(r['norad']) if g==0 else None,alpha=.6)
            axes[0,col].set(title=regime,ylabel='Family residual (Hz)',xlabel='Scan time (s)');axes[0,col].legend();axes[0,col].axhline(0,color='black',lw=.7)
            axes[1,col].bar([str(r['norad']) for r in rows],[r['score'] for r in rows]);axes[1,col].set(ylabel='Matched diagnostic cost',xlabel='NORAD')
        fig.suptitle(f'{z["case"]}: family {n}, {len(entries)} tracks, {len(t)} unique native points\nShared phase/rate and per-track offset diagnostic; no unique identity claim');old_render.save(fig,out/f'family-{n}.png')
    write(out/'family_consistency.json',result)
    return result

def render_graph(target,out):
    a=target['full_graph_audit'];t=np.array(a['times_s']);y=np.array(a['raw_unwrapped_hz']);poly=a['polynomial'];best=poly['rows'][poly['selected_degree']]
    fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    axes[0,0].scatter(t,y/1000,s=12,color='black');axes[0,0].plot(t,np.array(best['prediction'])/1000,label=f'degree {poly["selected_degree"]}')
    keep=np.zeros(len(t),bool);keep[a['retained_indices']]=True;axes[0,0].scatter(t[~keep],y[~keep]/1000,color='red',marker='x',label='Not retained in orbit audit');axes[0,0].legend()
    axes[0,1].plot(range(5),[r['bic'] for r in poly['rows']],'o-');axes[0,1].set(xlabel='Degree',ylabel='Descriptive independent-noise BIC')
    axes[1,0].plot(t,best['residual'],'.-');axes[1,0].axhspan(-150,150,color='gray',alpha=.15);axes[1,0].set(ylabel='Residual (Hz)',xlabel='Scan time (s)')
    for p in a['pieces']:
        for ax in (axes[0,0],axes[1,0]):ax.axvline(p['start_s'],color='orange',alpha=.5,lw=.8);ax.axvline(p['end_s'],color='orange',alpha=.5,lw=.8)
    axes[1,1].bar(['First','Last'],best['endpoint_leverage']);axes[1,1].set(ylabel='Endpoint leverage');axes[0,0].set(xlabel='Scan time (s)',ylabel='Native unwrapped CFO (kHz)')
    fig.suptitle(f'Target {target["index"]}: complete original graph; {len(t)} native points, {len(a["pieces"])} pieces\nPolynomial audit includes endpoints excluded from published orbit evidence; orange = original graph piece boundary');old_render.save(fig,out/f'target-{target["index"]}-graph-audit.png')

def report(case,out,targets,families,swaps):
    lines=[f'# {case}: orbit and curve diagnostic', '', 'The catalogue search compares the saved ALGO06 composition at its own inferred positions. Per-track nuisance fits are diagnostic lower bounds; a clean fit does not establish unique identity. No localization gain or production recovery is claimed.', '', '| Target | Incumbent | Regime | L3 winner / runner-up | Margin | RMS Hz | Phase s | Rate Hz/s | Noise gate |', '|---|---:|---|---|---:|---:|---:|---:|---|']
    summary=[];details=[]
    for target in targets:
        for regime in ('causal','later'):
            rr=sorted([r for r in target['results'] if r['regime']==regime and r['arm']=='fitted_c' and r['model']=='L3_phase'],key=lambda r:r['score'])
            if not rr:continue
            w=rr[0];runner=rr[1] if len(rr)>1 else None;margin=runner['score']-w['score'] if runner else None
            margin_text=f'{margin:.2f}' if margin is not None else 'missing'
            lines.append(f'| {target["index"]}: {target["key"]} | {target["meta"]["assigned_norad"]} | {regime} | {w["norad"]} / {runner["norad"] if runner else "missing"} | {margin_text} | {w["rms_hz"]:.1f} | {w["phase_s"]:.1f} | {w["rate_hz_s"]:.2f} | {w["noise"]["noise_screen_pass"]} |')
            summary.append(dict(target=target['index'],incumbent=target['meta']['assigned_norad'],regime=regime,winner=w['norad'],runner_up=runner['norad'] if runner else None,margin=margin,rms_hz=w['rms_hz'],noise_pass=w['noise']['noise_screen_pass'],identity_status='ambiguous: independent family validation absent',physical_model_adequacy='diagnostic screen pass' if w['physical_screen_pass'] else 'failed diagnostic screen'))
        poly=target['full_graph_audit']['polynomial'];w=poly['rows'][poly['selected_degree']]
        details += ['',f'Target {target["index"]} full graph selects degree {poly["selected_degree"]} under descriptive independent-noise BIC; RMS {w["rms_hz"]:.1f} Hz; endpoint leverage {w["endpoint_leverage"]}. Irregular correlation limits this complexity score. Piece fits and excluded original endpoints are retained in `targets.json`.',f'![Orbit](target-{target["index"]}-orbit.png)',f'![Graph audit](target-{target["index"]}-graph-audit.png)',f'![Consecutive 20-second context](target-{target["index"]}-20s.png)',f'![Candidates](target-{target["index"]}-models.png)']
    lines += details
    lines += ['', 'Whole-family consistency uses all published native owners of each influential family and matched shortlists. A shared phase/rate must explain every track. Constants remain per-track diagnostic terms; no independent receiver correction is inferred from them.', '', 'These restricted-model RMS values are not published baseline residuals. The restricted search uses SGP4 phase plus constant/rate in place of the production marginalized satellite/orbit nuisance block. It omits the posterior physical orbital-mode corrections and any satellite-clock/family corrections in that full block. Published full-model residuals and exact production gates are recorded separately in the sibling diagnostics report. A restricted-model failure therefore does not prove the published association is wrong.']
    for family_item in families:
        n=family_item['incumbent'];lines += ['',f'![Family {n}](family-{n}.png)']
        for regime in ('causal','later'):
            rr=sorted([r for r in family_item['results'] if r['regime']==regime and r['arm']=='fitted_c' and r['model']=='shared_phase_small_rate'],key=lambda r:r['score'])
            if rr:
                w=rr[0];lines += [f'{regime} family {n}: best shortlist identity {w["norad"]}, RMS {w["rms_hz"]:.1f} Hz, shared phase {w["phase_s"]:.1f} s, rate {w["rate_hz_s"]:.2f} Hz/s, all-track noise pass {w["all_tracks_noise_pass"]}.']
    lines += ['', 'Paired causal/later swaps appear in `frozen_tle_swap.json`: the frozen-corrections comparison isolates the changed elements; later-refitted values are separately labeled. Missing later exact fits are null. Exact production gates and localization ablations live in the sibling diagnostics report. These per-track RMS/noise screens are not a replacement for those gates.', '', 'Search: every propagation-valid member of causal ≤72h and first-post-epoch ≤48h catalogues receives a coarse scan. Matched c arms share top-three model nominees plus the incumbent and exact phase budget. L1/L2 freeze the saved phase; L3/L4 profile ±30s with a 5s prior. L2 rate prior SD is 0.5 Hz/s and L4 is 2 Hz/s. Detailed inventories and hash provenance are in `run_manifest.json`, `tle_inventory.csv`, and search coverage files.', '', 'Remaining ambiguity: independent whole-group prediction and regional position stability have not been executed for these single-track catalogue fits. Per-track slopes cannot distinguish receiver clock, calibration and orbit errors. Next bounded discriminator: compare the same candidate over independent receivers/families using a shared correction, then replay exact ownership gates.', '', 'Reproduce from the worktree with `PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python reports/2026_11_02_algo07_top10_outliers/orbits/investigate.py CASE`, then the same invocation of `finish.py CASE`. Archive creation requires the existing read-only archive permission. No RF collection was performed.']
    (out/'report.md').write_text('\n'.join(lines)+'\n');write(out/'association_summary.json',summary)
    with (out/'association_summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=summary[0]);w.writeheader();w.writerows(summary)

def run_finish(case):
    setup();out=ROOT/case;d,z,replay=engine.load_case(case);targets=read(out/'targets.json');ledger=read(out/'tle-ledger.json');enrich(d,targets);write(out/'targets.json',targets)
    swaps=paired_swaps(d,z,targets,ledger);write(out/'frozen_tle_swap.json',swaps);write(out/'targets.json',targets)
    old_render.contexts(case,z,d,out)
    old_render.target_figures(case,out)
    for target in targets:render_graph(target,out)
    families=family(d,z,targets,ledger,out);report(case,out,targets,families,swaps)
    import subprocess
    manifest=read(out/'run_manifest.json');manifest.update(actual_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),engine_sha256=hashlib.sha256((REPO/'tools/algo07_science/engine.py').read_bytes()).hexdigest(),renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),original_graph_points_preserved=True,family_consistency_status='complete conditional shortlist; independent identity validation absent');write(out/'run_manifest.json',manifest)
    write(out/'candidate_fits.json',[dict(r,target=t['index']) for t in targets for r in t['results']])
    print(case,'finished plots/family',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case',choices=CASES);run_finish(ap.parse_args().case)
