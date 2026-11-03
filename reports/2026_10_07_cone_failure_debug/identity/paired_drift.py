"""Orbit-free differential RX evidence from raw, epoch-matched pilot candidates."""
import json,csv,importlib.util
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parents[1];PERIOD=1/4.4e-6
def circular(x):return (np.asarray(x)+PERIOD/2)%PERIOD-PERIOD/2

def pairs(source,tolerance_s,selected=None):
    grouped={}
    for p in source.probes:grouped.setdefault((p.visit_index,p.probe_index,p.actual_rf_hz),{})[p.receiver_id]=p
    output=[]
    for (visit,probe,rf),rx in grouped.items():
        if set(rx)!={0,1}:continue
        left,right=rx[0],rx[1];choices=[]
        for a in left.candidates:
            if not a.passed_fractional_margin_gate:continue
            if selected is not None and selected.get((visit,probe,0),(-1,-1))[1]!=a.candidate_rank:continue
            for b in right.candidates:
                if not b.passed_fractional_margin_gate:continue
                if selected is not None and selected.get((visit,probe,1),(-1,-1))[1]!=b.candidate_rank:continue
                dt=((right.valid_start_counter-left.valid_start_counter)+(right.probe_start_ms-left.probe_start_ms)*source.sample_rate_hz//1000+b.integer_epoch_sample-a.integer_epoch_sample+b.fractional_epoch_offset_samples-a.fractional_epoch_offset_samples)/source.sample_rate_hz
                if abs(dt)>tolerance_s:continue
                choices.append((-min(a.fractional_margin,b.fractional_margin),abs(dt),a.candidate_rank,b.candidate_rank,a,b,dt))
        if not choices:continue
        _,_,_,_,a,b,dt=min(choices,key=lambda q:q[:4]);relative=left.valid_start_counter-source.timing.session_start_device_sample_counter+left.probe_start_ms*source.sample_rate_hz//1000+a.integer_epoch_sample
        t=(relative+a.fractional_epoch_offset_samples)/source.sample_rate_hz
        output.append(dict(visit=visit,probe=probe,rf_hz=rf,channel=left.channel,time_s=t,epoch_difference_ns=dt*1e9,rank0=a.candidate_rank,rank1=b.candidate_rank,margin0=a.fractional_margin,margin1=b.fractional_margin,cfo0_hz=a.fractional_tracking_cfo_hz,cfo1_hz=b.fractional_tracking_cfo_hz,difference_hz=float(circular(b.fractional_tracking_cfo_hz-a.fractional_tracking_cfo_hz))))
        if selected is not None:output[-1].update(row0=selected[(visit,probe,0)][0],row1=selected[(visit,probe,1)][0],rx0=0,rx1=1)
    return sorted(output,key=lambda p:p['time_s'])

def huber(x,y):
    beta=np.linalg.lstsq(x,y,rcond=None)[0]
    for _ in range(40):
        residual=y-x@beta;w=np.minimum(1.,100/np.maximum(abs(residual),1e-12));new=np.linalg.lstsq(x*np.sqrt(w[:,None]),y*np.sqrt(w),rcond=None)[0]
        if np.max(abs(new-beta))<1e-7:beta=new;break
        beta=new
    return beta

def models(rows,key):
    t=np.asarray([r['time_s'] for r in rows]);y=np.asarray([r[key] for r in rows]);ch=np.asarray([r['channel'] for r in rows]);center=(t.min()+t.max())/2;scale=(t.max()-t.min())/2;z=(t-center)/scale;intercepts=np.column_stack([ch==c for c in np.unique(ch)]);out={}
    for degree in (1,2):
        x=np.column_stack([intercepts,*[z**d for d in range(1,degree+1)]]);beta=huber(x,y);residual=y-x@beta;fold=np.minimum(4,((t-t.min())/(t.max()-t.min())*5).astype(int));held=[]
        for f in range(5):
            test=fold==f;train=(fold!=f)&((t<t[test].min()-1)|(t>t[test].max()+1))
            if train.sum()<2*x.shape[1]:continue
            b=huber(x[train],y[train]);held.extend((y[test]-x[test]@b).tolist())
        out[str(degree)]=dict(coefficients=beta.tolist(),channel_order=np.unique(ch).tolist(),time_center_s=float(center),time_scale_s=float(scale),quadratic_center_to_endpoint_hz=float(beta[-1]) if degree==2 else None,training_median_abs_error_hz=float(np.median(abs(residual))),training_rms_hz=float(np.sqrt(np.mean(residual**2))),held_timefold_median_abs_error_hz=float(np.median(abs(np.asarray(held)))) if held else None,held_timefold_p90_abs_error_hz=float(np.quantile(abs(np.asarray(held)),.9)) if held else None)
    return out

def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.contracts.digests import canonical_digest
    spec=importlib.util.spec_from_file_location('paired_oracle',REPORTS/'2026_10_07_sigma1_root_cause/oracle.py');oracle=importlib.util.module_from_spec(spec);spec.loader.exec_module(oracle);output=dict(protocol='Same visit/probe/exactRF; passing raw candidates; epoch1us/100ns; maximize weaker margin; no CFO filtering; native-zero bin unavailable in public TrackingCandidate contract',cases={});allrows=[]
    topone=dict(protocol='Exact prepared candidate IDs on both RX; same visit/probe/RF; no CFO threshold; epoch agreement is not decoded identity; native-zero-bin unavailable',cases={})
    for case in ('1939','2139'):
        snap=json.loads((REPORTS/'2026_10_07_recent_filter_review/snapshot.json').read_text());doc=next(c['regional_document'] for c in snap['captures'] if c['session_id']==oracle.CONTROLS.CASES[case]);receipt=json.loads((REPORTS/'2026_10_07_sigma1_cones'/case/'polished.json').read_text());chosen=next(r for r in receipt['selections'] if r['option']=='control' and r['arm']=='fitted-c')
        store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
        try:source=store.load(doc['session_id'])
        finally:store.close()
        assert source.input_manifest_sha256==doc['input_manifest_sha256'];assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256'];prepared=prepare_position_windows(source);obs=prepared.observations
        from leo.application.scanner_trajectory import project_scanner_candidates
        by_id={p.candidate_id:p for p in project_scanner_candidates(source)}
        selected={(p.visit_index,p.probe_index,p.receiver_id):(i,p.candidate_rank) for i,cid in enumerate(prepared.candidate_ids) for p in [by_id[cid]]}
        from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
        cp=RegionalCheckpointStore(Path('/srv/bulk/leo'),doc['session_id'],doc['diagnostics']['checkpoint_binding']);cal=cp.get(canonical_digest(doc['configuration']['run'])+':'+chosen['basin']+':calibration')['result'];center=obs.time_center_s;rx=obs.receiver;ct=obs.times_s-center;design=np.column_stack([rx==0,(rx==0)*ct,rx==1,(rx==1)*ct]);affine=np.linalg.lstsq(design,np.asarray(cal['receiver_baseline_hz'])-np.asarray(cal['correction']['values_hz']),rcond=None)[0];assert np.max(abs(design@affine-(np.asarray(cal['receiver_baseline_hz'])-np.asarray(cal['correction']['values_hz']))))<1e-6
        knots=np.asarray(cal['correction']['knots_hz']);nodes=np.asarray(cal['correction']['nodes_s']);fit=np.asarray(chosen['vector']);record=dict(input_sha256=source.input_manifest_sha256,analysis_sha256=source.analysis_manifest_sha256,sample_rate_hz=source.sample_rate_hz,cohorts={})
        for tol in (1e-6,1e-7):
            rows=pairs(source,tol)
            for r in rows:
                t=r['time_s'];baseline_difference=affine[2]-affine[0]+(affine[3]-affine[1])*(t-center)+np.interp(t,nodes,knots[1]-knots[0]);fitted_difference=fit[4]-fit[2]+(fit[5]-fit[3])*(t-center)
                r.update(case=case,tolerance_ns=tol*1e9,baseline_difference_hz=float(baseline_difference),calibration_residual_hz=float(circular(r['difference_hz']-baseline_difference)),full_fit_residual_hz=float(circular(r['difference_hz']-baseline_difference-fitted_difference)))
            label=str(round(tol*1e9))+'ns';summary=dict(count=len(rows),epoch_abs_ns_quantiles=np.quantile(abs(np.asarray([r['epoch_difference_ns'] for r in rows])),[0,.5,.9,1]).tolist(),time_range_s=[min(r['time_s'] for r in rows),max(r['time_s'] for r in rows)],models={key:models(rows,key) for key in ('difference_hz','calibration_residual_hz','full_fit_residual_hz')},time_bins=[dict(start_s=start,count=sum(start<=r['time_s']<start+30 for r in rows),median_full_residual_hz=float(np.median([r['full_fit_residual_hz'] for r in rows if start<=r['time_s']<start+30])) if any(start<=r['time_s']<start+30 for r in rows) else None) for start in range(0,300,30)])
            record['cohorts'][label]=summary;allrows.extend(rows)
            retained=pairs(source,tol,selected)
            for r in retained:
                r.update(observation_time0_s=float(obs.times_s[r['row0']]),observation_time1_s=float(obs.times_s[r['row1']]),support_centroid_difference_s=float(obs.times_s[r['row1']]-obs.times_s[r['row0']]))
                t=r['time_s'];bd=affine[2]-affine[0]+(affine[3]-affine[1])*(t-center)+np.interp(t,nodes,knots[1]-knots[0]);fd=fit[4]-fit[2]+(fit[5]-fit[3])*(t-center)
                r.update(baseline_difference_hz=float(bd),selected_rx_nuisance_difference_hz=float(fd),full_fit_residual_hz=float(circular(r['difference_hz']-bd-fd)),calibration_residual_hz=float(circular(r['difference_hz']-bd)))
            topone['cases'].setdefault(case,{})[label]=dict(count=len(retained),time_range_s=[min(r['time_s'] for r in retained),max(r['time_s'] for r in retained)] if retained else None,rows=retained,models={key:models(retained,key) for key in ('difference_hz','calibration_residual_hz','full_fit_residual_hz')} if len(retained)>20 else {})
            (HERE/'paired_topone_timing.json').write_text(json.dumps(topone,indent=2))
        output['cases'][case]=record;(HERE/'paired_results.json').write_text(json.dumps(output,indent=2));print(case,json.dumps(record['cohorts']['100ns']),flush=True)
    with (HERE/'paired_points.csv').open('w') as f:writer=csv.DictWriter(f,fieldnames=allrows[0].keys());writer.writeheader();writer.writerows(allrows)

if __name__=='__main__':main()
