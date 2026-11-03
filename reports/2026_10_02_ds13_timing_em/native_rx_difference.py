"""DS13 replay of the orbit-free, tightly paired receiver-difference diagnostic."""
import csv
import json
import sys
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parent
HELPER=ROOT.parent/'2026_10_02_cross_scan_drift_evidence'
sys.path.insert(0,str(HELPER))
from check_other_scans import digest,select_pairs,design,huber_fit


def models(t,ch,y):
    t,ch,y=map(np.asarray,(t,ch,y))
    if len(t)<6 or np.ptp(t)==0:return {'available':False,'reason':'insufficient temporal support'}
    channels=np.unique(ch);labels=np.minimum(((t-t.min())/np.ptp(t)*5).astype(int),4);result={}
    for order in (0,1,2):
        matrix=design(t,ch,order,channels);coef=huber_fit(matrix,y);error=y-matrix@coef
        held=np.full(len(t),np.nan);folds=[]
        for fold in range(5):
            test=labels==fold
            if not test.any():continue
            train=(~test)&((t<t[test].min()-1)|(t>t[test].max()+1))
            if train.sum()<matrix.shape[1] or np.linalg.matrix_rank(matrix[train])<matrix.shape[1]:continue
            held[test]=y[test]-matrix[test]@huber_fit(matrix[train],y[train]);folds.append(int(test.sum()))
        valid=np.isfinite(held)
        result[str(order)]=dict(channel_intercepts_hz_at_150s=dict(zip(map(str,channels),map(float,coef[:len(channels)]))),
            slope_hz_s_at_150s=float(coef[len(channels)]/150) if order else 0.,
            quadratic_coefficient_hz_s2=float(coef[-1]/150**2) if order==2 else 0.,
            descriptive_median_absolute_error_hz=float(np.median(abs(error))),
            descriptive_p90_absolute_error_hz=float(np.quantile(abs(error),.9)),
            all_selected_rms_hz=float(np.sqrt(np.mean(error**2))),fraction_within_300_hz=float(np.mean(abs(error)<=300)),
            held_count=int(valid.sum()),held_fold_counts=folds,
            five_time_block_held_median_absolute_error_hz=float(np.median(abs(held[valid]))) if valid.any() else None,
            five_time_block_held_p90_absolute_error_hz=float(np.quantile(abs(held[valid]),.9)) if valid.any() else None)
    return result


def summarize_pairs(pairs):
    t=np.array([p['time_s'] for p in pairs]);ch=np.array([p['channel'] for p in pairs])
    y=np.array([p['rx1_minus_rx0_modulo_alias_hz'] for p in pairs])
    strong=np.array([min(p['margin0'],p['margin1'])>=.4 for p in pairs]);bins=[]
    for start in range(0,300,30):
        m=(t>=start)&(t<start+30)
        bins.append(dict(start_s=start,end_s=start+30,pair_count=int(m.sum()),median_rx_difference_hz=float(np.median(y[m])) if m.any() else None))
    medians=[b['median_rx_difference_hz'] for b in bins if b['pair_count']]
    return dict(pair_count=len(pairs),time_range_s=[float(t.min()),float(t.max())],
        absolute_epoch_difference_ns_quantiles=dict(zip(('minimum','median','p90','maximum'),map(float,np.quantile([abs(p['epoch_difference_s'])*1e9 for p in pairs],[0,.5,.9,1])))),
        native_direct_difference_equals_wrapped_fraction=float(np.mean([abs(p['rx1_minus_rx0_raw_hz']-p['rx1_minus_rx0_modulo_alias_hz'])<1e-6 for p in pairs])),
        channel_offset_controlled_models=models(t,ch,y),thirty_second_bin_medians=bins,
        thirty_second_bin_median_range_hz=float(np.ptp(medians)),
        per_channel={str(c):dict(pair_count=int(np.sum(ch==c)),models=models(t[ch==c],ch[ch==c],y[ch==c])) for c in np.unique(ch)},
        strong_margin_at_least_0p4_both=dict(pair_count=int(strong.sum()),models=models(t[strong],ch[strong],y[strong])))


