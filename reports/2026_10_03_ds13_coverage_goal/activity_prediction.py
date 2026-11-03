"""Strict held-out likelihood with training-only receiver/channel activity gates.

Fixed 17 s support radius = 10 s held-out block + two 1 s embargo margins
+ 5 s permitted support gap. This is a bounded extrapolation diagnostic,
not a calibrated activity probability or a new defensible-coverage result.
"""
import argparse,csv,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,digest,split_masks
from training_bootstrap import training_view
from summarize_training_union import validate_partition
from soft_activity import mixture_log_likelihood


def activity_mask(train_times,train_rx,train_channel,assignments,numbers,
                  query_times,query_rx,query_channel,radius=17.):
    if radius<0:raise ValueError('Negative support radius')
    result=np.zeros((len(query_times),len(numbers)),bool)
    lookup={int(n):c for c,n in enumerate(numbers)};support={}
    for record in assignments:
        row=int(record['row_index']);number=int(record['catalog_number'])
        if not 0<=row<len(train_times) or number not in lookup:raise ValueError('Invalid training assignment')
        key=(lookup[number],int(train_rx[row]),int(train_channel[row]))
        support.setdefault(key,[]).append(float(train_times[row]))
    for (col,rx,ch),times in support.items():
        times=np.unique(times);rr=np.flatnonzero((query_rx==rx)&(query_channel==ch))
        if not len(rr):continue
        t=query_times[rr];j=np.searchsorted(times,t)
        left=times[np.clip(j-1,0,len(times)-1)];right=times[np.clip(j,0,len(times)-1)]
        result[rr,col]=np.minimum(abs(t-left),abs(t-right))<=radius
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',choices=['A','B'],required=True);p.add_argument('--soft',action='store_true');args=p.parse_args()
    started=time.monotonic();sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,rf_features,prepare_finite_set_likelihood
    data=load_expanded_scan(SESSIONS[args.scan]);folder=ROOT/('soft-activity-prediction' if args.soft else 'activity-prediction');folder.mkdir(exist_ok=True)
    target=folder/f'{args.scan}.json'
    if target.exists():raise FileExistsError(target)
    with np.load(ROOT/'frozen'/f'{args.scan}-observations.npz') as a:
        times=a['times_s'].copy();groups=a['group'].copy();canonical=np.zeros(len(times),bool);canonical[a['canonical_rows']]=True
    records=[];receipts=[];sources={}
    for fold in range(5):
        source=ROOT/'training-union'/f'fold-{fold}'/f'{args.scan}.json';r=json.loads(source.read_text());receipts.append(r);sources[str(source)]=digest(source)
        train,test=split_masks(times,groups,fold);d=training_view(data,canonical&train);t=training_view(data,canonical&test)
        np.testing.assert_array_equal(d.original_rows,r['original_train_rows']);np.testing.assert_array_equal(t.original_rows,r['original_test_rows'])
        prepared=prepare_finite_set_likelihood(t.measured,t.group);_,features=rf_features(t.rf,t.receiver,False)
        for arm in ('fitted-c','zero-c'):
            a=r['arms'][arm];chosen=a['chosen_modes'];indices=np.array([m['satellite_index'] for m in chosen],int);numbers=np.array([m['catalog_number'] for m in chosen])
            pred,vis,_=SharedPredictionPlan(t,indices).predict(np.array(a['parameters']))
            pred=pred.reshape(len(t.times),len(indices))+(features@np.array(a['coefficient']))[:,None];vis=vis.reshape(pred.shape)
            mask=activity_mask(d.times,d.receiver,d.channel,a['training_assignments'],numbers,t.times,t.receiver,t.channel)
            def score(v):return prepared.evaluate(pred,v,sigma_hz=200.,detection_probability=.8/(13 if args.scan=='A' else 15),clutter_rate=2.,return_gradient=False,return_precision=False)
            global_score=score(vis);active_score=score(vis&mask)
            global_ll=float(global_score['total_log_likelihood']);assert np.isclose(global_ll,a['heldout_global_log_likelihood'],atol=1e-6,rtol=0)
            active_ll=float(active_score['total_log_likelihood'])
            # Diagnostic only: existing test labels never influence the mask.
            oldpath=ROOT/'heldout-decoding'/f'fold-{fold}'/f'{args.scan}.json';old=json.loads(oldpath.read_text());sources[str(oldpath)]=digest(oldpath)
            byrow={int(row):i for i,row in enumerate(t.original_rows)};bycatalog={int(n):i for i,n in enumerate(numbers)}
            admitted={}
            for method,v in old['arms'][arm]['methods'].items():
                pairs=v['assignments'];inside=sum(bool(mask[byrow[q['row_index']],bycatalog[q['catalog_number']]]) for q in pairs)
                admitted[method]=dict(existing_coherent_test_assignments=len(pairs),inside_training_activity=inside,outside_training_activity=len(pairs)-inside)
            record=dict(scan=args.scan,fold=fold,arm=arm,test_rows=len(t.times),selected_catalogs=len(indices),
                global_gain_vs_clutter=a['heldout_gain_vs_clutter'],activity_gain_vs_clutter=a['heldout_gain_vs_clutter']+active_ll-global_ll,
                activity_minus_global=active_ll-global_ll,visible_edges=int(vis.sum()),activity_visible_edges=int((vis&mask).sum()),
                existing_decoder_support=admitted)
            if args.soft:
                local=np.array(active_score['log_likelihood']);glob=np.array(global_score['log_likelihood'])
                mixed=mixture_log_likelihood(local,glob,.1);mixed_ll=float(mixed.sum())
                assert np.isclose(local.sum(),active_ll,atol=1e-6,rtol=0)
                assert np.all(mixed>=glob+np.log(.1)-1e-9)
                record.update(soft_gain_vs_clutter=a['heldout_gain_vs_clutter']+mixed_ll-global_ll,
                    soft_minus_global=mixed_ll-global_ll,soft_minus_hard=mixed_ll-active_ll,
                    groups_preferring_global=int((glob>local).sum()),test_groups=len(glob))
            records.append(record);print(json.dumps(record),flush=True)
    validate_partition(receipts,np.flatnonzero(canonical));summary={}
    for arm in ('fitted-c','zero-c'):
        rr=[r for r in records if r['arm']==arm]
        summary[arm]={key:sum(r[key] for r in rr) for key in ('global_gain_vs_clutter','activity_gain_vs_clutter','activity_minus_global')}
        summary[arm]['positive_activity_folds']=sum(r['activity_gain_vs_clutter']>0 for r in rr)
        if args.soft:
            summary[arm].update({key:sum(r[key] for r in rr) for key in ('soft_gain_vs_clutter','soft_minus_global','soft_minus_hard','groups_preferring_global','test_groups')})
            summary[arm]['soft_improves_global_folds']=sum(r['soft_minus_global']>0 for r in rr)
            summary[arm]['soft_improves_hard_folds']=sum(r['soft_minus_hard']>0 for r in rr)
        summary[arm]['existing_decoder_support']={m:{key:sum(r['existing_decoder_support'][m][key] for r in rr) for key in ('existing_coherent_test_assignments','inside_training_activity','outside_training_activity')} for m in ('activity','history','tracklet')}
    sources[str(ROOT/'activity_prediction.py')]=digest(ROOT/'activity_prediction.py')
    if args.soft:sources[str(ROOT/'soft_activity.py')]=digest(ROOT/'soft_activity.py')
    target.write_text(json.dumps(dict(scope=__doc__,support_radius_s=17,global_mixture_weight=.1 if args.soft else None,records=records,summary=summary,sources=sources,elapsed_s=time.monotonic()-started,
        limitations=['Predeclared radius is a heuristic, not a learned probabilistic transition model.','Existing assignments are unchanged; no new peak coverage is claimed.',
            'Soft variant mixes normalized conditional-positive set likelihoods per probe with fixed global weight 0.1. This is group-level availability uncertainty, not independent satellite-state inference.',
            'Support comes from the existing training tracklet selector; comparison is conditional on that selection.', 'Source calibration convergence and identity/negative-control caveats remain.']),indent=2))
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
