"""Bounded archived-identity inventory and fixed-position conditional replay."""

import copy
import json
from pathlib import Path
import signal
import sys
import time

import numpy as np
from scipy.linalg import solve_triangular
from scipy.special import logsumexp

HERE=Path(__file__).resolve().parent
TRANSFER=Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer')
sys.path.insert(0,str(TRANSFER))
import transfer as t
q=t.q; original=t.original; r=t.r


def write(name,value):r.write_new(HERE/name,value)


def inventory():
    panel=r.read(TRANSFER/'panel.json')['panel'];rows=[];sources={}
    for target in panel:
        case=target['case'];fitpath=r.SOURCE/case/'fit_radio_noise.json'
        fit=r.read(fitpath);sources[str(fitpath)]=r.sha(fitpath)
        parentpath=r.SOURCE/'family_cavity/position'/(case+'.json')
        parent=r.read(parentpath);sources[str(parentpath)]=r.sha(parentpath)
        node=parent['selected']['node'] if parent['accepted'] else parent['baseline_node']
        trackpath=r.SOURCE/case/'tracks.json';tracks=r.read(trackpath);sources[str(trackpath)]=r.sha(trackpath)
        lookup={track['key']:track for track in tracks}
        choices=[]
        for choice in fit['choices']:
            for index,row in enumerate(choice['node']['seed']['rows']):
                if row['component']==target['component']:
                    choices.append(dict(hypothesis=choice['hypothesis'],norad=row['candidate_norad'],
                        candidate_index=row['candidate_index'],alias=choice['node']['aliases'][index],
                        nomination_compatible=row['compatible'],feasible_candidates=row.get('feasible_candidates'),
                        archived_nomination_RMS_hz=row['rms_hz'],archived_nomination_bias_hz=row['bias_hz']))
        others=[]
        for index,row in enumerate(node['seed']['rows']):
            if row['candidate_norad']!=target['candidate_norad'] or row['component']==target['component']:continue
            track=lookup[row['component']]
            others.append(dict(component=track['key'],candidate_index=row['candidate_index'],
                alias=node['aliases'][index],receiver=track['receiver'],channel=track['channel'],
                points=len(track['times']),observation_ids=track['observation_ids'],
                start_s=track['times'][0],end_s=track['times'][-1],
                archived_nomination_compatible=row['compatible']))
        coverage=r.read(target['parent_ledger_path'])['coverage'];sources[target['parent_ledger_path']]=r.sha(target['parent_ledger_path'])
        accepted={arm:[row for row in coverage[arm]['associations'] if row.get('norad') in
            {choice['norad'] for choice in choices}] for arm in t.ARMS}
        cavitypath=r.SOURCE/'family_cavity'/(case+'_nominations.json')
        cavity=r.read(cavitypath);sources[str(cavitypath)]=r.sha(cavitypath)
        rows.append(dict(case=case,target=target,archived_radio_hypotheses=choices,
            unique_archived_candidate_alias_pairs=sorted({(c['norad'],c['alias']) for c in choices}),
            dedicated_cavity_identity_records=sum(f['original_norad']==target['candidate_norad'] for f in cavity['families']),
            other_same_family_raw_sources=others,accepted_same_candidate_owners=accepted,
            other_sources_are_validated_associations=False,
            repeated_same_label_is_independent_support=False,exhaustive_catalogue_competition=False))
    sourcepaths=[Path(__file__),TRANSFER/'transfer.py',t.R2/'scientific/quadrature02.py',
        t.R2/'scientific/adapter.py',r.REPO/'tools/ds23_soft_predictive_identity.py',
        r.REPO/'tools/ds23_orphan_predictive_mixture.py',r.REPO/'tools/ds23_temporal_predictive_recovery.py',
        Path('/srv/bulk/leo/research/algo04-family-predictive-20261023/identity/study.py')]
    sources.update({str(path):r.sha(path) for path in sourcepaths})
    result=dict(rows=rows,input_source_sha256=sources,
        no_GPS_or_error_lookup=True,position_fits=0,new_nomination=False)
    write('inventory.json',result)
    return result


