"""Test saved cross-RX coherence against frame-repeat and pilot-null controls."""

from pathlib import Path
import time

import numpy as np

from ds23_cross_receiver_carrier import circular_delta, cross_carrier
from ds23_pilot_channel_projection import (
    advance_samples, project_arbitrary_pilot_symbols, project_pilot_channel,
)
from run_algo01_ds23_sample import ROOT, read, write, sha

SOURCE = ROOT / 'reports/2026_10_19_algo03_cross_receiver_carrier'
OUT = ROOT / 'reports/2026_10_19_algo03_cross_receiver_payload'


def frame_coherence(first, second, fs, epoch, frequency):
    fractions = []
    for k in range(14):
        start = round(epoch + k * fs / 750)
        stop = round(epoch + (k + 1) * fs / 750)
        if stop > len(first):
            break
        a, b = first[start:stop].copy(), second[start:stop].copy()
        a -= a.mean(); b -= b.mean()
        den = np.sum(abs(a)**2) * np.sum(abs(b)**2)
        if den:
            fractions.append(float(abs(np.sum(b * a.conj() * np.exp(
                -2j*np.pi*frequency*np.arange(len(a))/fs)))**2 / den))
    return dict(mean=float(np.mean(fractions)), median=float(np.median(fractions)),
                per_frame=fractions)


def main():
    if OUT.exists():
        raise FileExistsError('preserve payload controls')
    OUT.mkdir()
    source = read(SOURCE/'results.json')
    protocol = read(SOURCE/'protocol.json')
    write(OUT/'protocol.json', dict(selection_sha256=sha(SOURCE/'protocol.json'),
        original_result_sha256=sha(SOURCE/'results.json'),
        source_sha256=sha(Path(__file__)),
        projection_source_sha256=sha(ROOT/'tools/ds23_pilot_channel_projection.py'),
        no_GPS_or_TLE_used=True, no_calibration_or_position_updated=True,
        controls=['per-symbol null of arbitrary eight-pilot amplitudes',
                  'one-frame time shift within same receiver window',
                  'same-channel wrong window aligned to reference frame epoch',
                  'incoherent per-frame score permits arbitrary frame phases']))
    panels = {}
    for path, digest in protocol['panel_sha256'].items():
        if sha(ROOT/path) != digest:
            raise ValueError('saved IQ changed')
        panels[path] = np.load(ROOT/path, allow_pickle=False)
    started = time.monotonic()
    results, stored = [], []
    try:
        for row in source['rows']:
            entry = row['entry']; fs = entry['sample_rate_hz']
            values = panels[entry['panel']][entry['window_key']]
            samples = [values[:,k,0].astype(float) + 1j*values[:,k,1] for k in (0,1)]
            modes, residuals = {}, {}
            for name in ('raw', 'per_tone_three_taps', 'arbitrary_symbols'):
                rr = []; projections = []
                for k in (0,1):
                    if name == 'raw':
                        residual, detail = samples[k], {}
                    elif name == 'arbitrary_symbols':
                        residual, detail = project_arbitrary_pilot_symbols(samples[k], fs,
                            entry['edge'], entry['epochs'][k], row['fits'][k])
                    else:
                        residual, detail = project_pilot_channel(samples[k], fs, entry['edge'],
                            entry['epochs'][k], row['fits'][k], delay_taps=(-1.,0.,1.))
                    rr.append(residual); projections.append(detail)
                actual = cross_carrier(*rr, fs)
                frequency = actual['differential_CFO_hz']
                shifted = advance_samples(rr[1], fs/750)
                modes[name] = dict(actual=actual, projection=projections,
                    same_frame_score=frame_coherence(*rr, fs, entry['epochs'][0], frequency),
                    next_frame_control=cross_carrier(rr[0], shifted, fs),
                    next_frame_score=frame_coherence(rr[0], shifted, fs, entry['epochs'][0], frequency))
                residuals[name] = rr
            stored.append(residuals)
            results.append(dict(entry=entry, modes=modes))
            print(entry['case'],entry['channel'],entry['visit_index'],
                  {m:round(d['actual']['coherent_fraction'],6) for m,d in modes.items()},flush=True)
        for k, row in enumerate(results):
            e = row['entry']; fs = e['sample_rate_hz']
            for name, detail in row['modes'].items():
                controls = []
                for j, other in enumerate(results):
                    o = other['entry']
                    if j == k or (e['case'],e['channel']) != (o['case'],o['channel']):
                        continue
                    advance = circular_delta(o['epochs'][1],e['epochs'][0],fs/750)
                    shifted = advance_samples(stored[j][name][1], advance)
                    control = cross_carrier(stored[k][name][0], shifted, fs)
                    controls.append(dict(other_index=j, advance_samples=advance,
                        aligned_control=control, incoherent_score=frame_coherence(
                            stored[k][name][0], shifted, fs,e['epochs'][0],control['differential_CFO_hz'])))
                detail['epoch_aligned_other_window_controls'] = controls
        write(OUT/'results.json',dict(rows=results,seconds=time.monotonic()-started,
            protocol_sha256=sha(OUT/'protocol.json'),
            no_calibration_or_position_updated=True))
    finally:
        for panel in panels.values():
            panel.close()


if __name__ == '__main__':
    main()
