"""Matched channel ablation over the exact previously frozen fast input cohort."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
PARENT=Path('/srv/bulk/leo/research/ds25-20261024')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    source=json.loads((PARENT/'sample.json').read_bytes())
    members=[m for m in source['selected'] if m['mode']=='fast']
    assert len(members)==34
    for name,channels in [('ch1_4',[1,2,3,4]),('ch5_8',[5,6,7,8])]:
        root=ROOT/name
        assert not (root/'sample.json').exists()
        (root/'sample.json').write_text(json.dumps(dict(selected=members,parent_sample_sha256=sha(PARENT/'sample.json'),
            selection='all 34 DS24 revision 2 fast scans; no outcome or readiness selection'),indent=2)+'\n')
        (root/'channels.json').write_text(json.dumps(dict(channels=channels))+'\n')
    protocol=dict(dataset='DS24 revision 2 fast only',cases=34,
        primary='fresh ALGO02 + causal signed prior + equal-assignment-prior family cavity',
        secondary='original ALGO02',groups=['ch1_4','ch5_8','all_channels'],
        arms=['c0','fitted_c'],cold_start_km=[0,0],search_center=[37.906,-122.545],box_width_km=25,
        all_channel_reference=str(PARENT),all_channel_inference_reused=True,
        same_physical_source_contracts=True,subset_filter_before_graph_noise_orbit_association_and_calibration=True,
        preserve_original_observation_ids_timing_and_CFO=True,
        full_causal_catalogue_search_no_inherited_satellite_identities=True,
        excluded_channel_points_not_used_for_calibration=True,no_GPS_in_inference=True,no_post_scan_TLE=True,
        workers=8,stage_limits_seconds=dict(export=180,prepare=600,algo02=900,cavity=960),
        primary_comparison='common successful cases across all three groups; also report per-group success and all available results',
        missing_inputs='keep frozen missing-input status for paired comparison; no IQ reprocessing campaign',
        sources_sha256={str(p):sha(p) for p in sorted(ROOT.rglob('*.py'))},
        previous_protocol_sha256=sha(PARENT/'protocol.json'))
    (ROOT/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')


if __name__=='__main__':main()
