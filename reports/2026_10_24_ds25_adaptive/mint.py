"""Freeze adaptive-only DS25 and its same-interval fast comparison cohort."""
import copy
import gzip
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
PARENT = Path('/srv/bulk/leo/research/ds24-20261024-extension/manifest.json')


def digest(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def select(parent):
    members = []
    for m in sorted(parent['members'], key=lambda x: (x['captured_utc_ns'], x['recording_id'])):
        if m['recording_format'] != 'starlink_adaptive_hop_iq':
            continue
        assert m['sample_rate_hz'] == 10000000
        r = copy.deepcopy(m)
        r['parent_dataset_label'] = r['dataset_label']
        r['dataset_label'] = f'DS25-{len(members)+1:04d}'
        members.append(r)
    return members


def main():
    if (OUT/'sample.json').exists():
        raise ValueError('refusing to change frozen analysis cohort')
    raw = PARENT.read_bytes()
    parent = json.loads(raw)
    members = select(parent)
    manifest = dict(schema='ds25-recording-membership/v1', dataset_id='DS25',
        parent_dataset='DS24 revision 2', parent_manifest_sha256=digest(raw),
        start_utc_ns=parent['start_utc_ns'], cutoff_utc_ns=parent['cutoff_utc_ns'],
        selection='All adaptive 10 MS/s acquisitions in DS24 revision 2; no outcome or readiness filter',
        analysis_readiness_required=False, complete_recording_required=False,
        members=members, counts=dict(members=len(members),
        complete=sum(m['recording_state']=='complete' for m in members),
        windows=sum(m['window_count'] for m in members)))
    raw = (json.dumps(manifest, indent=2)+'\n').encode()
    (OUT/'dataset/manifest.json').write_bytes(raw)
    (OUT/'dataset/manifest.json.gz').write_bytes(gzip.compress(raw, compresslevel=6,mtime=0))
    (OUT/'dataset/manifest.sha256').write_text(digest(raw)+'  manifest.json\n')
    selected = []
    combined = members + [m for m in parent['members'] if m['recording_format']=='short_window_iq_recording']
    for m in combined:
        r = {k:copy.deepcopy(v) for k,v in m.items() if k!='raw_recording'}
        r['raw_authority_digest'] = m.get('raw_authority_digest') or m['raw_recording']['identity_sha256']
        r['raw_identity_sha256'] = m['raw_recording']['identity_sha256']
        r['raw_manifest_receipts'] = m['raw_recording']['segments']
        r['mode'] = 'adaptive' if m['recording_format']=='starlink_adaptive_hop_iq' else 'fast'
        selected.append(r)
    sample = dict(study='DS25 adaptive vs same-interval DS24 fast', dataset_manifest_sha256=digest(raw),
        parent_manifest_sha256=manifest['parent_manifest_sha256'],
        sampling='all members of both modes; unavailable inputs retained', selected=selected)
    (OUT/'sample.json').write_text(json.dumps(sample,indent=2)+'\n')
    protocol=dict(primary_method='fresh ALGO02 + qualified causal signed phase prior + equal-prior family cavity',
        secondary_method='original ALGO02-v1', arms=['c0','fitted_c'],
        region_center=[37.906,-122.545], box_width_km=25, start_east_north_km=[0,0],
        same_observations_candidates_priors_budgets_between_c_arms=True,
        same_inference_pipeline_for_both_modes=True, existing_GLRT_only=True,
        no_stationary_position_pooling=True, no_post_scan_TLE=True, no_GPS_in_inference=True,
        sample_sha256=digest((OUT/'sample.json').read_bytes()),
        dataset_manifest_sha256=digest(raw), temporal_sensitivity='also compare shared occupied UTC 3-hour blocks',
        execution=dict(workers=8,per_case_export_seconds=180,prepare_seconds=600,algo02_seconds=900,cavity_seconds=960),
        inference_sources_sha256={str(p):digest(p.read_bytes()) for p in sorted((OUT/'engine').glob('*.py'))})
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    print(json.dumps(dict(adaptive=len(members),fast=len(combined)-len(members))))


if __name__=='__main__':
    main()
