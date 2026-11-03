"""Frozen-track diagnostic: how much trend can one native-Hz RX slope remove?"""
import json
from pathlib import Path

import numpy as np

from plot_all_glrt_doppler_overlay import load_archived_session, file_digest, serializable
from residual_trend_audit import CARRIER, rms

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'later-tle-timing-aligned-v2/receipt.json'
OUTPUT=ROOT/'receiver-linear-recovery'
MODELS=('receiver_offset','receiver_line','track_offsets','track_offsets_shared_line','track_lines')


def design(times,ids,model,levels=None):
    levels=np.unique(ids) if levels is None else levels
    x=(np.asarray(times)-150.)/100.
    constants=np.column_stack([ids==s for s in levels])
    if model=='receiver_offset':return np.ones((len(times),1))
    if model=='receiver_line':return np.column_stack([np.ones(len(times)),x])
    if model=='track_offsets':return constants
    if model=='track_offsets_shared_line':return np.column_stack([constants,x])
    if model=='track_lines':return np.column_stack([constants,constants*x[:,None]])
    raise ValueError(model)


def solve(matrix,y,ids,train=None,balanced=False):
    train=np.ones(len(y),bool) if train is None else train
    w=np.ones(np.sum(train))
    if balanced:
        for s in np.unique(ids[train]):
            mask=ids[train]==s;w[mask]=1./mask.sum()
    a=matrix[train]*np.sqrt(w[:,None]);b=y[train]*np.sqrt(w)
    coefficient,_,rank,_=np.linalg.lstsq(a,b,rcond=None)
    if rank!=matrix.shape[1]:return None,None
    return coefficient,matrix@coefficient


def blocked_folds(times,ids):
    labels=np.zeros(len(times),int)
    for s in np.unique(ids):
        m=ids==s;t=times[m]
        labels[m]=np.minimum(((t-t.min())/(t.max()-t.min())*5).astype(int),4)
    for k in range(5):
        test=labels==k;train=~test
        for s in np.unique(ids):
            held=test&(ids==s)
            if held.any():
                train&=~((ids==s)&(times>=times[held].min()-1)&(times<=times[held].max()+1))
        yield train,test


