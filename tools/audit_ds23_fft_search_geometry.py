"""Read-only public capture metadata check for the fixed native search origin.

No IQ is read. Paths come verbatim from the sealed DS23 authority. The only
write is a local research receipt; no recording or QNAP path is changed.
"""

import json
import os
from pathlib import Path

from ds23_fft_grid_origin import search_origin
from probe_ds23_fft_grid_position import OUT, SOURCE, prepare
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.contracts.digests import canonical_digest


def main():
    protocol = prepare()
    authority = ROOT/'reports/2026_10_18_ds23_post_ds22/manifest.json'
    members = {m['dataset_label']:m for m in read(authority)['members']}
    rows = []
    for case in protocol['development_cases']+protocol['confirmation_cases']:
        member = members[case]; segment = member['raw_recording']['segments'][0]
        path = Path(segment['path'])
        if 'sha256:'+sha(path) != segment['sha256']:
            raise ValueError('capture manifest digest changed')
        document = read(path)
        if member['recording_format'] == 'short_window_iq_recording':
            targets = document['configuration']['targets']
            fs = document['sample_rate_hz']
        elif member['recording_format'] == 'starlink_adaptive_hop_iq':
            if canonical_digest(document['manifest']) != document['sha256']:
                raise ValueError('native capture envelope digest changed')
            geometry = document['manifest']['receipt']['plan']['geometry']
            targets = [p['target'] for p in geometry['profiles']]
            fs = geometry['sample_rate_hz']
        else:
            raise ValueError('unsupported public capture format')
        lookup = {(t['channel'],t['edge']):t['rf_center_hz'] for t in targets}
        tracking = read(SOURCE/case/'tracking.json');source = tracking.get('source',tracking)
        if source['sample_rate_hz'] != fs:
            raise ValueError('capture and GLRT rate differ')
        centers = sorted({float(lookup[p['channel'],p['edge']]-p['actual_rf_hz']) for p in source['probes']})
        origins = sorted({search_origin(fs,c) for c in centers})
        expected = search_origin(fs)
        rows.append(dict(case=case,sample_rate_hz=fs,public_capture_manifest=str(path),
            capture_manifest_sha256=segment['sha256'],centers_hz=centers,origins_hz=origins,
            expected_origin_hz=expected,matches=all(abs(o-expected)<1e-6 for o in origins)))
    if not all(r['matches'] for r in rows):
        raise ValueError('capture metadata contradicts fixed search origin')
    destination = OUT/'capture_geometry_audit.json'
    write(destination,dict(rows=rows,all_origins_match=True,no_IQ_or_GPS_or_TLE_read=True,
        first_segment_configuration_as_target_authority=True,
        every_saved_GLRT_probe_actual_RF_frequency_checked=True,
        historical_executable_identity_not_certified=True,
        dataset_manifest_sha256=sha(authority),source_sha256=sha(Path(__file__))))
    if os.geteuid() == 0:
        owner = OUT.stat();os.chown(destination,owner.st_uid,owner.st_gid)
    print('Verified capture geometry for',len(rows),'scans; all origins match',flush=True)


if __name__ == '__main__':
    main()
