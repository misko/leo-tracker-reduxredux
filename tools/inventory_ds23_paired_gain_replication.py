"""Freeze scan-disjoint paired-RX probes from already saved local dual IQ."""

from pathlib import Path
import json
import numpy as np

from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_21_ds23_paired_gain_replication'
AUTHORITY=ROOT/'reports/2026_10_21_ds23_differential_frame_phase_v2/protocol.json'
OLD=ROOT/'reports/2026_10_19_algo03_joint_frame_phase_fractional/results.json'


def epoch(peak):
    return peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']


def main():
    OUT.mkdir(exist_ok=True);destination=OUT/'inventory.json'
    if destination.exists():raise FileExistsError('preserve prospective point-disjoint inventory')
    authority=read(AUTHORITY);old=read(OLD);excluded={r['entry']['case'] for r in old['rows']}
    records=[];failures=[];bindings={}
    for filename,digest in authority['saved_panel_sha256'].items():
        path=Path(filename)
        if sha(path)!=digest:raise ValueError('saved dual-RX panel changed')
        with np.load(path,allow_pickle=False) as z:
            metadata=json.loads(str(z['metadata_json']));case=metadata['case']
            if case in excluded:continue
            points={r['window_key']:r for r in metadata['points']}
            tracking=ROOT/'reports/2026_10_19_algo02_ds23_full'/case/'tracking.json'
            if not tracking.exists():failures.append(dict(case=case,reason='original native peak contract missing'));continue
            document=read(tracking);source=document.get('source',document)
            probes={(r['visit_index'],r['receiver_id']):r for r in source['probes']}
            for window_key,point in points.items():
                visit=point['visit_index'];pair=[probes.get((visit,rx)) for rx in [0,1]]
                if any(p is None for p in pair):continue
                candidates=[[p for p in r['candidates'] if p['passed_fractional_margin_gate'] and p['fractional_margin']>=.3] for r in pair]
                proposed=[]
                for a in candidates[0]:
                    for b in candidates[1]:
                        difference=(epoch(a)-epoch(b)+2500000/1500)%(2500000/750)-2500000/1500
                        if abs(difference)>.25:continue
                        proposed.append((min(a['fractional_margin'],b['fractional_margin']),abs(difference),a,b))
                if not proposed:continue
                margin,delta,a,b=max(proposed,key=lambda p:(p[0],-p[1],-p[2]['fractional_tracking_cfo_hz']))
                records.append(dict(case=case,panel=str(path),window_key=window_key,visit_index=visit,
                    sample_counter=point['sample_counter'],channel=point['lane'][1],rf_hz=point['lane'][2],
                    edge=point['edge'],sample_rate_hz=2500000,epochs=[epoch(a),epoch(b)],peaks=[a,b],
                    minimum_native_margin=margin,native_epoch_difference_samples=delta,
                    raw_window_sha256=point['raw_window_sha256']))
        bindings[str(path)]=digest
    selected=[]
    for case in sorted({r['case'] for r in records}):
        choices=[r for r in records if r['case']==case]
        chosen=max(choices,key=lambda r:(r['minimum_native_margin'],-r['native_epoch_difference_samples'],-r['visit_index']))
        selected.append(chosen)
    write(destination,dict(selected=selected,available_pairs=len(records),candidate_case_counts={c:sum(r['case']==c for r in records) for c in sorted({r['case'] for r in records})},
        prior_5_probe_cases_excluded=sorted(excluded),failures=failures,
        selected_one_probe_per_new_scan_by_native_margin_only=True,
        native_epoch_tolerance_samples=.25,minimum_each_native_margin=.3,
        no_complex_gain_prediction_position_error_GPS_TLE_or_satellite_ID_used_for_selection=True,
        no_new_RF_collection_or_raw_export=True,panel_sha256=bindings,
        authority_sha256=sha(AUTHORITY),source_sha256=sha(Path(__file__)),
        not_an_RF_replication_result_until_actual_fits_controls_and_covariance_are_evaluated=True))
    print(dict(scan_disjoint_probes=len(selected),available_pairs=len(records),missing=failures),flush=True)


if __name__=='__main__':main()
