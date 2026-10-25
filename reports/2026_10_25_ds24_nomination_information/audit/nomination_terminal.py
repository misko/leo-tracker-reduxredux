"""Independent saved-draw, ordinary-screen and endpoint-reference audit."""
import hashlib
import json
from pathlib import Path
import signal
import time

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp
from scipy.stats import t as student

ROOT=Path(__file__).resolve().parents[1]
NOM=ROOT/'nomination'
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
PERIOD=1e8/440


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def main():
    began=time.monotonic()
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('90s saved-array audit cap')))
    signal.setitimer(signal.ITIMER_REAL,90.)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    protocol=read(NOM/'protocol.json');execution=read(NOM/'execution.json')
    check('frozen protocol matches preflight',sha(NOM/'protocol.json')==read(ROOT/'audit/nomination_preflight.json')['protocol_sha256'])
    for path,h in read(NOM/'RF_seal.json')['files'].items():check('RF binding '+path,sha(path)==h)
    check('terminal all12 trials',execution['all_selected_terminal'] and sum(len(r['rows']) for r in execution['rows'])==12)
    check('600s global cap',execution['cumulative_scientific_seconds']<=600.)
    check('no fits/GPS/identity qualification',execution['position_fits']==0 and execution['GPS_used'] is False and execution['identity_qualified'] is False)
    summaries=[];allrows=[];physical_contexts=0;candidate_contexts=0;adaptive_count=0
    max_coarse_error=0.;max_generator_error=0.;max_null_error=0.;numeric_failures=[];cavity_changes=[]
    for case in protocol['cases']:
        folder=NOM/case;context=read(folder/'context.json');cat=dict(np.load(folder/'context.npz'))
        seal=read(folder/'context_seal.json')
        check(case+' pre-draw context seal',sha(folder/'context.json')==seal['context_json_sha256'] and sha(folder/'context.npz')==seal['context_npz_sha256'] and seal['no_new_CFO_generated_yet'])
        parent=read(SOURCE/'family_cavity/position'/f'{case}.json');tracks={t['key']:t for t in read(SOURCE/case/'tracks.json')}
        node=parent['selected']['node'] if parent['accepted'] else parent['baseline_node']
        oldentries=parent['selected']['entries'] if parent['accepted'] else parent['baseline_entries']
        familyids={};cursor=0
        for r in node['seed']['rows']:
            if not r['active_curvature']:continue
            ids=tracks[r['component']]['observation_ids'];keep=parent['original_mask'][cursor:cursor+len(ids)];cursor+=len(ids)
            familyids.setdefault(r['candidate_index'],set()).update(oid for oid,use in zip(ids,keep,strict=True) if use)
        predictiveids={}
        for e in oldentries:predictiveids.setdefault(e['candidate_index'],set()).update(e['observation_ids'])
        eligible=[j for j in range(len(cat['norads'])) if j not in context['original_parent_families']
                  and np.isfinite(cat['phase_means_s'][j]) and np.isfinite(cat['phase_sd_s'][j]) and cat['phase_sd_s'][j]>0
                  and abs(cat['phase_means_s'][j])<=15 and cat['minimum_mean_elevation_deg'][j]>=0
                  and cat['minimum_domain_endpoint_elevation_deg'][j]>=0]
        check(case+' response-free eligible set',eligible==context['eligible_generating_indices'])
        selected=np.random.Generator(np.random.PCG64(np.random.SeedSequence([protocol['seed'],int(case[-4:]),99]))).choice(eligible,4,replace=False)
        check(case+' reproducible identity draw',selected.tolist()==context['selected_generating_indices'])
        check(case+' no generating family in parent',not set(selected)&set(context['original_parent_families']))
        for trial in range(6):
            f=folder/('trial'+str(trial));truth=read(f/'generation.json');screen=read(f/'screen.json');obs=dict(np.load(f/'observations.npz'))
            values=obs['values_hz'];n=len(values);kind='physical' if trial<4 else 'unresolved'
            check(case+str(trial)+' complete native metadata',np.array_equal(obs['native_ids'],cat['native_ids']) and np.array_equal(obs['times_s'],cat['times_s']) and np.array_equal(obs['q'],cat['q']))
            seeds=[int(child.generate_state(1)[0]) for child in np.random.SeedSequence([protocol['seed'],int(case[-4:]),trial]).spawn(5)]
            check(case+str(trial)+' independent seed children',truth['seed_children']==seeds and len(set(seeds))==5)
            zshape=np.random.Generator(np.random.PCG64(seeds[1])).normal(size=3 if trial<4 else 5)
            zcov=np.random.Generator(np.random.PCG64(seeds[2])).normal(size=n)
            alias=int(np.random.Generator(np.random.PCG64(seeds[3])).choice(np.arange(-4,5)))
            check(case+str(trial)+' shape/polynomial draw',np.array_equal(zshape,truth['shape_or_polynomial_coefficients']))
            check(case+str(trial)+' covariance draw',np.array_equal(zcov,truth['conditional_Gaussian_z']))
            check(case+str(trial)+' uniform finite alias draw',alias==truth['whole_source_alias'])
            check(case+str(trial)+' common generating covariance',np.array_equal(cat['conditional_covariance_hz2'],truth['c0_generating_covariance_hz2']))
            check(case+str(trial)+' common generating radio mean',np.array_equal(cat['radio_mean_hz'],truth['c0_generating_radio_mean_hz']))
            if trial<4:
                j=int(selected[trial]);law=truth['phase_prior']
                check(case+str(trial)+' unforced realized true identity',truth['generating_index']==j and truth['generating_norad']==int(cat['norads'][j]))
                check(case+str(trial)+' original candidate-specific prior',law['nu']==3 and law['original_location_s']==cat['phase_means_s'][j] and law['original_marginal_sd_s']==cat['phase_sd_s'][j])
                distribution=student(3,loc=cat['phase_means_s'][j],scale=cat['phase_sd_s'][j]/np.sqrt(3))
                uniform=np.random.Generator(np.random.PCG64(seeds[0])).uniform()
                phase=distribution.ppf(distribution.cdf(-15)+uniform*(distribution.cdf(15)-distribution.cdf(-15)))
                check(case+str(trial)+' actual conditioned Student phase draw',abs(phase-truth['phase_s'])<1e-11 and uniform==truth['phase_uniform_draw'])
            else:
                check(case+str(trial)+' null has no privileged label',truth['generating_index'] is None and truth['generating_norad'] is None)
                z=2*(obs['times_s']-obs['times_s'].min())/np.ptp(obs['times_s'])-1
                columns=np.polynomial.legendre.legvander(z,4)*PERIOD/np.sqrt(6)
                check(case+str(trial)+' declared polynomial prior',np.array_equal(columns,truth['shape_or_polynomial_columns_hz']))
            generated=cat['radio_mean_hz']+np.asarray(truth['physical_mean_hz'])+np.asarray(truth['shape_or_polynomial_columns_hz'])@zshape+np.linalg.cholesky(cat['conditional_covariance_hz2'])@zcov-alias*PERIOD
            closure=float(np.max(abs(generated-values)));max_generator_error=max(max_generator_error,closure)
            check(case+str(trial)+' exact saved-observation closure',closure<1e-8)
            raw=values-cat['radio_mean_hz'];check(case+str(trial)+' actual injected screen vector',digest(raw)==screen['screen_observation_sha256'])
            residual=raw[None]-cat['frequency_hz'];aliases=np.rint(-residual.mean(axis=1)/PERIOD).astype(int)
            residual=residual+aliases[:,None]*PERIOD
            root=np.linalg.cholesky(cat['conditional_covariance_hz2'])
            white=solve_triangular(root,residual.T,lower=True)
            phase=solve_triangular(root,(cat['derivative_hz_per_s']*cat['phase_sd_s'][:,None]).T,lower=True)
            norm=np.sum(phase**2,axis=0);projection=np.sum(phase*white,axis=0)
            scores=np.sum(white**2,axis=0)-projection**2/(1+norm)+np.log1p(norm)+2*np.log(np.diag(root)).sum()+n*np.log(2*np.pi)
            scores=np.where(cat['minimum_mean_elevation_deg']>=0,scores,np.inf)
            saved=np.array([np.inf if s is None else s for s in screen['coarse_scores']])
            finite=np.isfinite(scores);err=float(np.max(abs(scores[finite]-saved[finite])));max_coarse_error=max(max_coarse_error,err)
            check(case+str(trial)+' independent whole-catalogue coarse scores',np.array_equal(finite,np.isfinite(saved)) and np.allclose(scores[finite],saved[finite],rtol=1e-11,atol=1e-5))
            ranked=sorted(np.flatnonzero(finite),key=lambda j:(scores[j],int(cat['norads'][j])))
            check(case+str(trial)+' ordinary top8 no backfill',screen['candidate_indices']==ranked[:8] and screen['forced_or_reserved_candidate'] is False)
            for arm in ('c0','fitted_c'):
                result=read(f/(arm+'_result.json'));conditional=dict(np.load(f/(arm+'_conditional.npz')));cavity=result['cavity']
                check(case+str(trial)+arm+' same data and position',np.allclose(conditional['raw_hz']+conditional['radio_mean_hz'],values,rtol=0,atol=1e-8) and result['fixed_position_east_north_km']==context['fixed_position_east_north_km'])
                expectedremoved=set().union(*(familyids.get(j,set()) for j in ranked[:8]))
                expectedpred=set().union(*(predictiveids.get(j,set()) for j in ranked[:8]))
                check(case+str(trial)+arm+' exact symmetric curved cavity',set(cavity['removed_curved_ids'])==expectedremoved and set(cavity['calibration_ids'])==set(context['parent_states'][arm]['calibration_ids'])-expectedremoved)
                check(case+str(trial)+arm+' exact symmetric predictive cavity',set(cavity['removed_predictive_ids'])==expectedpred and set(cavity['predictive_ids'])==set(context['parent_states'][arm]['predictive_ids'])-expectedpred)
                check(case+str(trial)+arm+' retained parent numeric/support prerequisites',all(cavity[k] for k in ('phase_qualified','precision_qualified','support_qualified')))
                check(case+str(trial)+arm+' original active shortlist trace',result['original_active_shortlist_families']==sorted(set(ranked[:8])&set(context['original_parent_likelihood_families'])))
                check(case+str(trial)+arm+' no exact truth backfill', [c['candidate_index'] for c in result['candidates']]==ranked[:8])
                candidates=result['candidates'];candidate_contexts+=len(candidates)
                complete=[c for c in candidates if c['status']=='complete'];dense=sorted(complete,key=lambda c:(c['reference_objective'],c['norad']))
                check(case+str(trial)+arm+' dense ranking',result['denser_ranked_norads']==[c['norad'] for c in dense])
                selectedadaptive=set(result['adaptive_checked_norads']);best=dense[0]
                for c in candidates:
                    if c['status']!='complete':continue
                    j=c['candidate_index'];law=c['phase_prior']
                    check(case+str(trial)+arm+str(c['norad'])+' candidate-specific unchanged causal prior',
                          law['nu']==3 and law['original_location_s']==cat['phase_means_s'][j]
                          and law['original_marginal_sd_s']==cat['phase_sd_s'][j])
                    check(case+str(trial)+arm+str(c['norad'])+' prior-mass and visibility',
                          abs(c['quadrature_prior_mass']-1)<1e-8 and c['minimum_elevation_deg']>=0)
                    check(case+str(trial)+arm+str(c['norad'])+' score discrepancy',abs(abs(c['objective']-c['reference_objective'])-c['score_error'])<1e-8)
                    valid=c['score_error']<=1e-3
                    if c['norad'] in selectedadaptive:
                        adaptive_count+=1
                        if 'adaptive_reference' in c:
                            check(case+str(trial)+arm+str(c['norad'])+' actual adaptive discrepancy',
                                  abs(abs(c['objective']-c['adaptive_reference']['objective'])-c['adaptive_score_error'])<1e-8
                                  and c['adaptive_reference']['relative_integral_error']<=1e-6)
                        valid &= ('adaptive_reference'in c and c.get('adaptive_score_error',float('inf'))<=1e-3)
                    check(case+str(trial)+arm+str(c['norad'])+' qualification retained',c['numerically_qualified']==valid)
                valid=len(complete)==len(candidates) and best['numerically_qualified'] and all(c['numerically_qualified'] for c in candidates if c['norad'] in selectedadaptive)
                check(case+str(trial)+arm+' whole ordering guard',result['ordering_numerically_qualified']==valid)
                # Exact normalized finite-mixture polynomial comparator, from
                # the same saved parent-conditioned vector/covariance.
                z=2*(obs['times_s']-obs['times_s'].min())/np.ptp(obs['times_s'])-1
                b=np.polynomial.legendre.legvander(z,4)*PERIOD/np.sqrt(6)
                covariance=conditional['covariance_hz2']+b@b.T
                raw=conditional['raw_hz'];ys=raw[None]+np.arange(-4,5)[:,None]*PERIOD
                costs=np.sum(ys*np.linalg.solve(covariance,ys.T).T,axis=1)+np.linalg.slogdet(covariance)[1]+n*np.log(2*np.pi)
                oracle=float(-2*(logsumexp(-costs/2)-np.log(9)))
                error=abs(oracle-result['null']['objective']);max_null_error=max(max_null_error,error)
                check(case+str(trial)+arm+' actual shared-base normalized null oracle',error<1e-3)
                check(case+str(trial)+arm+' best-minus-null sign',abs(best['objective']-result['null']['objective']-result['best_physical_minus_null'])<1e-8)
                if not valid:numeric_failures.append(dict(case=case,trial=trial,kind=kind,arm=arm,blocked=[dict(norad=c['norad'],reason=c.get('reason')) for c in candidates if c['status']!='complete'],unqualified=[c['norad'] for c in complete if not c['numerically_qualified']]))
                cavity_changes.append(dict(case=case,trial=trial,arm=arm,removed_curved=len(expectedremoved),removed_predictive=len(expectedpred),parent_legacy_gates_pass=cavity['original_remaining_gates_pass'],radio_mean_shift_RMS_hz=float(np.sqrt(np.mean((conditional['radio_mean_hz']-cat['radio_mean_hz'])**2))),covariance_relative_change=float(np.linalg.norm(conditional['covariance_hz2']-cat['conditional_covariance_hz2'])/np.linalg.norm(cat['conditional_covariance_hz2']))))
                allrows.append(dict(case=case,trial=trial,kind=kind,arm=arm,truth_in_shortlist=truth['generating_index'] in ranked[:8] if kind=='physical' else None,best_is_truth=best['norad']==truth['generating_norad'] if kind=='physical' else None,ordering_qualified=valid,physical_preferred=result['best_physical_minus_null']<0))
    for arm in ('c0','fitted_c'):
        for kind in ('physical','unresolved'):
            rows=[r for r in allrows if r['arm']==arm and r['kind']==kind]
            summaries.append(dict(arm=arm,kind=kind,selected=len(rows),ordering_qualified=sum(r['ordering_qualified'] for r in rows),truth_in_shortlist=sum(r['truth_in_shortlist'] is True for r in rows) if kind=='physical' else None,raw_best_is_truth=sum(r['best_is_truth'] is True for r in rows) if kind=='physical' else None,raw_physical_preferred=sum(r['physical_preferred'] for r in rows)))
    signal.setitimer(signal.ITIMER_REAL,0)
    output=dict(all_passed=True,checks=checks,seconds=time.monotonic()-began,protocol_sha256=sha(NOM/'protocol.json'),RF_seal_sha256=sha(NOM/'RF_seal.json'),source_sha256=sha(__file__),candidate_contexts=candidate_contexts,adaptive_references=adaptive_count,max_coarse_score_error=max_coarse_error,max_generator_closure_error_hz=max_generator_error,max_actual_null_oracle_error=max_null_error,summaries=summaries,ordering_guard_failures=numeric_failures,conditioning_changes=cavity_changes,propagation_calls=0,fits=0,GPS_or_position_errors_read=False)
    (ROOT/'audit/nomination_terminal.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ('checks','conditioning_changes','ordering_guard_failures')}))


if __name__=='__main__':main()
