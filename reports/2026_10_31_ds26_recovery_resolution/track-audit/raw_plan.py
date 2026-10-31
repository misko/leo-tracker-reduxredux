"""Freeze a measurement-only 18-window panel and recover original scorer inputs.

Stops before IQ access: existing verified reader has no selective-window port.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path
import numpy as np
from audit import OUT,OLD,read,encode


def run():
    diag=read(next(OLD.glob('*DS26-0265/result.json')));row=diag['row'];tracking=read(row['tracking_path']);source=tracking['source']
    tracks=read(row['tracks_path']);obs={o['observation_id']:o for o in read(row['observations_path'])}
    original=read(Path(row['inventory_path']).parents[2]/'snapshot/inference/family_cavity/position/SCAN.json')
    identities={r['component']:r['candidate_norad'] for r in original['baseline_node']['seed']['rows']}
    active_ids=set();offset=0
    bycomponent={t['key']:t for t in tracks}
    for r in original['baseline_node']['seed']['rows']:
        t=bycomponent[r['component']];n=len(t['observation_ids']);mask=original['original_mask'][offset:offset+n];offset+=n
        active_ids.update(oid for oid,use in zip(t['observation_ids'],mask,strict=True) if use)
    assert offset==len(original['original_mask'])
    target=tracks[row['track_index']]
    rng=np.random.default_rng(20261031)
    chosen=[dict(kind='target',observation_id=target['observation_ids'][i],component=target['key']) for i in sorted(rng.choice(len(target['observation_ids']),12,replace=False).tolist())]
    controls=[dict(kind='other_family_control',observation_id=oid,component=t['key'],nominee_norad=identities[t['key']])
        for t in tracks if t['receiver']==1 and t['channel']==4 and t['key'] in identities and identities[t['key']]!=66102 for oid in t['observation_ids'] if oid in active_ids]
    chosen += [controls[i] for i in sorted(rng.choice(len(controls),min(6,len(controls)),replace=False).tolist())]
    lookup={}
    for p in source['probes']:
        if p['receiver_id']!=0 or p['channel']!=4:continue
        for c in p['candidates']:
            key=(round(c['fractional_tracking_cfo_hz'],6),round(c['fractional_margin'],10));lookup.setdefault(key,[]).append((p,c))
    for point in chosen:
        o=obs[point['observation_id']];key=(round(o['measured_cfo_hz'],6),round(o['fractional_margin'],10))
        p,c=min(lookup[key],key=lambda z:z[1]['candidate_rank'])
        point.update(time_s=o['time_s'],visit_index=p['visit_index'],receiver_id=0,channel=4,edge=p['edge'],sample_start=p['valid_start_counter'],peak=c)
    plan=dict(seed=20261031,selection='Uniform target observation indices before orbital-residual read; then uniform actively retained other-family same-RX/same-channel controls. No residual selection.',
        target_count=12,control_count=len(chosen)-12,maximum_unique_windows=20,window_samples=200000,sample_rate_hz=10000000,
        maximum_seconds=300,no_GPS_TLE_or_orbit_input_in_refinement=True,points=chosen,
        proposed_refinement='Existing continuous_glrt_score at fixed original fractional epoch and source-bound acquired_cfo_hz; same symbols2..65 and alias; exact/control both DTFT-refined; freeze outputs before comparing orbital residuals.')
    (OUT/'raw-plan.json').write_text(json.dumps(plan,default=encode,indent=2)+'\n')
    root=Path('/srv/bulk/leo/analysis')/source['session_id'];manifest_path=next(root.glob('*/manifest.json'));manifest=read(manifest_path)
    receipt=dict(status='blocked_before_IQ',raw_windows_read=0,new_RF=False,plan_sha256=hashlib.sha256((OUT/'raw-plan.json').read_bytes()).hexdigest(),
        original_analysis_manifest=str(manifest_path),pipeline_release_id=manifest['pipeline_release_id'],
        original_analysis_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),rows=[],source_products={})
    needed={p['visit_index'] for p in chosen};original_windows={}
    for product in manifest['products']:
        scope=product['scope_key'];match=re.fullmatch(r'segment-(\d+)\.windows-(\d+)-(\d+)',scope)
        if product['kind']!='fast-scan.glrt' or match is None:continue
        seg,first,last=map(int,match.groups());base=seg*512
        if not any(base+first<=v<base+last for v in needed):continue
        path=Path('/srv/bulk/leo')/product['logical_uri'].removeprefix('bulk://')
        payload=path.read_bytes();digest='sha256:'+hashlib.sha256(payload).hexdigest();assert digest==product['digest']
        receipt['source_products'][str(path)]=digest
        for w in json.loads(payload)['windows']:
            if w['visit'] in needed:original_windows[w['visit']]=w
    spacing=1/(512*4.4e-6)
    for p in chosen:
        w=original_windows[p['visit_index']];rx=next(r for r in w['receivers'] if r['receiver_id']==0)
        c=next(c for c in rx['candidates'] if c['candidate_rank']==p['peak']['candidate_rank'])
        assert abs(c['fractional_tracking_cfo_hz']-p['peak']['fractional_tracking_cfo_hz'])<1e-6
        assert abs(c['fractional_epoch_offset_samples']-p['peak']['fractional_epoch_offset_samples'])<1e-9
        grid_bin=c['fractional_residual_cfo_hz']/spacing
        receipt['rows'].append(dict(observation_id=p['observation_id'],visit_index=p['visit_index'],
            acquired_cfo_hz=c['acquired_cfo_hz'],fractional_residual_cfo_hz=c['fractional_residual_cfo_hz'],
            fractional_tracking_cfo_hz=c['fractional_tracking_cfo_hz'],exact_score=c['fractional_exact_score'],control_score=c['fractional_control_score'],
            fractional_offset_samples=c['fractional_epoch_offset_samples'],anchor=c['epoch_sample'],iq_sha256=w['iq_sha256'],
            discrete_bin=round(grid_bin),distance_from_512_grid_bins=abs(grid_bin-round(grid_bin))))
    reader=Path('/opt/leo-shared-scans/v063-10m-0eab0c85fa2aac69/worker/src/leo/storage/short_window.py')
    receipt.update(blocker='Pinned deployed multirate ShortWindowReader exposes only sequential windows(), not selective read. Its 64-window compressed chunks/512-window segments require reading unselected IQ to reach this frozen random panel, exceeding the authorized20-window cap. No raw export or native/continuous replay was attempted.',
        reader_source=str(reader),reader_source_sha256=hashlib.sha256(reader.read_bytes()).hexdigest(),
        existing_reader_methods=['__init__','_member','windows'],
        archived_default_grid_spacing_hz=spacing,uniform_bin_noise_scale_hz=spacing/np.sqrt(12),
        maximum_archived_distance_from_512_grid_bins=max(r['distance_from_512_grid_bins'] for r in receipt['rows']),
        all_archived_residual_increments_zero=all(r['fractional_residual_cfo_hz']==0 for r in receipt['rows']),
        FFT_size_identified_from_archived_increments=False,
        limitation='ALL18 archived residual increments are zero: tracking CFO equals the continuous acquisition conditioning frequency. This indicates a refinement deadband, not absolute443.892Hz CFO quantization. Zero increments cannot distinguish512 fromotherFFT sizes. Source code default512 and a synthetic scorer test establish implementation mechanics, not archived binary/config identity. Source-bound discrete scores are recovered but not replayed onIQ; continuous counterfactual is still unavailable.')
    (OUT/'raw-pilot-receipt.json').write_text(json.dumps(receipt,default=encode,indent=2)+'\n')
    print('points',len(chosen),'controls',len(controls),'source_products',len(receipt['source_products']),'maxbinerror',receipt['maximum_archived_distance_from_512_grid_bins'])


if __name__=='__main__':run()
