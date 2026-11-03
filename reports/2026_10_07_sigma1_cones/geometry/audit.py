"""Read-only capture-specific fixture authority and companion verification."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SIDS=('scan-fw-6a376b600fc2f542','scan-fw-e3bebc228093a125')
def canonical(d):return json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(raw):return 'sha256:'+hashlib.sha256(raw).hexdigest()
def utc(ns):return datetime.fromtimestamp(ns/1e9,timezone.utc).isoformat()

def main():
    snap=json.loads((ROOT/'reports/2026_10_07_recent_filter_review/snapshot.json').read_text())
    authority=json.loads((ROOT/'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json').read_text())
    fixture=ROOT/'3d_prints/LT3D-004-opposite-side-lnbf-snap-stand/LT3D-004B-40deg-snap-stand.stl'
    assert digest(fixture.read_bytes())==authority['fixture_digest']
    iq=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);tracking=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    out=dict(authority=authority,fixture_sha256=authority['fixture_digest'],captures={})
    try:
        for sid in SIDS:
            source=tracking.load(sid);doc=next(c['regional_document'] for c in snap['captures'] if c['session_id']==sid);assert source.input_manifest_sha256==doc['input_manifest_sha256'];assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
            published=iq.inspect(sid);manifest=published.manifest;receipt=manifest.receipt
            # This immutable companion location is the published interface documented
            # in docs/operations/radio20-lt3d-004b-20261001.md, not an IQ implementation path.
            companion=Path('/srv/bulk/leo/capture-pose')/authority['revision']/(sid+'.json')
            binding=json.loads(companion.read_text());pose=binding['pose_authority']
            assert binding['session_id']==sid;assert binding['manifest_sha256']==source.input_manifest_sha256==published.manifest_sha256
            assert binding['pose_authority_digest']==digest(canonical(pose))==digest(canonical(authority));assert binding['binding_digest']==digest(canonical({k:v for k,v in binding.items() if k!='binding_digest'}))
            assert (receipt.radio_id,receipt.radio_serial)==(pose['radio_id'],pose['radio_serial']);assert tuple(receipt.plan.geometry.receiver_ids)==(0,1)
            assert manifest.timing.qualified;assert binding['capture_start_earliest_utc_ns']==manifest.timing.first_sample_earliest_utc_ns;assert binding['capture_end_utc_ns']==manifest.timing.terminal_realtime_ns
            assert pose['valid_from_utc_ns']<=binding['capture_start_earliest_utc_ns']<=binding['capture_end_utc_ns']<pose['valid_until_utc_ns']
            out['captures'][sid]=dict(companion_path=str(companion),binding_digest=binding['binding_digest'],pose_authority_digest=binding['pose_authority_digest'],input_sha256=source.input_manifest_sha256,analysis_sha256=source.analysis_manifest_sha256,radio_id=receipt.radio_id,radio_serial=receipt.radio_serial,receiver_ids=list(receipt.plan.geometry.receiver_ids),qualified=True,start_earliest_utc=utc(binding['capture_start_earliest_utc_ns']),end_utc=utc(binding['capture_end_utc_ns']),source_timing=source.timing.model_dump(mode='json') if hasattr(source.timing,'model_dump') else str(source.timing),fixture_part_id=pose['fixture_part_id'],all_bindings_verified=True)
    finally:tracking.close();iq.close()
    summary=json.loads((ROOT/'reports/2026_10_05_receiver_cones/summary.json').read_text());out['frozen_empirical_cones']=dict(parameters=summary['primary']['parameters'],nominal_boresights_az_el_deg=[[270,70],[90,70]],not_measured_beamwidth=True)
    (HERE/'geometry.json').write_text(json.dumps(out,indent=2));print(json.dumps(out['captures'],indent=2))

if __name__=='__main__':main()
