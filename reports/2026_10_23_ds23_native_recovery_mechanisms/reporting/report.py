"""Read-only inference artifacts; GPS is used exclusively for evaluation here."""
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023')
spec = importlib.util.spec_from_file_location('frozen_report', FROZEN/'source/report_full.py')
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)
position_error = oracle.position_error
ARMS = ('c0', 'fitted_c')


def read(path):
    return json.loads(path.read_text())


def row(case, method, arm, fit, status='complete', cov=None, **metadata):
    r = dict(case=case, method=method, arm=arm, status=status,
             error_km=None, east_km=None, north_km=None, RMS_hz=None,
             objective=None, full_same_mask_objective=None, minimum_gate_slack=None,
             failing_gates=None, qualified=None, associated=None, total_GLRT=None,
             active_points=None, predictive_points=None, offered_likelihood_points=None,
             likelihood_points_minus_associated=None, **metadata)
    if status != 'complete' or not fit:
        return r
    point = fit.get('endpoint_latlon')
    if point is None or len(point) != 2 or not all(math.isfinite(x) for x in point):
        raise ValueError('Invalid completed endpoint')
    en = fit['endpoint_east_north_km']
    slacks = fit.get('gate_slacks', {})
    r.update(error_km=position_error(point), east_km=en[0], north_km=en[1],
             RMS_hz=fit.get('RMS_hz'), objective=fit.get('negative_twice_elbo'),
             full_same_mask_objective=fit.get('untempered_same_mask_objective'),
             minimum_gate_slack=min(slacks.values()) if slacks else None,
             failing_gates=sum(v < 0 for v in slacks.values()) if slacks else None,
             qualified=fit.get('qualified', min(slacks.values())>=0 if slacks else None), active_points=fit.get('active_points'),
             predictive_points=fit.get('predictive_points'))
    if cov:
        r['associated'], r['total_GLRT'] = oracle.coverage(cov)
    if r['active_points'] is not None and r['predictive_points'] is not None:
        r['offered_likelihood_points']=r['active_points']+r['predictive_points']
        if r['associated'] is not None:
            r['likelihood_points_minus_associated']=r['offered_likelihood_points']-r['associated']
    if r['minimum_gate_slack'] is None:
        r['minimum_gate_slack']=fit.get('minimum_gate_slack')
    return r


