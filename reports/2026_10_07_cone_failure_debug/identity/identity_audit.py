"""Read-only candidate lineage and conditional satellite-confusion audit."""
import csv,json,importlib.util
from dataclasses import replace
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent;REPORTS=HERE.parents[1]
def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.regional_position_inputs import prepare_position_windows
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.analysis.regional_position_score import PositionObjective,predict_orbits,circular,ALIAS_HZ
    from leo.contracts.regional_position import PositionScore
    oracle=load_module('identity_oracle',REPORTS/'2026_10_07_sigma1_root_cause/oracle.py');output=dict(alias_period_hz=ALIAS_HZ,cases={})
    for case,targets in [('1939',(61946,58947)),('2139',(48396,67076))]:
        doc,old,obs,prior,bank,cp,prefix=oracle.load(case);control=json.loads((REPORTS/'2026_10_07_sigma1_cones'/case/'polished.json').read_text());chosen=next(r for r in control['selections'] if r['option']=='control' and r['arm']=='fitted-c');basin=chosen['basin'];a=cp.get(prefix+':'+basin+':association')['result'];c=cp.get(prefix+':'+basin+':calibration')['result'];sub=bank.select(a['selected_indices']);obj=PositionObjective(obs,sub,prior,replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.),receiver_baseline_hz=np.asarray(c['receiver_baseline_hz']));v=np.asarray(chosen['vector']);value,_,terms=obj.evaluate(v);assert abs(value-chosen['objective'])<1e-6
        store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
        try:source=store.load(doc['session_id'])
        finally:store.close()
        assert source.input_manifest_sha256==doc['input_manifest_sha256'];assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256'];prepared=prepare_position_windows(source);assert prepared.observations.window_ids==obs.window_ids
        points=project_scanner_candidates(source);groups=defaultdict(list)
        for p in points:groups[p.source_group_id].append(p)
        by_id={p.candidate_id:p for p in points};owners=[by_id[id] for id in prepared.candidate_ids]
        shifts=v[7]+obj.basis@v[8:];prediction,visible,_,_=predict_orbits(sub,obs,prior,v[:2],shifts,derivatives=False);prediction+=(obj.design@v[2:7]+obj.baseline)[:,None];resp=terms.responsibilities;hard=resp.argmax(axis=1);mass=resp.sum(axis=1);hard=np.where(mass>=.5,hard,-1)
        record=dict(session_id=doc['session_id'],basin=basin,objective_repriced=value,windows=len(obs.window_ids),passing_candidate_count=len(points),bootstrap_tracks=[dict(rx=int(obs.receiver[rows[0]]),channel=int(obs.channel[rows[0]]),windows=len(rows),time_range_s=[float(obs.times_s[list(rows)].min()),float(obs.times_s[list(rows)].max())]) for rows in prepared.bootstrap_tracks],targets={});rows_out=[]
        for target in targets:
            js=np.flatnonzero(sub.numbers==target)
            if not len(js):record['targets'][str(target)]={'present_in_selected_bank':False};continue
            j=int(js[0]);w=resp[:,j];chosen_rows=hard==j;active=w>=.1;blocks={}
            masks={**{f'rx{rx}-ch{ch}':(obs.receiver==rx)&(obs.channel==ch) for rx in (0,1) for ch in np.unique(obs.channel)},**{f'time-{start}-{start+30}s':(obs.times_s>=start)&(obs.times_s<start+30) for start in range(0,300,30)}}
            for label,mask in masks.items():
                inds=np.flatnonzero(mask);hardinds=inds[chosen_rows[inds]];blocks[label]=dict(windows=int(mask.sum()),mass=float(w[mask].sum()),hard_rows=len(hardinds),mean_residual_hz=float(w[mask]@terms.residual_hz[mask,j]/max(w[mask].sum(),1e-30)),hard_time_range_s=[float(obs.times_s[hardinds].min()),float(obs.times_s[hardinds].max())] if len(hardinds) else None)
            alias=np.rint((obs.measured_hz-prediction[:,j])/ALIAS_HZ).astype(int);alternatives=Counter();ambiguous=0;raw_alt_viable=0;top_margin_rank=Counter();lineage_bootstrap=Counter();peer_hard_agree=peer_seen=0
            peer={(p.visit_index,p.probe_index,p.receiver_id):i for i,p in enumerate(owners)}
            for i in np.flatnonzero(active):
                p=owners[i];alt_order=np.argsort(resp[i])[::-1];alt_order=alt_order[alt_order!=j];alt=int(alt_order[0]);other=sub.numbers[alt];alternatives[int(other)]+=float(w[i]);ambiguous+=int(resp[i,alt]>=.2 and chosen_rows[i]);top_margin_rank[p.candidate_rank]+=1
                raw=sorted(groups[p.source_group_id],key=lambda q:(-q.margin,q.candidate_rank,q.candidate_id));viable=[q for q in raw if abs(float(circular(q.measured_cfo_hz-prediction[i,j])))<=125.];raw_alt_viable+=int(len(viable)>1)
                raw_details=[dict(candidate_id=q.candidate_id,rank=q.candidate_rank,measured_hz=q.measured_cfo_hz,margin=q.margin,integer_source_sample_start=q.source_sample_start,exact_score=q.exact_score,control_score=q.control_score,model_residual_hz=float(circular(q.measured_cfo_hz-prediction[i,j]))) for q in raw]
                pi=peer.get((p.visit_index,p.probe_index,1-p.receiver_id));peer_seen+=int(pi is not None);peer_hard_agree+=int(pi is not None and hard[pi]==j)
                for b,track in enumerate(prepared.bootstrap_tracks):
                    if i in track:lineage_bootstrap[b]+=1
                rows_out.append(dict(target=target,index=int(i),window_id=obs.window_ids[i],candidate_id=p.candidate_id,visit=p.visit_index,probe=p.probe_index,rx=p.receiver_id,channel=p.channel,time_s=float(obs.times_s[i]),rf_hz=float(obs.rf_hz[i]),measured_hz=float(obs.measured_hz[i]),margin=float(obs.margin[i]),target_resp=float(w[i]),hard_target=bool(chosen_rows[i]),alias_integer=int(alias[i]),unwrapped_prediction_hz=float(prediction[i,j]),circular_residual_hz=float(terms.residual_hz[i,j]),alternative_sat=int(other),alternative_resp=float(resp[i,alt]),alternative_residual_hz=float(terms.residual_hz[i,alt]),alternative_prediction_difference_hz=float(circular(prediction[i,alt]-prediction[i,j])),passing_raw_candidates=raw_details,peer_receiver_window=obs.window_ids[pi] if pi is not None else None,peer_hard_sat=int(sub.numbers[hard[pi]]) if pi is not None and hard[pi]>=0 else None))
            # Adjacent original windows in each RX/channel, not only target rows.
            switches=[]
            for rx in (0,1):
                for ch in np.unique(obs.channel):
                    inds=np.flatnonzero((obs.receiver==rx)&(obs.channel==ch));inds=inds[np.argsort(obs.times_s[inds])]
                    for i,k in zip(inds[:-1],inds[1:]):
                        if (hard[i]==j)!=(hard[k]==j) and max(w[i],w[k])>=.5 and obs.times_s[k]-obs.times_s[i]<=2:
                            switches.append(dict(from_index=int(i),to_index=int(k),rx=rx,channel=int(ch),gap_s=float(obs.times_s[k]-obs.times_s[i]),measured_jump_hz=float(circular(obs.measured_hz[k]-obs.measured_hz[i])),from_sat=int(sub.numbers[hard[i]]) if hard[i]>=0 else None,to_sat=int(sub.numbers[hard[k]]) if hard[k]>=0 else None,from_target_resp=float(w[i]),to_target_resp=float(w[k])))
            record['targets'][str(target)]=dict(present_in_selected_bank=True,absolute_shift_s=float(shifts[j]),relative_shift_s=float(shifts[j]-v[7]),mass=float(w.sum()),hard_rows=int(chosen_rows.sum()),active_rows=int(active.sum()),raw_winning_ranks=dict(top_margin_rank),ambiguous_hard_rows_alt_resp_ge02=ambiguous,active_windows_multiple_raw_candidates_fitting_target_125hz=raw_alt_viable,alias_integer_hard_counts={str(a):int(np.sum(chosen_rows&(alias==a))) for a in np.unique(alias[chosen_rows])},alternative_mass_ranked=alternatives.most_common(10),bootstrap_track_active_counts=dict(lineage_bootstrap),paired_active_windows=peer_seen,peer_same_hard_satellite=peer_hard_agree,blocks=blocks,nearby_identity_switches=switches)
        (HERE/('windows-'+case+'.json')).write_text(json.dumps(rows_out,indent=2));output['cases'][case]=record;(HERE/'results.json').write_text(json.dumps(output,indent=2));print(case,json.dumps({n:{k:v for k,v in r.items() if k not in ('blocks','nearby_identity_switches')} for n,r in record['targets'].items()}),flush=True)

if __name__=='__main__':main()
