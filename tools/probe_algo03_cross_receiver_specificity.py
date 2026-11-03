"""Qualify a saved-IQ differential receiver observable against known pilots."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import time

import numpy as np

from ds23_cross_receiver_carrier import cross_carrier
from ds23_pilot_channel_projection import project_pilot_channel
from run_algo01_ds23_sample import ROOT, read, write, sha

SOURCE = ROOT / 'reports/2026_10_19_algo03_cross_receiver_carrier'
OUT = ROOT / 'reports/2026_10_19_algo03_cross_receiver_specificity'


def main():
    if OUT.exists():
        raise FileExistsError('preserve specificity controls')
    OUT.mkdir()
    original = read(SOURCE / 'results.json')
    protocol = read(SOURCE / 'protocol.json')
    write(OUT / 'protocol.json', dict(
        selection_protocol_sha256=sha(SOURCE / 'protocol.json'),
        original_result_sha256=sha(SOURCE / 'results.json'),
        source_sha256=sha(Path(__file__)),
        projection_source_sha256=sha(ROOT / 'tools/ds23_pilot_channel_projection.py'),
        controls=['independent per-tone complex gains per frame',
                  'per-tone gains with -1,0,+1 sample channel delay taps',
                  'same-channel different-window receivers',
                  'first-versus-second-half frequency repeatability'],
        no_GPS_or_TLE_used=True, no_calibration_or_position_updated=True))
    panels = {}
    for path, digest in protocol['panel_sha256'].items():
        if sha(ROOT / path) != digest:
            raise ValueError('saved panel changed')
        panels[path] = np.load(ROOT / path, allow_pickle=False)
    started = time.monotonic()
    def one(index, row):
        entry = row['entry']
        values = panels[entry['panel']][entry['window_key']]
        samples = [values[:, k, 0].astype(float) + 1j * values[:, k, 1]
                   for k in (0, 1)]
        modes = {}
        stored = {}
        for name, taps in [('per_tone', (0.,)), ('per_tone_three_taps', (-1., 0., 1.))]:
            residuals, details = [], []
            for k in (0, 1):
                residual, detail = project_pilot_channel(samples[k], entry['sample_rate_hz'],
                    entry['edge'], entry['epochs'][k], row['fits'][k], delay_taps=taps)
                residuals.append(residual)
                details.append(detail)
            modes[name] = dict(projection=details, full=cross_carrier(*residuals, entry['sample_rate_hz']),
                halves=[cross_carrier(*(r[a:b] for r in residuals), entry['sample_rate_hz'])
                        for a,b in [(0,25000),(25000,50000)]])
            stored[name] = residuals
        return index, dict(entry=entry, original_raw=row['raw'],
            original_one_gain_projection=row['pilot_projected'], modes=modes), stored
    results, residuals = {}, {}
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            for future in as_completed([executor.submit(one, i, row)
                                       for i,row in enumerate(original['rows'])]):
                k, row, r = future.result()
                results[k], residuals[k] = row, r
                print(k, row['entry']['case'], row['entry']['channel'],
                      {m:r['full']['coherent_fraction'] for m,r in row['modes'].items()}, flush=True)
        for k, row in results.items():
            key = (row['entry']['case'], row['entry']['channel'])
            for mode, detail in row['modes'].items():
                detail['different_window_controls'] = [dict(other_index=j,
                    **cross_carrier(residuals[k][mode][0], residuals[j][mode][1],
                                    row['entry']['sample_rate_hz']))
                    for j, other in results.items() if j != k
                    and (other['entry']['case'], other['entry']['channel']) == key]
        write(OUT / 'results.json', dict(rows=[results[k] for k in sorted(results)],
            seconds=time.monotonic()-started, protocol_sha256=sha(OUT/'protocol.json'),
            independent_unknown_content_not_yet_established=True,
            no_calibration_or_position_updated=True))
    finally:
        for panel in panels.values():
            panel.close()


if __name__ == '__main__':
    main()
