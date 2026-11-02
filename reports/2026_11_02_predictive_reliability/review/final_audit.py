"""Independent endpoint/receipt replay; no optimizer, refit or geography."""
import hashlib,importlib.util,json,signal,subprocess,time
from collections import Counter
from pathlib import Path
import numpy as np
from algo07_science import engine as e
from algo07_science.diagnose import objective
from algo07_science.validation import clean
from algo06_science.common import read,write

ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
m=module('independent_endpoint_engine',BASE/'predictive/engine.py')
decision=module('independent_frozen_decision',BASE/'decision.py')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(v):return json.dumps(clean(v),sort_keys=True,separators=(',',':'))
def compare(actual,saved,label,issues,atol=2e-6,rtol=2e-7):
    if not np.allclose(actual,saved,atol=atol,rtol=rtol):issues.append(label)

def replay(d,z,record,part,row):
    issues=[];a=m.native(d['problems']['fitted_c'][0])
    train=np.isin(a['ids'],part['train_ids']);held=np.isin(a['ids'],part['held_ids'])
    dd=m.family.candidate_context(d,z,row['SD_scale'],family=record['family'])
    dd,zz,receipt=m.adapter.prepare_context(dd,z,train)
    p,ctx=e.build(dd,zz,row['arm'],np.asarray(row['reference']));x=np.asarray(row['x_km']);c=p.calculate(x)
    if row['preprocessing']!=receipt:issues.append('preprocessing_receipt')
    for key,use in [('train_ids_sha256',train),('held_ids_sha256',held)]:
        if row[key]!=hashlib.sha256('\n'.join(a['ids'][use]).encode()).hexdigest():issues.append(key)
    if not np.all(p.point_noise==150.) or not np.all(dd['powers']==1.):issues.append('fixed_noise_unit_powers')
    if dd['entries'] or dd['families'] or 'selected' in zz or 'gap_selected' in zz:issues.append('ancillary_not_omitted')
    compare(objective(p,ctx,x),row['history'][-1]['objective'],'endpoint_training_objective',issues)
    phase=np.max(abs(p.state(x)['phases'][p.labels]-p.reference))
    compare(phase,row['phase_change_s'],'raw_phase_gap',issues,atol=1e-10,rtol=1e-9)
    u=c['features'];g=p.noise_groups[train];w=c['noise_precision'][g]/150.**2
    gram=np.diag(c['coefficient_prior_precision'])+u[train].T@(u[train]*w[:,None])
    nuisance=np.linalg.solve(np.linalg.cholesky(gram),u.T).T
    mean=p.q*c['intercept']+u@c['coefficient'];raw=p.values-mean
    counts=np.bincount(g,minlength=len(c['noise_precision']));alpha=2.+counts/2.
    inv=np.full(len(alpha),2.);present=counts>0
    inv[present]=alpha[present]/((alpha[present]-1)*c['noise_precision'][present])
    sigma=150.*np.sqrt(inv[p.noise_groups])
    compare(alpha,row['noise']['posterior_shape'],'Gamma_shapes',issues)
    compare(c['noise_precision'],row['noise']['mean_precision'],'Gamma_precision',issues)
    compare(inv,row['noise']['inverse_precision_expectation'],'Gamma_inverse_moment',issues)
    compare(c['final_log_precision_change'],row['final_inner_precision_change'],'inner_convergence',issues,atol=1e-12,rtol=1e-8)
    cost=lambda at:objective(p,ctx,at);h=.02;f0=cost(x);H=np.zeros((2,2));J=[]
    for k in range(2):
        dlt=np.eye(2)[k]*h;cp=p.calculate(x+dlt);cm=p.calculate(x-dlt)
        J.append(((p.q*cp['intercept']+cp['features']@cp['coefficient'])-(p.q*cm['intercept']+cm['features']@cm['coefficient']))/(2*h))
        H[k,k]=(cost(x+dlt)+cost(x-dlt)-2*f0)/h**2
    v0,v1=np.eye(2)*h
    H[0,1]=H[1,0]=(cost(x+v0+v1)-cost(x+v0-v1)-cost(x-v0+v1)+cost(x-v0-v1))/(4*h*h)
    eig,vec=np.linalg.eigh(H/2);floored=np.maximum(eig,1/(25.**2/12));S=(vec/floored)@vec.T
    compare(eig,row['position_precision_eigenvalues'],'position_curvature',issues)
    compare(S,row['position_covariance_km2'],'position_covariance',issues)
    probes_valid=True
    for probe in row['local_gaussian_probes']:
        at=np.asarray(probe['position_km']);inside=bool(np.all(abs(at)<=12.5))
        change=cost(at)-f0 if inside else None
        if inside:compare(change,probe['training_negative_twice_objective_change'],'training_probe_objective',issues)
        passed=inside and abs(change-1.)<=.5
        if passed!=probe['pass_probe']:issues.append('training_probe_gate')
        probes_valid &= passed
    j=np.column_stack(J);position=j@np.linalg.cholesky(S);maxscore=0.;quadrature_valid=True
    for key,use in {'all':held,'target':held&(a['family']==record['family']),'other':held&(a['family']!=record['family'])}.items():
        saved=row['scores'][key]
        if not use.any():
            if saved['status']!='not_applicable':issues.append(key+'_subset_scope')
            continue
        orig=m.gaussian(raw[use],sigma[use],np.column_stack((nuisance[use],position[use])))
        bounded=m.box.correct_score(orig['negative_twice_log_density'],raw[use],sigma[use],nuisance[use],j[use],x,S)
        for field in ('negative_twice_log_density','quadratic','logdet_hz2','points'):compare(orig[field],saved['unbounded'][field],key+'_unbounded_'+field,issues)
        diff=abs(bounded['negative_twice_log_density']-saved['bounded']['negative_twice_log_density']);maxscore=max(maxscore,diff)
        compare(bounded['negative_twice_log_density'],saved['bounded']['negative_twice_log_density'],key+'_bounded_score',issues)
        for box in ('prior_box','posterior_box'):
            compare(bounded[box]['log_probability'],saved['bounded'][box]['log_probability'],key+'_'+box,issues)
            quadrature_valid &= np.isfinite(bounded[box]['relative_quadrature_error']) and bounded[box]['relative_quadrature_error']<=1e-6
    expected=bool(phase<=.01 and row['history'][-1]['optimizer_success'] and np.all(abs(x)<=12.49)
        and np.all(eig>0) and np.all(eig==floored) and c['final_log_precision_change']<=1e-5
        and probes_valid and np.min(c['elevation'][train])>=0 and quadrature_valid)
    if expected!=row['numerical_fit_qualified']:issues.append('independent_numerical_qualification')
    return dict(case=record['case'],split=part['name'],arm=row['arm'],SD_scale=row['SD_scale'],issues=sorted(set(issues)),
        numerical_qualified=row['numerical_fit_qualified'],maximum_bounded_score_difference=maxscore,
        source_cell_sha256=sha(BASE/'predictive/cells'/f"{record['case']}_{part['name']}_{row['arm']}_SD{row['SD_scale']:g}.json"))