def main():
    source_hashes={str(Path(__file__)):digest(__file__),str(HELPER/'check_other_scans.py'):digest(HELPER/'check_other_scans.py')}
    cases=[];all_pairs=[]
    for label,sid in [('A','scan-fw-911c4e5db9243281'),('B','scan-fw-ffa1cc19d8d7c09f')]:
        directory=ROOT/'scans'/sid
        manifest_path=directory/'bundle.json';array_path=directory/'bundle.npz'
        manifest=json.loads(manifest_path.read_text())
        assert digest(array_path)==manifest['artifacts']['bundle_npz_sha256']
        for p,h in manifest['provenance']['source_hashes'].items():
            assert digest(p)==h
            source_hashes[p]=h
        capture_path=ROOT.parent/'2026_10_02_ds13_from_911c4e5d/local/published'/(sid+'.json')
        capture=json.loads(capture_path.read_text());rate=capture['timing']['sample_rate_hz']
        for p in (manifest_path,array_path,capture_path):source_hashes[str(p)]=digest(p)
        with np.load(array_path,allow_pickle=False) as a:
            arrays={k:a[k] for k in ('times','measured','rf','receiver','channel','group','margin')}
        rows=np.asarray(manifest['family_representatives'])
        metadata=[dict(r,local_probe_key=r['probe_key']) for r in manifest['alias_grouping']['representative_rows']]
        assert np.array_equal(arrays['measured'][rows],[r['tracking_cfo_hz'] for r in metadata])
        assert np.array_equal(arrays['receiver'][rows],[r['local_probe_key'][1] for r in metadata])
        case=dict(scan=label,session_id=sid,sample_rate_hz=rate,cohorts={})
        for name,tolerance in [('epoch_within_1us',1e-6),('epoch_within_100ns',1e-7)]:
            pairs=select_pairs(metadata,rows,arrays,rate,tolerance)
            if len(pairs)<30:raise ValueError('Insufficient pairs for existing diagnostic')
            case['cohorts'][name]=summarize_pairs(pairs)
            all_pairs.extend(dict(scan=label,session_id=sid,cohort=name,**p) for p in pairs)
        cases.append(case)
        print(json.dumps(case),flush=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(14,9),sharex=True)
    for col,case in enumerate(cases):
        pairs=[p for p in all_pairs if p['scan']==case['scan'] and p['cohort']=='epoch_within_100ns']
        t=np.array([p['time_s'] for p in pairs]);ch=np.array([p['channel'] for p in pairs])
        y=np.array([p['rx1_minus_rx0_modulo_alias_hz'] for p in pairs]);center=float(np.median(y))
        strong=np.array([min(p['margin0'],p['margin1'])>=.4 for p in pairs])
        for row,selection in enumerate((np.ones(len(t),bool),strong)):
            ax=axes[row,col]
            for channel in np.unique(ch):
                m=selection&(ch==channel);ax.scatter(t[m],y[m]-center,s=7,alpha=.5,label=f'CH{channel}')
            lo,hi=np.quantile(y[selection]-center,[.02,.98]);ax.set_ylim(lo-100,hi+100)
            outside=int(np.sum(selection&((y-center<lo-100)|(y-center>hi+100))))
            ax.set_title(f"Scan {case['scan']} · {'all' if row==0 else 'both margins ≥0.4'} · {selection.sum()} pairs\nCenter {center:+.1f} Hz; {outside} point(s) outside display")
            ax.set_xlim(0,300);ax.grid(alpha=.2);ax.legend(markerscale=2)
            ax.set_ylabel('RX1−RX0 minus panel median (native Hz)');ax.set_xlabel('Receive time (s)')
    fig.suptitle('DS13 · tightly epoch-matched receiver differences\nSame visit/probe/RF; epochs ≤100 ns apart; no orbit, location or receiver-drift correction')
    fig.text(.5,.012,'Modulo 227.273 kHz; selection uses timing and GLRT margins, not frequency agreement. 2–98% plot limits + 100 Hz; fits/CSV retain every pair.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.035,1,.93))
    out=ROOT/'native-rx-difference';out.mkdir(exist_ok=True)
    fig.savefig(out/'comparison.png',dpi=160)
    with (out/'pairs.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(all_pairs[0]));w.writeheader();w.writerows(all_pairs)
    for p,h in source_hashes.items():assert digest(p)==h
    (out/'receipt.json').write_text(json.dumps(dict(cases=cases,source_sha256=source_hashes,
        scope='Same selection and fixed-100Hz Huber models as cross-scan diagnostic. Native zero residual bins, '
              'one pair per visit/probe, exact RF, choose highest weaker margin independently of CFO. '
              'Separate channel intercepts and common polynomial time terms; five contiguous held-out time blocks '
              'with 1s guard. 100ns primary and 1us sensitivity, plus both margins >=.4 control. '
              'No orbit or location used, no separate RX correction removed. All archived family representatives '
              'used, no final-track or satellite-posterior filter. Timing agreement is not decoded common-signal identity; '
              'differences cancel common transmitter/orbit effects only if same signal. No new RF or IQ read.'),indent=2,allow_nan=False))


if __name__=='__main__':main()
