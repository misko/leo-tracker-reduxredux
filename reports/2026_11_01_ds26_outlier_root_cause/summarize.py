"""Build report tables, reproducibility ledger and case galleries."""
import csv,hashlib,json,subprocess
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from diagnose import ROOT,INPUT,CASES,ARMS,read,write
from family_debug import SUSPECT

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def run():
    rows=[];inventory=[];fig,axes=plt.subplots(1,2,figsize=(14,6),layout='constrained')
    for i,case in enumerate(CASES):
        out=ROOT/case;z=read(INPUT/(case+'.json'));a=read(out/'audit.json');n=SUSPECT[case]
        name=f'extended_omit_{n}' if (out/f'extended_omit_{n}.json').exists() else f'omit_{n}'
        omitted=read(out/(name+'.json'));gates=read(out/'gate_validation.json');targets=read(out/'targets.json')
        candidate_rows=[]
        for t in targets:
            for r in t['results']:
                candidate_rows.append(dict(target=t['index'],source=t['key'],role=t['meta']['role'],
                    regime=r['regime'],arm=r['arm'],norad=r['norad'],model=r['model'],score=r['score'],
                    rms_hz=r['rms_hz'],phase_s=r['phase_s'],bias_hz=r['bias_hz'],rate_hz_s=r['rate_hz_s'],
                    alias=r['alias'],minimum_elevation_deg=r['minimum_elevation_deg'],physical_screen_pass=r['physical_screen_pass'],
                    mean_z=r['noise']['mean_z'],slope_z=r['noise']['slope_z'],quadratic_bic_gain=r['noise']['quadratic_bic_gain'],
                    maximum_step_z=r['noise']['maximum_step_z'],lag1_acf=r['noise']['lag1_acf'],
                    uncertainty_status='parameter posterior uncertainty not estimated in this diagnostic',identity_status='model-sensitive or ambiguous; no independent uniqueness certification'))
        with (out/'candidate_fits.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=candidate_rows[0]);w.writeheader();w.writerows(candidate_rows)
        association=list(csv.DictReader((out/'association_summary.csv').open()))
        for r in association:
            r['identity_status']='ambiguous' if r['role']=='longest_unassociated' and case in ['DS26-0203','DS26-0070'] else 'model-sensitive'
            r['qualification']='diagnostic shortlist preference only; consult causal partition audit and family transfer before accepting identity'
        with (out/'association_summary.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=association[0]);w.writeheader();w.writerows(association)
        files=[INPUT/(case+'.json'),Path(z['inventory_path']),Path(z['native_path'])/'observations.json',Path(z['native_path'])/'nominal_elements.json']
        inventory.append(dict(case=case,inputs={str(p):sha(p) for p in files},scan_receipt=z['scan_receipt'],
            native_total=len(read(Path(z['native_path'])/'observations.json')),associated=len(z['baseline_owners']['fitted_c']),
            family=n,curved_family_points=sum(t['n'] for t in read(out/'track_residuals.json') if t['arm']=='fitted_c' and t['norad']==n)))
        replacements=[]
        for path in sorted(out.glob('replace*.json')):
            r=read(path)
            if r.get('arms'):replacements.append((path.stem,r))
        texts=[f'# {case} evidence gallery', '',f'Published error: **{a["arms"]["fitted_c"]["error_m"]/1000:.3f} km** fitted c; **{a["arms"]["c0"]["error_m"]/1000:.3f} km** c=0. Main influence family: **{n}**. See the [cross-scan conclusions](../README.md).','',
            '## Position and satellite-family influence','',
            '![Loss and influence](loss_and_influence.png)','', '![Family ablations](ablations.png)','',
            '| Trial | c=0 error km | Fitted-c error km | Both phase closed | Both optimizer successful | Remaining base gates |',
            '|---|---:|---:|---|---|---|']
        trialfiles=[('continue',read(out/'continue.json')),('regional_center',read(out/'regional_center.json')),('phase_sigma_x2',read(out/'phase_sigma_x2.json'))]
        trialfiles += [(f'omit_{sat}',read(out/f'omit_{sat}.json')) for sat in read(out/'fit-plan.json')['selected']]
        if name.startswith('extended'):trialfiles.append((name,omitted))
        for tag,pair in trialfiles:
            gg=[r for r in gates if r['trial']==tag];gatepass=all(r['all_base_gates_pass'] for r in gg) if len(gg)==2 else None
            texts.append(f'| {tag} | {pair["c0"]["error_m"]/1000:.3f} | {pair["fitted_c"]["error_m"]/1000:.3f} | {all(r["phase_closed"] for r in pair.values())} | {all(r["optimizer_success"] for r in pair.values())} | {gatepass} |')
            for arm,r in pair.items():rows.append(dict(case=case,trial=tag,arm=arm,error_m=r['error_m'],frequency_objective=r['objective'],RMS_hz=r['rms_hz'],
                points_in_curved_likelihood=r['active_points'],phase_closed=r['phase_closed'],optimizer_success=r['optimizer_success'],base_gates_pass=gatepass))
        texts += ['', 'Gate results here cover retained curved/predictive base terms. Omissions remove evidence; their raw objective is not comparable to the full-data objective. New-family mixture quadrature and complete published-ownership requalification were not rerun for omissions. These are influence experiments, not automatic deletion recommendations.', '',
                  '## Same-observation identity replacements','', '| Replacement | c=0 / fitted-c error km | Fitted-c objective | Failed gate inequalities c=0 / fitted c | Both phase closed | Both optimizer successful |','|---|---:|---:|---:|---|---|']
        for tag,r in replacements:
            pair=r['arms'];texts.append(f'| {r["old"]} → {r["new"]} | {pair["c0"]["error_m"]/1000:.3f} / {pair["fitted_c"]["error_m"]/1000:.3f} | {pair["fitted_c"]["objective"]:.2f} | {len(pair["c0"]["failed_gates"])} / {len(pair["fitted_c"]["failed_gates"])} | {all(v["phase_closed"] for v in pair.values())} | {all(v["optimizer_success"] for v in pair.values())} |')
            for arm,v in pair.items():rows.append(dict(case=case,trial=tag,arm=arm,error_m=v['error_m'],frequency_objective=v['objective'],RMS_hz=v['rms_hz'],points_in_curved_likelihood=v['active_points'],phase_closed=v['phase_closed'],optimizer_success=v['optimizer_success'],base_gates_pass=not v['failed_gates']))
        texts += ['', 'No ownership was changed in production. These experiments retain the fitted observation mask; they do not claim that every previously postfit-only extension remains accepted. Exact checks cover the replacement family plus all base gate inequalities; full promotion still requires independent identity validation and a complete ownership replay. Candidate sets were selected by causal RF scores, not error at the evaluation site.', '',
                  '## Nuisance and receiver transfer', '', '![Nuisance coefficients](nuisance_pulls.png)', '', '![Family transfer](family_transfer.png)', '',
                  'The transfer shortlist was nominated using an inspected full track. Whole-track train/held diagnostics are conditional on that selection, and alias branches use each whole curve. They are not independent prospective validation. Separate constant/affine minima are diagnostic shape bounds.', '',
                  '## GLRT context', '', '![RX1 context](context_RX1.png)', '', '![RX2 context](context_RX2.png)', '', '![GLRT score](glrt_score.png)', '',
                  'Blue/green/yellow colors and NORAD annotations identify owned satellite points; red dots/lines are unassociated graph evidence; orange crosses are untracked evidence. Lines connect native graph samples. The exported score is fractional GLRT winner margin, not the unavailable raw detector statistic.', '',
                  '## Target-by-target debug skill results', '', '| Target | Role | Original NORAD | Points | Span s | Polynomial degree / RMS Hz | Graph parent pieces |', '|---|---|---:|---:|---:|---:|---:|']
        for t in targets:
            p=t['polynomial'];r=p['rows'][p['selected_degree']]
            texts.append(f'| {t["index"]} | {t["meta"]["role"]} | {t["meta"]["assigned_norad"]} | {len(t["times_s"])} | {np.ptp(t["times_s"]):.1f} | {p["selected_degree"]} / {r["rms_hz"]:.1f} | {len(t["pieces"])} |')
        for t in targets:
            k=t['index'];texts += ['',f'### Target {k}: {t["key"]}', '', f'![Orbit and residual](target-{k}-orbit.png)', '',f'![Candidate-model comparison](target-{k}-models.png)', '',f'![Polynomial audit](target-{k}-polynomial.png)', '',f'![Twenty-second native views](target-{k}-20s.png)']
        texts += ['', 'Polynomial BIC assumes independent noise and is descriptive here. Mean/slope removal is automatic for fitted polynomials; acceptance is not inferred from zero fitted mean alone. The target-orbit screen freezes hardware and uses per-source corrections; its failed gate is distinct from a failure of the full production model, which also includes orbital modes.', '',
                  '## Paired TLE swap', '', '| Target / NORAD | Causal RMS Hz | Later TLE, corrections frozen | Later TLE, corrections refitted |', '|---|---:|---:|---:|']
        for r in read(out/'frozen_tle_swap.json'):
            if r['arm']!='fitted_c' or r['status']!='paired':continue
            texts.append(f'| {r["target"]} / {r["norad"]} | {r["causal_rms_hz"]:.1f} | {r["later_frozen_corrections_rms_hz"]:.1f} | {r["later_refitted_rms_hz"]:.1f} |')
        texts += ['', 'The frozen swap preserves the causal phase, alias, offset and rate; large changes mostly expose that phase corrections cannot be carried unchanged between element epochs. The refitted comparison is the fairer shape diagnostic, still at the same inferred position. First-post elements are selected by time within a fixed 48-hour horizon, never by best residual. Missing later candidates are not replaced by causal elements.', '',
                  'Machine-readable results: [family ablation plan](fit-plan.json), [exact replay and loss](audit.json), [all gate outcomes](gate_validation.json), [candidate summaries](association_summary.csv), [full candidate predictions](targets.json), [family-transfer fits](family_diagnostic.json), [TLE inventory](tle_inventory.csv), [frozen/refitted TLE swap](frozen_tle_swap.json).']
        (out/'README.md').write_text('\n'.join(texts)+'\n')
        for arm,ax in zip(['fitted_c','c0'],axes):
            ax.barh(i-.15,a['arms'][arm]['error_m']/1000,height=.28,color='#777777',label='Published' if i==0 else None)
            bad=next(r for r in gates if r['trial']==name and r['arm']==arm)['failed_gates']
            ax.barh(i+.15,omitted[arm]['error_m']/1000,height=.28,color='#0072b2',hatch='//' if bad else None,label='Omit influential family' if i==0 else None)
            small=omitted[arm]['error_m']/1000<.6
            ax.text(omitted[arm]['error_m']/1000+.05 if small else .05,i+.15,str(n),va='center',color='#0072b2' if small else 'white',fontsize=8)
            if replacements:
                # Select by matched summed RF objective only for the display marker.
                tag,r=min(replacements,key=lambda v:sum(q['objective'] for q in v[1]['arms'].values()));rr=r['arms'][arm]
                good=not rr['failed_gates'] and rr['phase_closed'] and rr['optimizer_success']
                ax.scatter(rr['error_m']/1000,i,marker='o' if good else 'x',s=70,color='#d55e00',label='RF-best tested replacement (× fails qualification)' if i==0 else None)
            ax.set(yticks=range(4),yticklabels=CASES,xlabel='Position error (km)',title=arm);ax.invert_yaxis() if i==0 else None
    for ax in axes:ax.legend(fontsize=8,loc='lower right')
    fig.suptitle('DS26 four largest outliers: diagnostic family influence\nOmission can localize better while discarding real evidence; hatched omission fails a retained-track gate. No deployment changes.')
    fig.savefig(ROOT/'summary.png',dpi=155,bbox_inches='tight');plt.close(fig)
    with (ROOT/'localization_trials.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    write(ROOT/'run_manifest.json',dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        cases=inventory,scripts={p.name:sha(p) for p in ROOT.glob('*.py')},
        scientific_skill='/home/mouse9911/gits/leo-tracker-reduxredux/.agents/skills/find-glrt-association/SKILL.md',
        policy='ALGO06 frozen paired 72h_30s outcomes; all four retain ALGO05; no raw-IQ rerun',
        position_prior=dict(center=[37.906,-122.545],width_km=25),evaluation_site_only=[37.849061591561885,-122.48574968092912],
        future_TLE='diagnostic only: first epoch after scan end, earliest collection tie break, 48h lookahead',
        seeds=[20261101],observations='native unique GLRT; no synthetic interpolation counted',
        changes='research scripts and report artifacts only; no production, recording or published ownership mutation'))

if __name__=='__main__':run()