def main():
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s endpoint-replay cap')));signal.alarm(180)
    protocol=read(BASE/'protocol.json');plan=read(BASE/'predictive/plan.json');result=read(BASE/'predictive/results.json')
    ph=sha(BASE/'protocol.json');issues=[];audits=[];decisions=[]
    for path,h in protocol['source_sha256'].items():
        if sha(path)!=h:issues.append('frozen source: '+path)
    if sha(BASE/'roster.json')!=protocol['roster_sha256']:issues.append('roster_hash')
    if sha(BASE/'predictive/plan.json')!=protocol['plan_sha256'] or result['plan_sha256']!=protocol['plan_sha256']:issues.append('plan_hash')
    if result['protocol_sha256']!=ph:issues.append('results_protocol')
    if len(result['rows'])!=100 or not result['all_workers_joined']:issues.append('execution_completion')
    index={(r['case'],r['split'],r['arm'],r['SD_scale']):r for r in result['rows']}
    if len(index)!=100:issues.append('duplicate_cells')
    for record in plan['cases']:
        path=Path(record['input_path'])
        if sha(path)!=record['input_sha256']:issues.append('native_input: '+record['case'])
        e.configure(path.parent.parent,ROOT/'local_engine');e.ROOTS[record['case'][:4]]=path.parent.parent
        d,z,_=e.load_case(record['case']);expected=m.plans(d['problems']['fitted_c'][0],record['family'],record['seed'])
        if canonical(expected)!=canonical(record['partitions']):issues.append('partition/support regeneration: '+record['case'])
        for part in record['partitions']:
            for arm in ('c0','fitted_c'):
                for scale in (1.,4.):
                    row=index[(record['case'],part['name'],arm,scale)]
                    cell=BASE/'predictive/cells'/f"{record['case']}_{part['name']}_{arm}_SD{scale:g}.json"
                    if read(cell)!=row:issues.append('cell/aggregate binding: '+cell.name)
                    if row['protocol_sha256']!=ph:issues.append('cell/protocol binding: '+cell.name)
                    if not part['eligible']:
                        if row['status']!='ineligible_support' or row.get('numerical_fit_qualified'):issues.append('unsupported cell scope: '+cell.name)
                    elif row['status']=='complete':audits.append(replay(d,z,record,part,row))
        case_rows=[r for r in result['rows'] if r['case']==record['case']]
        decisions.append(dict(case=record['case'],**decision.decide(record['partitions'],case_rows)))
    processes=subprocess.run(['ps','-eo','pid,args'],check=True,capture_output=True,text=True).stdout.splitlines()
    running=[s.strip() for s in processes if '/predictive_reliability/predictive/runner.py --run' in s and 'python' in s]
    # Completed worker children inherit the manager command line; no matching
    # numerical runner processes may remain after the explicit pool join.
    if running:issues.append('numerical runner processes still active')
    for path,h in protocol['source_sha256'].items():
        if sha(path)!=h:issues.append('frozen source changed during replay: '+path)
    signal.alarm(0)
    failed=[r for r in audits if r['issues']]
    output=dict(status='passed' if not issues and not failed else 'failed',scope='Fixed-endpoint evaluations and frozen decision replay only; no optimizer, refit or geography',
        protocol_sha256=ph,plan_sha256=sha(BASE/'predictive/plan.json'),results_sha256=sha(BASE/'predictive/results.json'),
        review_source_sha256=sha(Path(__file__)),issues=issues,failed_cells=failed,completed_endpoint_replays=len(audits),
        cell_status_counts=dict(Counter(r['status'] for r in result['rows'])),
        maximum_bounded_score_difference=max((r['maximum_bounded_score_difference'] for r in audits),default=0.),
        running_numerical_processes=running,seconds=time.monotonic()-began,decisions=decisions,endpoint_audits=audits)
    write(ROOT/'final_audit.json',output)
    print(json.dumps({k:output[k] for k in ('status','completed_endpoint_replays','cell_status_counts','maximum_bounded_score_difference','issues','seconds')}),flush=True)

if __name__=='__main__':main()