def run():
    receipt=json.loads(SOURCE.read_text());results=[];inputs={str(SOURCE):file_digest(SOURCE)}
    for scan in receipt['scans']:
        label,session=scan['scan'],scan['session']
        archive,_,archive_path,archive_receipt=load_archived_session(session)
        inputs[str(archive_path)]=file_digest(archive_path)
        inputs[str(archive_receipt)]=file_digest(archive_receipt)
        for rx in (0,1):
            tracks=[r for r in receipt['tracks'] if r['scan']==label and r['receiver']==rx]
            t=np.concatenate([r['time_s'] for r in tracks])
            ids=np.concatenate([np.full(len(r['rows']),r['catalog_number']) for r in tracks])
            rf=np.concatenate([archive['rf_hz'][r['rows']] for r in tracks])
            factor=CARRIER/rf
            normalized=np.concatenate([r['later_residual_hz'] for r in tracks])
            y=normalized/factor
            fitted=[]
            for model in MODELS:
                a=design(t,ids,model)
                for balanced in (False,True):
                    coef,pred=solve(a,y,ids,balanced=balanced)
                    errors=np.full(len(y),np.nan)
                    fold_info=[]
                    for train,test in blocked_folds(t,ids):
                        co,pr=solve(a,y,ids,train,balanced)
                        if co is None:continue
                        errors[test]=(y[test]-pr[test])*factor[test]
                        fold_info.append({'test_count':int(test.sum()),'train_count':int(train.sum()),
                                          'rms_hz':rms(errors[test])})
                    slope=float(coef[-1]/100) if model in ('receiver_line','track_offsets_shared_line') else None
                    per=[]
                    for s in np.unique(ids):
                        m=ids==s
                        per.append({'catalog_number':int(s),'count':int(m.sum()),'baseline_rms_hz':rms(normalized[m]),
                                    'corrected_rms_hz':rms((y-pred)[m]*factor[m]),
                                    'cv_rms_hz':rms(errors[m]) if np.isfinite(errors[m]).all() else None})
                    fitted.append({'model':model,'weighting':'equal_satellite' if balanced else 'equal_point',
                                   'coefficients':coef,'delta_slope_native_hz_s':slope,
                                   'corrected_rms_hz':rms((y-pred)*factor),
                                   'cv_rms_hz':rms(errors) if np.isfinite(errors).all() else None,
                                   'per_track':per,'folds':fold_info})
            loso=[]
            for s in np.unique(ids):
                train=ids!=s;test=~train
                for balanced in (False,True):
                    matrix=design(t[train],ids[train],'track_offsets_shared_line')
                    coef,_=solve(matrix,y[train],ids[train],balanced=balanced)
                    slope=coef[-1]/100
                    # Target mean is removed ONLY for a conditional shape score,
                    # not claimed as an independently predicted target intercept.
                    yn=y[test];before=(yn-yn.mean())*factor[test]
                    corrected=yn-slope*(t[test]-150)
                    after=(corrected-corrected.mean())*factor[test]
                    peer=np.min(np.abs(t[test,None]-t[None,train]),axis=1)<=2.
                    loso.append({'catalog_number':int(s),'weighting':'equal_satellite' if balanced else 'equal_point',
                                 'held_count':int(test.sum()),'delta_slope_native_hz_s':float(slope),
                                 'baseline_centered_rms_hz':rms(before),'corrected_centered_rms_hz':rms(after),
                                 'same_time_peer_count':int(peer.sum()),
                                 'peer_supported_before_rms_hz':rms(before[peer]) if peer.any() else None,
                                 'peer_supported_after_rms_hz':rms(after[peer]) if peer.any() else None})
            track_slopes=[]
            for r in tracks:
                s=r['catalog_number'];m=ids==s
                co,_=solve(design(t[m],ids[m],'receiver_line'),y[m],ids[m])
                track_slopes.append({'catalog_number':s,'count':int(m.sum()),'duration_s':float(np.ptp(t[m])),
                                     'residual_slope_native_hz_s':float(co[1]/100)})
            oracle=np.sqrt(sum(len(r['rows'])*r['later_stats']['line_rms_hz']**2 for r in tracks)/len(y))
            result={'scan':label,'session':session,'receiver':rx,'point_count':len(y),'track_count':len(tracks),
                    'existing_slope_native_hz_s':scan['later_fit']['parameters'][3+2*rx],
                    'baseline_rms_hz':rms(normalized),'independent_normalized_track_lines_rms_hz':float(oracle),
                    'models':fitted,'leave_satellite_out':loso,'track_slopes':track_slopes}
            results.append(result)
    OUTPUT.mkdir(exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(12,8))
    for ax,r in zip(axes.flat,results,strict=True):
        baseline=r['baseline_rms_hz'];oracle=r['independent_normalized_track_lines_rms_hz']
        def model(name):return next(m for m in r['models'] if m['model']==name and m['weighting']=='equal_point')
        shared=model('receiver_line');conditional=model('track_offsets_shared_line')
        values=[baseline,shared['corrected_rms_hz'],conditional['corrected_rms_hz'],oracle]
        ax.barh(range(4),values,color=['.6','#0072B2','#E69F00','#009E73'])
        ax.set_yticks(range(4),['Current fit','One RX offset + slope','Track offsets + one RX slope','Separate line per track'])
        for i,v in enumerate(values):ax.text(v+1,i,f'{v:.1f}',va='center')
        ax.set_xlim(0,max(values)*1.18);ax.invert_yaxis();ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
        ax.set_title(f"Scan {r['scan']} · RX{r['receiver']} · {r['track_count']} tracks")
        ax.set_xlabel('RMS (Hz, normalized to 11.085 GHz)')
    fig.suptitle('How much can one receiver-wide linear correction recover?',fontsize=15)
    fig.text(.5,.015,'Identical final points; native-Hz additive corrections. Bars show in-sample RMS, not validation.\n'
             'Orange allows extra per-track offsets; green is the per-track linear-fit benchmark, not a shared receiver model.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.075,1,.95),h_pad=2.)
    fig.savefig(OUTPUT/'rms-comparison.png',dpi=170);fig.savefig(OUTPUT/'rms-comparison.svg');plt.close(fig)
    result={'source_hashes':{**inputs,str(Path(__file__)):file_digest(__file__)},'receivers':results,
            'scope':'Frozen final selected rows and TLE/timing/RF nuisance. Fit additive native-Hz corrections; report normalized Hz RMS. No production/orbit fit changed. Equal point vs equal total satellite weight explicitly tested.',
            'validation':'Five within-track contiguous time blocks with 1s purge, refit on training only. Leave-satellite-out scores remove the held satellite native mean and therefore test shape only, not absolute prediction. Cohort is baseline selected, not independent validation.',
            'outputs':{str(p):file_digest(p) for p in OUTPUT.iterdir()}}
    (OUTPUT/'receipt.json').write_text(json.dumps(serializable(result),indent=2,allow_nan=False)+'\n')
    for r in results:
        print(r['scan'],r['receiver'],'base',r['baseline_rms_hz'],'oracle',r['independent_normalized_track_lines_rms_hz'])
        for m in r['models']:
            print(m['model'],m['weighting'],'delta',m['delta_slope_native_hz_s'],'RMS',m['corrected_rms_hz'],'CV',m['cv_rms_hz'])
        print('LOSO',[(s['catalog_number'],round(s['baseline_centered_rms_hz'],1),round(s['corrected_centered_rms_hz'],1)) for s in r['leave_satellite_out'] if s['weighting']=='equal_point'])


if __name__=='__main__':run()
