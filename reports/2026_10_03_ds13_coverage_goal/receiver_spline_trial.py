"""Training-only shared receiver-drift test, plus leave-satellite-out transfer."""
import argparse,json,sys,time
import numpy as np
from benchmark import ROOT,OLD,SESSIONS,ALIAS_HZ,digest
from training_bootstrap import training_view
from receiver_spline import fit,predict,NULL,NODES


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',choices=['A','B'],required=True);args=p.parse_args();started=time.monotonic()
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import load_expanded_scan,SharedPredictionPlan,rf_features,circular_residual,prepare_finite_set_likelihood
    data=load_expanded_scan(SESSIONS[args.scan]);folder=ROOT/'receiver-spline';folder.mkdir(exist_ok=True);target=folder/f'{args.scan}.json'
    if target.exists():raise FileExistsError(target)
    results=[];sources={}
    for fold in range(5):
        up=ROOT/'training-union'/f'fold-{fold}'/f'{args.scan}.json';rp=ROOT/'expanded-training-refit'/f'fold-{fold}'/f'{args.scan}.json'
        dp=ROOT/'refit-replay/heldout-decoding'/f'fold-{fold}'/f'{args.scan}.json'
        union=json.loads(up.read_text());refit=json.loads(rp.read_text());decoded=json.loads(dp.read_text());assert refit['source_sha256']==digest(up)
        assert union['original_test_rows']==refit['original_test_rows']==decoded['original_test_rows']
        assert union['original_train_rows']==refit['original_train_rows'];assert not set(union['original_train_rows'])&set(union['original_test_rows'])
        for path in (up,rp,dp):sources[str(path)]=digest(path)
        views=[]
        for name in ('original_train_rows','original_test_rows'):
            mask=np.zeros(len(data.times),bool);mask[union[name]]=True;views.append(training_view(data,mask))
        d,t=views;prepared=prepare_finite_set_likelihood(t.measured,t.group)
        for arm in ('fitted-c','zero-c'):
            u=union['arms'][arm];r=refit['arms'][arm];indices=np.array([m['satellite_index'] for m in u['chosen_modes']],int)
            lookup={m['catalog_number']:i for i,m in enumerate(u['chosen_modes'])};arrays=[]
            for view in views:
                _,features=rf_features(view.rf,view.receiver,False);pred,vis,_=SharedPredictionPlan(view,indices).predict(np.array(r['parameters']))
                pred=pred.reshape(len(view.times),len(indices))+(features@np.array(r['coefficient']))[:,None];vis=vis.reshape(pred.shape)
                arrays.append((pred,vis,circular_residual(view.measured[:,None],pred,ALIAS_HZ)))
            records=u['training_assignments'];rr=np.array([q['row_index'] for q in records],int);cc=np.array([lookup[q['catalog_number']] for q in records],int)
            yy=arrays[0][2][rr,cc];valid=arrays[0][1][rr,cc]&(abs(yy)<=600);rr=rr[valid];cc=cc[valid];yy=yy[valid]
            params=fit(d.times[rr],d.receiver[rr],yy);correction=predict(params,t.times,t.receiver)
            pred,vis,residual=arrays[1];pd=.8/(13 if args.scan=='A' else 15)
            def score(p):return float(prepared.evaluate(p,vis,sigma_hz=200.,detection_probability=pd,clutter_rate=2.,return_gradient=False,return_precision=False)['total_log_likelihood'])
            baseline=score(pred);assert np.isclose(baseline,r['heldout_log_likelihood'],atol=1e-6,rtol=0)
            new=score(pred+correction[:,None]);byrow={int(row):i for i,row in enumerate(t.original_rows)}
            points=decoded['arms'][arm]['methods']['tracklet']['assignments'];before=[];after=[];transfer=[];cache={}
            for q in points:
                row=byrow[q['row_index']];col=lookup[q['catalog_number']]
                if col not in cache:
                    others=cc!=col;beta=fit(d.times[rr[others]],d.receiver[rr[others]],yy[others])
                    cache[col]=predict(beta,t.times,t.receiver)
                error=float(residual[row,col]);before.append(error);after.append(error-correction[row]);transfer.append(error-cache[col][row])
            rms=lambda x:float(np.sqrt(np.mean(np.square(x))))
            result=dict(fold=fold,arm=arm,training_points=len(rr),heldout_change=new-baseline,heldout_gain_vs_clutter=r['heldout_gain_vs_clutter']+new-baseline,
                identical_test_points=len(points),before_rms_hz=rms(before),shared_rms_hz=rms(after),leave_satellite_out_rms_hz=rms(transfer),
                nodes_s=NODES.tolist(),correction_knots_hz=(params@NULL.T).tolist(),max_abs_test_correction_hz=float(np.max(abs(correction))))
            results.append(result);print(args.scan,json.dumps({k:v for k,v in result.items() if k not in ('nodes_s','correction_knots_hz')}),flush=True)
    target.write_text(json.dumps(dict(scope=__doc__,scan=args.scan,results=results,sources=sources,elapsed_s=time.monotonic()-started,
        settings=dict(knot_spacing_s=30,amplitude_prior_sigma_hz=50,second_difference_prior_sigma_hz=25,noise_sigma_hz=200,robust_iterations=3),
        limitations=['Shared receiver-only additive correction; constant and linear components removed. No per-track or channel correction.',
            'Training memberships selected by existing model; transfer check removes the evaluated satellite from drift fitting only, not all earlier calibration stages.',
            'No fresh associations or discovery; no coverage claim. Fixed settings chosen before these results, not independently validated physical drift priors.']),indent=2))


if __name__=='__main__':main()
