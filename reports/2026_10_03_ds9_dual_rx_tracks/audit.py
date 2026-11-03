"""DS9 longest dual-RX track overlaps: metadata-only, bounded retrospective audit."""
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
POP=REPORTS/'2026_09_28_ds9_post_ds8'
sys.path[:0]=[str(REPORTS/'2026_10_02_ds13_timing_em'),str(REPORTS/'2026_10_02_multiscan_localization'),
              str(REPORTS/'2026_10_02_localization_benchmark'),str(REPORTS/'2026_10_02_cross_scan_drift_evidence')]
from native_rx_difference import summarize_pairs
from check_other_scans import select_pairs,design,huber_fit


def digest(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def overlap_pairs(product):
    tracks={t['tracklet_id']:t for t in product['tracklets']};out=[]
    for hypothesis in product['tle_candidates']:
        members=[tracks[i] for i in hypothesis['tracklet_ids']]
        for left in members:
            if left['receiver_id']!=0:continue
            for right in members:
                if right['receiver_id']!=1 or left['actual_rf_hz']!=right['actual_rf_hz']:continue
                start=max(left['start_utc_ns'],right['start_utc_ns'])
                end=min(left['end_utc_ns'],right['end_utc_ns'])
                if end-start>=30e9:
                    out.append(dict(overlap_s=(end-start)/1e9,start_ns=start,end_ns=end,
                                    left=left,right=right,hypothesis=hypothesis))
    return out


def main():
    from edge_alias_diagnostic import _metadata
    from export_ds11 import raw_arrays,track_rows
    from leo.analysis.persistent_hop_trajectory import PersistentHopTrajectoryConfig,reconstruct_persistent_hop_trajectories
    started=time.monotonic();manifest_path=POP/'manifest.json';manifest=json.loads(manifest_path.read_text())
    hashes={str(manifest_path):digest(manifest_path),str(Path(__file__)):digest(__file__)}
    candidates=[]
    for capture in manifest['captures']:
        path=POP/'analysis'/(capture['session_id']+'.json')
        assert digest(path)==capture['analysis_evidence_sha256'];hashes[str(path)]=digest(path)
        product=json.loads(path.read_text())['tracking']['product']
        assert product['input_manifest_sha256']==capture['manifest_sha256']
        for candidate in overlap_pairs(product):
            candidates.append(dict(**candidate,capture=capture,product=product))
    candidates.sort(key=lambda c:(-c['overlap_s'],c['capture']['session_id']))
    print(f"Inventory: {len(candidates)} same-RF track overlaps >=30s in {len(set(c['capture']['session_id'] for c in candidates))} scans",flush=True)
    (HERE/'cases').mkdir(exist_ok=True);results=[];rejected=[];used=set();loaded={}
    for candidate in candidates:
        if len(results)>=16:break
        if time.monotonic()-started>600:raise TimeoutError('600s metadata-only audit limit; completed cases retained')
        capture=candidate['capture'];sid=capture['session_id'];product=candidate['product']
        if sid in used:continue
        if sid not in loaded:
            source,projected,metadata,join,rate=_metadata(Path('/srv/bulk/leo'),sid,capture['manifest_sha256'],product['analysis_manifest_sha256'])
            assert all(r is not None for r in metadata)
            arrays,_=raw_arrays(projected,source.timing.first_sample_estimate_utc_ns)
            trajectory=reconstruct_persistent_hop_trajectories(projected,config=PersistentHopTrajectoryConfig())
            loaded={sid:(source,projected,metadata,arrays,trajectory,rate)}
        source,projected,metadata,arrays,trajectory,rate=loaded[sid]
        selected,mapping=track_rows(projected,trajectory,[candidate['left'],candidate['right']])
        rows=sorted({r for t in selected for r in t['rows']})
        selected_metadata=[dict(metadata[r],local_probe_key=metadata[r]['probe_key']) for r in rows]
        assert np.array_equal(arrays['measured'][rows],[r['tracking_cfo_hz'] for r in selected_metadata])
        pairs=select_pairs(selected_metadata,rows,arrays,rate,1e-7)
        pairspan=float(np.ptp([p['time_s'] for p in pairs])) if pairs else 0.
        if len(pairs)<20 or pairspan<30:
            rejected.append(dict(session=sid,overlap_s=candidate['overlap_s'],pair_count=len(pairs),paired_span_s=pairspan))
            print(f"skip {sid}: {len(pairs)} pairs / {pairspan:.1f}s",flush=True);continue
        used.add(sid);h=candidate['hypothesis'];summary=summarize_pairs(pairs)
        origin=source.timing.first_sample_estimate_utc_ns
        pose_path=POP/'pose'/(sid+'.json');pose=json.loads(pose_path.read_text())
        assert digest(pose_path)==capture['pose_file_sha256'];assert pose['manifest_sha256']==capture['manifest_sha256']
        hashes[str(pose_path)]=digest(pose_path)
        null_delta=h['nominal_heldout_negative_log_score']-h['radio_null_heldout_negative_log_score']
        result=dict(case_id=f'DS9-{len(results)+1:02d}',session_id=sid,catalog_number=h['leading_catalog_number'],
            channel=candidate['left']['channel'],edge=candidate['left']['edge'],sample_rate_hz=rate,
            overlap_s=candidate['overlap_s'],overlap_start_s=(candidate['start_ns']-origin)/1e9,
            overlap_end_s=(candidate['end_ns']-origin)/1e9,
            rx0_track_s=(candidate['left']['end_utc_ns']-candidate['left']['start_utc_ns'])/1e9,
            rx1_track_s=(candidate['right']['end_utc_ns']-candidate['right']['start_utc_ns'])/1e9,
            rx0_track_id=candidate['left']['tracklet_id'],rx1_track_id=candidate['right']['tracklet_id'],
            paired_span_s=pairspan,summary=summary,pairs=pairs,archived_identity=h,
            nominal_minus_radio_null_score=null_delta,beats_radio_null=bool(null_delta<0),
            physical_group_id=h['physical_group_id'],capture_manifest_sha256=capture['manifest_sha256'],
            analysis_manifest_sha256=product['analysis_manifest_sha256'],pose_revision=pose['pose_authority']['revision'],
            pose_nominal_outward_tilt_deg=pose['pose_authority']['nominal_outward_tilt_deg'],
            raw_metadata_binding='Read-only stores verified input and analysis digests; archived track IDs and point counts replayed exactly.')
        results.append(result)
        (HERE/'cases'/(result['case_id']+'.json')).write_text(json.dumps(result,indent=2,allow_nan=False))
        print(f"{result['case_id']} {sid} candidate {h['leading_catalog_number']}: overlap {candidate['overlap_s']:.1f}s, {len(pairs)} pairs/{pairspan:.1f}s, null delta {null_delta:+.2f}",flush=True)
    if len(results)<16:raise ValueError(f'Only {len(results)} qualifying cases; do not relax thresholds silently')
    table=[];allpairs=[]
    for r in results:
        m=r['summary']['channel_offset_controlled_models']
        table.append(dict(case_id=r['case_id'],session_id=r['session_id'],candidate_satellite=r['catalog_number'],
            channel=r['channel'],overlap_s=r['overlap_s'],paired_span_s=r['paired_span_s'],pair_count=len(r['pairs']),
            difference_slope_hz_s=m['1']['slope_hz_s_at_150s'],
            held_constant_mae_hz=m['0']['five_time_block_held_median_absolute_error_hz'],
            held_linear_mae_hz=m['1']['five_time_block_held_median_absolute_error_hz'],
            held_quadratic_mae_hz=m['2']['five_time_block_held_median_absolute_error_hz'],
            nominal_minus_radio_null_score=r['nominal_minus_radio_null_score'],
            abstention_recommended=r['archived_identity']['abstention_recommended']))
        allpairs.extend(dict(case_id=r['case_id'],session_id=r['session_id'],**p) for p in r['pairs'])
    for name,rows in [('summary.csv',table),('paired-points.csv',allpairs)]:
        with (HERE/name).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(4,4,figsize=(18,13))
    for ax,r in zip(axes.ravel(),results):
        pairs=r['pairs'];t=np.array([p['time_s'] for p in pairs]);y=np.array([p['rx1_minus_rx0_modulo_alias_hz'] for p in pairs]);center=np.median(y)
        ax.scatter(t,y-center,s=9,alpha=.7)
        channel=np.full(len(t),r['channel'])
        for order,style in [(1,'--'),(2,'-')]:
            matrix=design(t,channel,order,np.unique(channel));pred=matrix@huber_fit(matrix,y)
            ix=np.argsort(t);ax.plot(t[ix],pred[ix]-center,style,lw=1.3,label=('Line' if order==1 else 'Quadratic'))
        ax.set_title(f"{r['case_id']} · candidate {r['catalog_number']}\n{len(pairs)} pairs · {r['paired_span_s']:.1f}s",fontsize=10)
        ax.grid(alpha=.2);ax.set_xlabel('Receive time (s)',fontsize=8);ax.set_ylabel('RX1−RX0, centered (Hz)',fontsize=8)
    axes[0,0].legend(fontsize=8)
    fig.suptitle('DS9 · 16 distinct scans with long, tightly paired dual-RX track support\nSame RF and visit/probe, epochs ≤100 ns; provisional satellite labels; no orbital correction',fontsize=14)
    fig.tight_layout(rect=(0,0,1,.95));fig.savefig(HERE/'sixteen-dual-rx-tracks.png',dpi=150)
    for p,h in hashes.items():assert digest(p)==h
    (HERE/'receipt.json').write_text(json.dumps(dict(schema='ds9-dual-rx-long-track-audit/v1',cases=table,
       population_scans=len(manifest['captures']),candidate_track_pair_count=len(candidates),rejected=rejected,source_hashes=hashes,
       elapsed_s=time.monotonic()-started,
       selection='Descending same-RF RX0/RX1 archived track overlap >=30s; at least20 native-zero-bin pairs '
                 'with <=100ns epoch mismatch spanning >=30s; at most one case per scan; first16 qualifying distinct scans. '
                 'Within fixed track memberships pair selection maximizes weaker GLRT margin, never frequency agreement.',
       limitations=['Retrospective longest-track selection, not a representative DS9 sample.',
         'Satellite labels are archived provisional candidates, not verified identities; radio-null controls are retained.',
         'Within-track CFO-based selection can narrow the observed difference distribution; no pair frequency gate added.',
         'Five contiguous time-block tests with 1s guard, fixed100Hz Huber loss; no full scan held out.',
         'Same epoch is not decoded common-signal identity. Differences modulo227272.727Hz.',
         'DS9 pose differs from DS13; nominal tilt recorded per case, no hard beam exclusion.',
         'No RF collection, raw IQ decoding, satellite re-fit or production changes.']),indent=2,allow_nan=False))


if __name__=='__main__':main()
