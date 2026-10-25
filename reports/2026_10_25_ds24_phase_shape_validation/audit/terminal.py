"""Independent sealed-result/gate/contrast audit, using saved numbers only."""
import json
import time
from pathlib import Path
import numpy as np
from audit_math import factorial
from preflight import HERE,S,OLD,PREV,read,sha


def main():
    began=time.monotonic(); checks=[]; failed_tracks=[]; independent=[]
    def check(name,passed,**data):checks.append(dict(test=name,passed=bool(passed),**data))
    protocol=read(S/'protocol.json'); seal=read(S/'scientific_seal.json')
    for sealname in ('scientific_seal.json','report_data_seal.json'):
        for path,expected in read(S/sealname)['files'].items():check('sealed file unchanged',sha(path)==expected,path=path)
    check('exact preflight protocol binding',read(HERE/'synthetic_preflight.json')['protocol_sha256']==sha(S/'protocol.json'))
    execution=read(S/'execution.json'); replay=read(S/'gate_replay.json'); summary=read(S/'summary.json')
    check('exact32 attempted/terminal jobs',execution['attempted_fits']==32 and len(execution['rows'])==32)
    check('zero runtime failures',execution['completed']==32 and execution['failures']==0)
    check('global600s cap',replay['within_original_deadline'] and replay['wall_seconds_since_first_preparation']<=600.)
    lookup={(r['case'],r['site_index'],r['variant'],r['intervention'],r['arm']):r for r in execution['rows']}
    check('32 distinct exact jobs',len(lookup)==32)
    paired={}
    for key,row in lookup.items():
        case,site,variant,intervention,arm=key
        stored=read(S/'fits'/case/f'site{site}'/variant/intervention/arm/'result.json')
        check('execution equals saved result',stored==row)
        vector=np.asarray(row['endpoint_east_north_km'])-np.asarray(protocol['sites'][site])
        check('saved error norm/vector',np.max(abs(vector-row['error_vector_east_north_km']))<1e-12 and
              abs(np.linalg.norm(vector)-row['synthetic_position_error_km'])<1e-12)
        phase=np.max(abs(np.asarray(row['state']['phases'])))
        gamma=row['fixed_objective_diagnostics']['endpoint_at_final_reference']['final_log_precision_change']
        trackpass=bool(row['gates']['tracks']) and all(g['compatible'] for g in row['gates']['tracks']) and all(
            g['compatible'] for g in row['linear_gates'])
        region=bool(np.asarray(row['endpoint_east_north_km']).shape==(2,) and np.isfinite(vector).all() and
                    np.max(abs(np.asarray(row['endpoint_east_north_km'])))<=12.500001)
        qualified=bool(trackpass and region and phase<=15.000001 and row['final_phase_change_s']<=.01 and gamma<=1e-5)
        check('independent final qualification',qualified==row['qualification']['passed'])
        check('raw absolute phase bound',phase<=15.000001)
        check('phase/Gamma convergence',row['final_phase_change_s']<=.01 and np.isfinite(gamma) and gamma<=1e-5)
        check('no known-phase inference',np.all(np.asarray(row['history'][0]['parent_phase_reference'])==0.) and len(row['history'])==5)
        paired.setdefault(key[:-1],{})[arm]=row['observations_sha256']
        for name,diag in row['fixed_objective_diagnostics'].items():
            if 'parent_decomposition_closure' in diag:check('objective decomposition closure',abs(diag['parent_decomposition_closure'])<1e-7)
        check('saved known-forward closure',row['fixed_objective_diagnostics']['known_forward_closure'][
              'maximum_known_forward_mean_identity_error_hz']<=1e-7)
    check('16 matched c-arm observation pairs',len(paired)==16 and all(r['c0']==r['fitted_c'] for r in paired.values()))
    # Recompute original residual predicates from the independently replayed raw
    # statistics, without repeating any geometry/propagation evaluation.
    for gate in replay['rows']:
        key=tuple(gate[k] for k in ('case','site_index','variant','intervention','arm'))
        row=lookup[key]; saved={g['component']:g for g in row['gates']['tracks']}
        supported=set(read(S/'instances'/key[0]/f'site{key[1]}'/key[2]/key[3]/'truth.json')['supported_shape_families'])
        tracks=[]
        for g in gate['curved']:
            flags={}
            for prefix,stats in [('profile_',g['profile_noise']),('conditional_',g['conditional_noise'])]:
                for name,limit in dict(mean_z=3.,slope_z=3.,quadratic_bic_gain=10.,maximum_step_z=4.,lag1_acf=4/np.sqrt(g['points'])).items():
                    flags[prefix+name]=bool((abs(stats[name]) if name=='lag1_acf' else stats[name])<=limit)
            flags.update(profile_RMS=g['profile_RMS_hz']<=450.,profile_bias=abs(g['profile_bias_hz'])<=3000.,
                         conditional_RMS=g['conditional_RMS_hz']<=450.,
                         alias=saved[g['component']]['aliases_changed']==0,visibility=g['checks']['visibility'])
            check('raw curved predicates',all(flags[name]==g['checks'][name] for name in flags))
            tracks.append(dict(g=g,passed=all(flags.values())))
        changed=True
        while changed:
            owners={}
            for t in tracks:
                if t['passed']:
                    g=t['g'];owners.setdefault(g['candidate_index'],set()).add((g['receiver'],g['channel']))
            changed=False
            for t in tracks:
                g=t['g']
                if t['passed'] and g['candidate_index'] in supported and len(owners[g['candidate_index']])<2:
                    t['passed']=False;changed=True
        for t in tracks:
            g=t['g'];check('original owner cascade/saved gate',t['passed']==g['after_support_passed']==saved[g['component']]['compatible'])
            if not t['passed']:failed_tracks.append(dict(case=key[0],site=key[1],variant=key[2],intervention=key[3],arm=key[4],
                component=g['component'],points=g['points'],predicates=g['failed_predicates'],profile_noise=g['profile_noise'],conditional_noise=g['conditional_noise']))
        for g in gate['predictive']:
            flags={}
            for name,limit in dict(mean_z=3.,slope_z=3.,quadratic_bic_gain=10.,maximum_step_z=4.,lag1_acf=4/np.sqrt(g['points'])).items():
                flags['predictive_'+name]=bool((abs(g['noise'][name]) if name=='lag1_acf' else g['noise'][name])<=limit)
            flags.update(RMS=g['RMS_hz']<=450,bias=abs(g['bias_hz'])<=3000,alias=g['checks']['alias'],visibility=g['checks']['visibility'])
            check('raw predictive predicates',all(flags[k]==g['checks'][k] for k in flags))
        check('saved endpoint objective replay',abs(gate['objective_replay_difference'])<1e-7)
    savedfact=read(S/'factorial_contrasts.json')['factorials']
    aggregates={}
    for fact in savedfact:
        case,site,variant,arm=(fact[k] for k in ('case','site_index','variant','arm'))
        values={}; source={}
        for cell in ('11','10','01','00'):
            binding=fact['source_bindings'][cell]; path=Path(binding['source_path']); result=read(path)
            check('four-cell source binding',sha(path)==binding['source_sha256'])
            vector=np.asarray(result['endpoint_east_north_km'])-np.asarray(protocol['sites'][site]); values[cell]=vector;source[cell]=result
            aggregates.setdefault((cell,arm),[]).append(vector)
        actual=factorial(*(values[c] for c in ('11','10','01','00')))
        check('vector interaction',np.max(abs(np.asarray(actual['vector_interaction_km'])-fact['contrasts']['vector']['interaction']))<1e-12)
        check('scalar interaction',abs(actual['scalar_error_interaction_km']-fact['contrasts']['error']['interaction'])<1e-12)
        check('squared-error interaction',abs(actual['squared_error_interaction_km2']-fact['contrasts']['squared_error']['interaction'])<1e-12)
        check('independent squared interaction identity',actual['squared_identity_error']<1e-12)
        for metric,cellvalues in [('vector',values),('error',{c:np.linalg.norm(v) for c,v in values.items()}),
                                 ('squared_error',{c:float(v@v) for c,v in values.items()})]:
            g=cellvalues
            direct=dict(phase_removal_shape_on=g['01']-g['11'],phase_removal_shape_off=g['00']-g['10'],
                shape_removal_phase_on=g['10']-g['11'],shape_removal_phase_off=g['00']-g['01'],
                marginal_phase_removal=(g['01']+g['00']-g['11']-g['10'])/2,
                marginal_shape_removal=(g['10']+g['00']-g['11']-g['01'])/2)
            for name,value in direct.items():check('predeclared paired contrast',np.max(abs(np.asarray(value)-fact['contrasts'][metric][name]))<1e-12)
        independent.append(dict(case=case,site=site,variant=variant,arm=arm,
                               all_cells_qualified=all(source[c]['qualification']['passed'] for c in source),**actual))
    independent_summaries=[]
    for (cell,arm),vectors in aggregates.items():
        vectors=np.asarray(vectors);errors=np.linalg.norm(vectors,axis=1)
        actual=dict(cell=cell,arm=arm,mean_error_km=float(errors.mean()),median_error_km=float(np.median(errors)),
                    maximum_error_km=float(errors.max()),mean_squared_error_km2=float(np.mean(errors**2)),mean_vector_km=vectors.mean(axis=0).tolist())
        given=next(r for r in summary['summaries'] if r['cell']==cell and r['arm']==arm)
        for name in ('mean_error_km','median_error_km','maximum_error_km','mean_squared_error_km2'):
            check('independent all-attempt summary',abs(actual[name]-given[name])<1e-12)
        check('independent mean error vector',np.max(abs(vectors.mean(axis=0)-given['mean_error_vector_km']))<1e-12)
        independent_summaries.append(actual)
    qualified=sum(r['qualification']['passed'] for r in execution['rows'])
    check('qualification denominator retained',qualified==summary['new_qualified_fits']==30 and len(failed_tracks)==2 and len(savedfact)==16)
    output=dict(all_passed=all(c['passed'] for c in checks),checks=checks,protocol_sha256=sha(S/'protocol.json'),
        scientific_seal_sha256=sha(S/'scientific_seal.json'),report_data_seal_sha256=sha(S/'report_data_seal.json'),
        audited_new_fits=32,reused_fits=32,qualified_new_fits=qualified,complete_four_cell_contrasts=len(independent),
        independent_interactions=independent,independent_cell_summaries=independent_summaries,failed_tracks=failed_tracks,
        original_deadline_met=replay['within_original_deadline'],wall_seconds_through_fixed_replay=replay['wall_seconds_since_first_preparation'],
        audit_seconds=time.monotonic()-began,position_fits=0,orbit_propagations=0,real_GPS_used=False,
        scope='raw saved numeric threshold/cascade replay; visibility decisions bound to producer fixed replay, no new propagation')
    with (HERE/'synthetic_terminal_audit.json').open('x') as stream:json.dump(output,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(all_passed=output['all_passed'],checks=len(checks),qualified=qualified,
        summaries=independent_summaries,failed_tracks=failed_tracks),indent=2))
    if not output['all_passed']:raise SystemExit(1)


if __name__=='__main__':main()