def table(name, rows):
    path = ROOT/'tables'/f'{name}.csv'
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=keys, lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def main():
    for name in ('tables', 'figures'):
        (ROOT/name).mkdir(exist_ok=True)
    rows, gates, hashes, statuses = [], [], {}, []
    def tracked(path):
        hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return read(path)
    for case in ('DS23-0259', 'DS23-0365', 'DS23-0041', 'DS23-0272'):
        old = tracked(FROZEN/'raw'/case/'result.json')
        for key, label in (('reference','saved_reference'), ('ordinary_graph','saved_graph'), ('final','saved_final')):
            for arm in ARMS:
                view = old[key]
                rows.append(row(case,label,arm,view['arms'][arm],cov=view['coverage'][arm]))
    for job in tracked(ROOT/'protocol.json')['jobs']:
        path = ROOT/'raw'/job['name']/'result.json'
        d = tracked(path) if path.exists() else {'status':'pending'}
        statuses.append(dict(name=job['name'], status=d['status'], error=d.get('error')))
        for arm in ARMS:
            fit = d.get('arms',{}).get(arm)
            rows.append(row(job['case'],job['name'],arm,fit,d['status'],d.get('coverage',{}).get(arm),
                            mode=job['mode'], family=job.get('family'), alpha=job['alpha'],
                            paired_gates_pass=d.get('paired_gates_pass'), parent_IDs_preserved=d.get('parent_IDs_preserved')))
            if fit and d['status']=='complete':
                gates.extend(dict(case=job['case'],method=job['name'],arm=arm,gate=k,slack=v) for k,v in fit.get('gate_slacks',{}).items())
    solver_path = ROOT/'solver0365/results.json'
    solver_summary=tracked(ROOT/'solver0365/summary.json')['rows']
    if solver_path.exists():
        for case in tracked(solver_path)['cases']:
            for f in case['fits']:
                status = 'complete' if f.get('summary') and not f.get('error') else 'failed'
                method = 'solver_'+f['solver']
                r=row(case['case'],method,f['arm'],f.get('summary'),status,seconds=f.get('seconds'))
                compact=next((x for x in solver_summary if x['case']==case['case'] and x['arm']==f['arm'] and x['solver']==f['solver']),{})
                r['associated']=compact.get('associated_points')
                r['total_GLRT']=next(x['total_GLRT'] for x in rows if x['case']==case['case'] and x['method']=='saved_graph')
                rows.append(r)
                if status=='complete':
                    gates.extend(dict(case=case['case'],method=method,arm=f['arm'],gate=k,slack=v) for k,v in f['summary'].get('gate_slacks',{}).items())
    follow=tracked(ROOT/'solver0365/followup/results.json')
    tracked(ROOT/'solver0365/followup/summary.json')
    for arm,f in follow['ablation'].items():
        rows.append(row('DS23-0365','path_exclusion',arm,f['summary'],cov=f['coverage'],
                        parent_IDs_preserved=f['original_parent_ids_preserved']))
    bias=[]
    bias_summary=tracked(ROOT/'solver0365/bias_prior/summary.json')['rows']
    for case in tracked(ROOT/'solver0365/bias_prior/results.json')['cases']:
        for f in case['fits']:
            compact=next(x for x in bias_summary if x['case']==case['case'] and x['arm']==f['arm'] and x['native_bias_sigma_hz']==f['native_bias_sigma_hz'])
            baseline=next(x for x in bias_summary if x['case']==case['case'] and x['arm']==f['arm'] and x['native_bias_sigma_hz']==300)
            r=row(case['case'],'bias_sigma_'+str(f['native_bias_sigma_hz']),f['arm'],f['summary'],cov=f['coverage'],
                  native_bias_sigma_hz=f['native_bias_sigma_hz'],common_sigma300_objective=compact['common_sigma300_objective'],
                  delta_common_sigma300_objective=compact['common_sigma300_objective']-baseline['common_sigma300_objective'],
                  new_model_objective=compact['own_objective'],parent_IDs_preserved=f['original_parent_ids_preserved'])
            r['qualified']=f['qualified']
            bias.append(r)
    rows.extend(bias)
    for r in rows:
        r['associated_percent']=100*r['associated']/r['total_GLRT'] if r['associated'] is not None and r['total_GLRT'] else None
    table('bias_prior',bias)
    table('0365_comparison',[r for r in rows if r['case']=='DS23-0365'])
    table('positions',rows); table('gates',gates); table('execution_status',statuses)
    table('family_ablation',[r for r in rows if r.get('mode') in ('only','without')])
    table('full_evidence_weights',[r for r in rows if r.get('mode')=='all' or r['method']=='saved_graph'])
    table('solver_comparison',[r for r in rows if r['method'].startswith('solver_') or r['method'].startswith('saved_')])
    table('coverage',[{k:r.get(k) for k in ('case','method','arm','status','associated','associated_percent','total_GLRT','active_points','predictive_points','offered_likelihood_points','likelihood_points_minus_associated','parent_IDs_preserved')} for r in rows])
    active=[]
    for r in rows:
        gg=sorted((g for g in gates if all(g[k]==r[k] for k in ('case','method','arm'))),key=lambda g:g['slack'])
        active.extend(dict(g,rank=i+1) for i,g in enumerate(gg[:5]))
    table('active_gates',active)
    paired=[]
    for r in rows:
        if r['arm']!='c0' or r['error_km'] is None: continue
        other=next((x for x in rows if x['case']==r['case'] and x['method']==r['method'] and x['arm']=='fitted_c'),None)
        if other and other['error_km'] is not None:
            paired.append(dict(case=r['case'],method=r['method'],fitted_minus_c0_error_km=other['error_km']-r['error_km'],fitted_minus_c0_RMS_hz=other['RMS_hz']-r['RMS_hz']))
    table('c_ablation',paired)
    receipt=dict(GPS_evaluation_only=True,position_helper=str(FROZEN/'source/report_full.py'),input_sha256=hashes,
                 expected_native_jobs=len(statuses),native_status_counts={s:sum(x['status']==s for x in statuses) for s in ('complete','failed','pending')},
                 score_caveat='Subset objectives are not comparable across family masks; frequency fit is separate from position accuracy.',
                 dose_interpretation='Prespecified discrete diagnostic weights, never GPS-optimized or an adopted production rule.',
                 source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),no_new_release=True,
                 bias_score_interpretation='Compare common sigma300 score changes separately from new-model objectives; no GPS selection or promotion.',
                 coverage_interpretation='Associated counts accepted unique original IDs, including possible postfit extensions. Likelihood points and associated points have different scopes; no conclusion follows from their signed difference.')
    (ROOT/'reporting/receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    plots(rows,gates)


def plots(rows,gates):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(14,5),layout='constrained')
    for ax,arm in zip(axes,ARMS):
        rr=[r for r in rows if r.get('mode') in ('only','without') and r['arm']==arm and r['error_km'] is not None]
        ax.barh(range(len(rr)),[r['error_km'] for r in rr],color=['#4477aa' if r['mode']=='only' else '#ee7733' for r in rr])
        ax.set_yticks(range(len(rr)),[f"{r['mode']} {r['family']}" for r in rr],fontsize=8)
        for label,style in (('saved_graph','--'),('DS23-0259_all',':')):
            r=next((r for r in rows if r['case']=='DS23-0259' and r['method']==label and r['arm']==arm),None)
            if r and r['error_km'] is not None: ax.axvline(r['error_km'],linestyle=style,label=label,color='black')
        ax.set(title=arm,xlabel='Evaluation position error (km)');ax.legend(fontsize=7)
    fig.savefig(ROOT/'figures/family_ablation.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    # Exact inverse of prototype_dsx01_continuous_position.latlon; evaluation only.
    gps=oracle.REFERENCE; center=(37.906,-122.545)
    gps_en=((gps[1]-center[1])*111.32*math.cos(math.radians(center[0])),(gps[0]-center[0])*111.0)
    for ax,arm in zip(axes,ARMS):
        rr=[r for r in rows if r['case']=='DS23-0259' and r['arm']==arm and (r.get('mode')=='all' or r['method']=='saved_graph') and r['error_km'] is not None]
        rr.sort(key=lambda r:r.get('alpha') or 0)
        ax.plot([r['east_km'] for r in rr],[r['north_km'] for r in rr],'-o')
        for r in rr:ax.annotate(str(r.get('alpha') or 0),(r['east_km'],r['north_km']))
        ax.scatter(*gps_en,marker='*',s=140,label='True GPS (evaluation only)')
        ax.set(title=arm,xlabel='East of regional center (km)',ylabel='North of regional center (km)',aspect='equal');ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.savefig(ROOT/'figures/dose_trajectory.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained')
    for col,arm in enumerate(ARMS):
        rr=[r for r in rows if r['method'].startswith('solver_') and r['arm']==arm and r['error_km'] is not None]
        labels=[r['case']+' '+r['method'].removeprefix('solver_') for r in rr]
        axes[0,col].barh(range(len(rr)),[r['error_km'] for r in rr]);axes[0,col].set_yticks(range(len(rr)),labels,fontsize=8)
        axes[0,col].set(title=arm,xlabel='Evaluation position error (km)')
        axes[1,col].barh(range(len(rr)),[r['minimum_gate_slack'] for r in rr],color=['#228833' if r['minimum_gate_slack']>=0 else '#cc3311' for r in rr]);axes[1,col].set_yticks(range(len(rr)),labels,fontsize=8)
        axes[1,col].axvline(0,color='black');axes[1,col].set(xlabel='Minimum gate slack (negative fails)')
    fig.savefig(ROOT/'figures/solver_and_gates.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(3,2,figsize=(15,12),layout='constrained')
    for i,case in enumerate(('DS23-0365','DS23-0041','DS23-0272')):
        for j,arm in enumerate(ARMS):
            ax=axes[i,j]
            subset=[g for g in gates if g['case']==case and g['arm']==arm and g['method'].startswith('solver_')]
            names=set()
            for method in ('solver_ordinary','solver_constrained'):
                names.update(g['gate'] for g in sorted((g for g in subset if g['method']==method),key=lambda g:g['slack'])[:3])
            names=sorted(names)
            for offset,method in ((-.18,'solver_ordinary'),(.18,'solver_constrained')):
                lookup={g['gate']:g['slack'] for g in subset if g['method']==method}
                ax.barh([k+offset for k in range(len(names))],[lookup.get(n,float('nan')) for n in names],height=.35,label=method.removeprefix('solver_'))
            ax.set_yticks(range(len(names)),[n.replace(case+'-','').replace('GRAPH_PATH_persistent5s_','native_') for n in names],fontsize=6)
            ax.axvline(0,color='black',lw=.7);ax.set(title=case+' '+arm,xlabel='Gate slack (negative fails)');ax.legend(fontsize=7)
    fig.suptitle('Union of three smallest gate slacks per solver; complete gates in gates.csv')
    fig.savefig(ROOT/'figures/active_gates.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    for col,arm in enumerate(ARMS):
        rr=[r for r in rows if r['case']=='DS23-0365' and r['arm']==arm and r['method'] in ('saved_reference','saved_graph','solver_ordinary','solver_constrained','path_exclusion')]
        labels=[r['method']+(' [RF gate FAIL; diagnostic]' if r['qualified'] is False else '') for r in rr]
        axes[0,col].barh(range(len(rr)),[r['error_km'] for r in rr],color=['#cc3311' if r['qualified'] is False else '#4477aa' for r in rr])
        axes[0,col].set_yticks(range(len(rr)),labels,fontsize=7);axes[0,col].set(title='DS23-0365 '+arm,xlabel='Evaluation position error (km)')
        for case in ('DS23-0259','DS23-0041','DS23-0272'):
            rr=sorted((r for r in rows if r['case']==case and r['arm']==arm and r.get('native_bias_sigma_hz')),key=lambda r:r['native_bias_sigma_hz'])
            axes[1,col].plot([r['native_bias_sigma_hz'] for r in rr],[r['error_km'] for r in rr],'-o',label=case)
        axes[1,col].set(xscale='log',xlabel='New native path bias sigma (Hz; diagnostic)',ylabel='Evaluation position error (km)',title=arm);axes[1,col].legend(fontsize=8);axes[1,col].grid(alpha=.2)
        from matplotlib.ticker import NullLocator
        axes[1,col].set_xticks([300,600,3000],['300','600','3000'])
        axes[1,col].xaxis.set_minor_locator(NullLocator())
    fig.suptitle('RF gate exclusion and native mean uncertainty diagnostics; no production adoption')
    fig.savefig(ROOT/'figures/followup_and_bias_prior.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    main()
