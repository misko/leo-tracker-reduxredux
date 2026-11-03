"""Read-only provenance/feasibility review of the originally discussed failures.

No numerical fitting or changes to the frozen experiment. Standard library only.
"""

import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / '2026_10_07_recent_filter_review/snapshot.json'
CASES = [
    ('original_first', 'scan-fw-6bf407cfe8158445', 'fitted-c'),
    ('original_second', 'scan-fw-559a822227a6a71b', 'fitted-c'),
    ('later_zero_c_failure', 'scan-fw-e3bebc228093a125', 'zero-c'),
]


def main():
    raw = SOURCE.read_bytes()
    captures = {c['session_id']: c for c in json.loads(raw)['captures']}
    manifest = json.loads((HERE/'inputs/manifest.json').read_text())
    tested = {c['session_id']: c['case'] for c in manifest['cases']}
    results = {option: json.loads((HERE/'polished'/option/'results.json').read_text())
               for option in ['control', 'window60', 'window30', 'window10']}
    rows = []
    for label, sid, arm in CASES:
        capture = captures[sid]
        doc = capture['regional_document']
        selected = next(a['selected'] for m in doc['methods'] if m['name']=='V16'
                        for a in m['arms'] if a['name']==arm)
        pool = [r for r in doc['diagnostics']['final_starts']
                if r['method']=='V16' and r['arm']==arm and r['fit']]
        best = min(pool,key=lambda r:(r['fit']['objective']+r['calibration_penalty'],r['basin'],r['start']))
        v = best['fit']['vector']
        assert best['basin'] == selected['source_basin']
        assert math.isclose(best['fit']['objective']+best['calibration_penalty'],selected['selection_score'],abs_tol=1e-8,rel_tol=0)
        assert v[:2] == [selected['east_km'],selected['north_km']]
        slopes = [v[3],v[5]]
        timestamp = datetime.fromisoformat(capture['capture_start_utc']).astimezone(ZoneInfo('America/Los_Angeles'))
        row = dict(label=label,session_id=sid,method='V16',arm=arm,
                   capture_start_local=timestamp.isoformat(),
                   published_error_km=selected['horizontal_error_m']/1000,
                   published_converged=selected['converged'],
                   additional_slopes_hz_s=slopes,
                   allowed_by_slope_windows={str(width): all(abs(s)<=width for s in slopes) for width in [60,30,10]},
                   included_in_slope_experiment=sid in tested,
                   published_document_sha256=capture['regional_document_sha256'])
        if sid in tested:
            row['slope_experiment'] = {}
            for option, receipt in results.items():
                fit = next(r for r in receipt['selections'] if r['case']==tested[sid] and r['method']=='V16' and r['arm']==arm)
                row['slope_experiment'][option] = dict(error_km=fit['horizontal_error_m']/1000,
                                                       additional_slopes_hz_s=fit['additional_slopes_hz_s'],
                                                       converged=fit['converged'], data_nll=fit['data_nll'],
                                                       posterior_rms_hz=fit['posterior_rms_hz'])
        rows.append(row)
    assert all(not r['included_in_slope_experiment'] for r in rows[:2])
    assert all(all(r['allowed_by_slope_windows'].values()) for r in rows[:2])
    assert not any(rows[2]['allowed_by_slope_windows'].values())
    output = dict(source=str(SOURCE),source_sha256=hashlib.sha256(raw).hexdigest(),
                  review='Original two catastrophic fitted-c captures omitted from slope experiment; all three tested boxes admit their saved bad fits.',
                  scope='Fixed-state slope feasibility and receipt provenance only, not new refitting.',cases=rows)
    (HERE/'original_failures_review.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2))


if __name__=='__main__':
    main()