def candidate_context(d,norad):
    j=int(np.flatnonzero(d['scan'].norads==norad)[0]);changed=dict(d)
    if j in d['original_protected']:raise ValueError('candidate has calibrated parent evidence; symmetric cavity required')
    bank,metadata=original.build_modes(d['scan'],[j],[j],'physical')
    changed['target']=dict(d['target'],candidate_index=j,norad=norad,
        phase_mean_s=float(d['all_means'][j]),phase_sd_s=float(d['widths'][j]),target_local_shape_metadata=metadata)
    # linear_geometry's label is only a dummy for constructing shared RADIO
    # columns. The physical mean/modes are supplied by the candidate-only bank.
    changed['target_entry']=dict(d['target_entry'])
    changed['target_sky']=dict(time_s=d['scan'].sky['time_s'],
        position_km=d['scan'].sky['position_km'][[j]],velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
    changed['target_mode_bank']=bank
    changed.pop('phase_rule_cache02',None)
    return changed


def multi_components(d,arm,x,entries):
    """One conditional parent covariance, independent300Hz constant per owner."""
    p=original.build(d,arm,d['arms'][arm]['phase_reference'])
    parent=p.curved_calculate(x) if d['entries'] else p.calculate(x)
    g=p.noise_groups[p.keep];weight=d['powers'][g]*parent['noise_precision'][g]/p.point_noise[p.keep]**2
    train=parent['features'][p.keep];gram=np.diag(parent['coefficient_prior_precision'])+train.T@(train*weight[:,None])
    root=np.linalg.cholesky(gram)
    view,values,sigma,groups,slices=original.linear_geometry(p,entries)
    hw=view.hardware.copy();hw[:,[4,6]]*=10
    ht=np.zeros((len(values),len(gram)));width=p.hardware.shape[1]+p.smooth.shape[1]
    ht[:,:width]=np.column_stack((hw,view.smooth*200))
    ut=solve_triangular(root,ht.T,lower=True).T
    if d['entries']:
        ev,ey,es,eg,_=original.linear_geometry(p,d['entries']);geo=original.geometry_features(ev,x,0.)
        he=geo['features'];raw=ey-ev.q*geo['intercept']-he@parent['coefficient']
        ue=solve_triangular(root,he.T,lower=True).T
        fe=np.column_stack((ue,np.eye(int(eg.max())+1)[eg]*300.))
        ft=np.column_stack((ut,np.zeros((len(ut),fe.shape[1]-len(gram)))))
        white=fe/(es*np.sqrt(2))[:,None];re=np.linalg.cholesky(np.eye(fe.shape[1])+white.T@white)
        mean=solve_triangular(re.T,solve_triangular(re,white.T@(raw/(es*np.sqrt(2))),lower=True),lower=False)
        update=ft@mean;uncertainty=solve_triangular(re,ft.T,lower=True).T
    else:update=np.zeros(len(ut));uncertainty=ut
    noise=sigma*np.sqrt(2)
    cov=np.diag(noise**2)+uncertainty@uncertainty.T+300.**2*(groups[:,None]==groups[None,:])
    changed=dict(d,target_track=dict(times=view.flat_times,rf_hz=11.5e9))
    return dict(d=changed,x=np.asarray(x),raw=values-ht@parent['coefficient']-update,
                covariance=(cov+cov.T)/2,q=view.q,slices=slices,groups=groups,
                parent_coefficients=parent['coefficient'],parent_noise=parent['noise_precision'])


def multi_score(components,count,indices):
    d=components['d'];nodes,logweights=q.phase_nodes(d,count)
    geom=q.phase_geometry(d,components['x'],nodes)
    ix=np.asarray(indices,int);scale=components['q'][ix]
    frequency=geom['frequency_hz'][:,ix]*scale
    shape=geom['shape_columns_hz'][:,ix]*scale[None,:,None]
    cov=components['covariance'][np.ix_(ix,ix)];root=np.linalg.cholesky(cov)
    raw=components['raw'][ix][None]-frequency
    white=solve_triangular(root,raw.T,lower=True).T
    flat=shape.transpose(1,0,2).reshape(len(ix),-1)
    wb=solve_triangular(root,flat,lower=True).reshape(len(ix),len(nodes),3).transpose(1,0,2)
    gram=np.eye(3)[None]+np.einsum('nki,nkj->nij',wb,wb)
    rhs=np.einsum('nki,nk->ni',wb,white)
    coefficient=np.linalg.solve(gram,rhs[...,None])[...,0]
    quadratic=np.sum(white**2,axis=1)-np.sum(rhs*coefficient,axis=1)
    cost=quadratic+np.linalg.slogdet(gram)[1]+2*np.log(np.diag(root)).sum()+len(ix)*np.log(2*np.pi)
    return dict(objective=float(-2*logsumexp(logweights-cost/2)),
        minimum_node_elevation_deg=float(geom['elevation_deg'][:,ix].min()),
        prior_mass=float(np.exp(logsumexp(logweights))))


def run():
    inv=inventory()
    protocol=dict(scope='fixed saved baseline positions/references, both c arms; no position fitting',
        candidate_pool='only explicitly archived radio-hypothesis NORAD/alias pairs, no catalogue expansion',
        prior='equal identity weight, same fresh causal Student/physical-prior construction per identity; no original calibrated phase/mode advantage',
        phase='unchanged conditioned[-15,+15] Student nu3 nonlinear integration at1281,2561 and adaptive for single-source comparison',
        witnesses='0013 four raw sources jointly predictive; common phase/modes/shared parent covariance, independent300Hz constants; leave-one-owner conditional NLL=joint minus other owners',
        witness_validation='none claimed; assigned60108 fit is conditional model consistency only; no target-trained receiver calibration',
        score_tolerance=1e-3,clutter_or_identity_threshold=None,
        maximum_scientific_seconds=300,position_fits=0,GPS_used=False,
        inventory_sha256=r.sha(HERE/'inventory.json'),source_sha256=r.sha(Path(__file__)))
    write('protocol.json',protocol)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('300s scientific cap')));signal.alarm(300)
    comparisons=[];owner_rows=[];tests=[]
    try:
        for item in inv['rows']:
            d=t.load_target(item['target'])
            pool=item['unique_archived_candidate_alias_pairs']
            for arm in t.ARMS:
                x=np.asarray(d['arms'][arm]['endpoint_east_north_km'])
                for norad,alias in pool:
                    try:
                        candidate=candidate_context(d,norad)
                        candidate['target_entry']['alias']=alias
                        p=q.build(candidate,arm,d['arms'][arm]['phase_reference'],t.BRANCHES[1],1281)
                        comp=q.conditional_components(candidate,p,x)
                        first=q.integrate(candidate,comp,1281,True);dense=q.integrate(candidate,comp,2561,True)
                        adaptive=q.adaptive_reference(candidate,comp,True)
                        error=max(abs(first['objective']-dense['objective']),abs(first['objective']-adaptive['objective']))
                        record=dict(case=item['case'],arm=arm,norad=norad,alias=alias,status='complete',
                            objective=first['objective'],denser_objective=dense['objective'],adaptive_objective=adaptive['objective'],
                            score_error=error,numerically_qualified=error<=1e-3,
                            phase_prior={key:value for key,value in q.prior(candidate).items() if key!='distribution'},
                            phase_posterior_mean_s=first['phase_conditional_mean_s'],phase_posterior_sd_s=first['phase_conditional_sd_s'],
                            minimum_elevation_deg=first['minimum_node_elevation_deg'],identity_qualified=False)
                    except Exception as exc:record=dict(case=item['case'],arm=arm,norad=norad,alias=alias,status='blocked',reason=repr(exc),identity_qualified=False)
                    comparisons.append(record)
            if item['case']=='DS24-0013':
                target=item['target'];owners=[dict(component=target['component'],alias=target['alias'],observation_ids=target['observation_ids'])]+item['other_same_family_raw_sources']
                entries=[]
                occupied=set().union(*(set(d['parent_membership'][arm]['accepted_observation_ids']) for arm in t.ARMS))
                for owner in owners:
                    track_index=next(i for i,track in enumerate(d['scan'].tracks) if track['key']==owner['component'])
                    if occupied & set(owner['observation_ids']):raise ValueError('raw witness overlaps accepted parent evidence')
                    entries.append(dict(track_index=track_index,component=owner['component'],candidate_index=target['candidate_index'],
                        alias=owner['alias'],observation_ids=owner['observation_ids'],points=len(owner['observation_ids'])))
                for arm in t.ARMS:
                    x=np.asarray(d['arms'][arm]['endpoint_east_north_km']);components=multi_components(d,arm,x,entries)
                    allidx=np.arange(len(components['raw']));scores={}
                    for count in (1281,2561):
                        scores[count]=dict(joint=multi_score(components,count,allidx),owners=[])
                        for index,sl in enumerate(components['slices']):
                            own=np.arange(sl.start,sl.stop);other=np.setdiff1d(allidx,own)
                            marginal=multi_score(components,count,own);others=multi_score(components,count,other)
                            scores[count]['owners'].append(dict(component=entries[index]['component'],points=len(own),
                                marginal_NLL=marginal['objective'],others_NLL=others['objective'],
                                conditional_NLL=scores[count]['joint']['objective']-others['objective']))
                    p=q.build(d,arm,d['arms'][arm]['phase_reference'],t.BRANCHES[1],1281)
                    single=q.integrate(d,q.conditional_components(d,p,x),1281,True)['objective']
                    equivalence=abs(single-scores[1281]['owners'][0]['marginal_NLL'])
                    tests.append(dict(test='multiowner marginal reproduces original single-source likelihood',arm=arm,error=equivalence,passed=equivalence<=1e-6))
                    owner_rows.append(dict(case=item['case'],arm=arm,owners=entries,scores=scores,
                        maximum_1281_2561_score_difference=max(abs(scores[1281]['joint']['objective']-scores[2561]['joint']['objective']),
                            *(abs(a['conditional_NLL']-b['conditional_NLL']) for a,b in zip(scores[1281]['owners'],scores[2561]['owners']))),
                        conditional_meaning='predict held owner given other raw owners under common assigned60108, no parent receiver/noise update',identity_qualified=False))
        result=dict(status='complete',comparisons=comparisons,owner_challenges=owner_rows,tests=tests,
            seconds=time.monotonic()-began,position_fits=0,GPS_used=False,identity_qualified=False)
    except Exception as exc:
        import traceback
        result=dict(status='failed',error=repr(exc),traceback=traceback.format_exc(),comparisons=comparisons,
            owner_challenges=owner_rows,tests=tests,seconds=time.monotonic()-began,position_fits=0,GPS_used=False)
    finally:signal.alarm(0)
    write('results.json',result)
    write('seal.json',dict(files={name:r.sha(HERE/name) for name in ('review.py','protocol.json','inventory.json','results.json')},
        no_position_fits=True,no_GPS=True))
    print(json.dumps(result,default=r.encode,indent=2))


if __name__=='__main__':run()
