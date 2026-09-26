"""Select a paired GLRT track segment without inspecting phase; plot its IQ cross-phase."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import zstandard

OUT = Path(__file__).resolve().parent
REPORT = OUT.parent
RATE = 10_000_000
SYMBOL_RATE = 250_000_000 / 1100
WINDOW = 16384


def alias_distance(value):
    return abs((value + SYMBOL_RATE / 2) % SYMBOL_RATE - SYMBOL_RATE / 2)


def main():
    visits = list(csv.DictReader((REPORT/'acquisition/visit-inventory.csv').open()))
    best = {}
    for row in csv.DictReader((REPORT/'acquisition/candidate-inventory.csv').open()):
        if row['passed_0p025_comparison_gate'] != 'True':
            continue
        key = int(row['visit_index']), int(row['receiver_id'])
        if key not in best or float(row['fractional_margin']) > float(best[key]['fractional_margin']):
            best[key] = row
    runs, current = [], []
    for visit in visits:
        index = int(visit['visit_index'])
        a, b = best.get((index, 0)), best.get((index, 1))
        good = a is not None and b is not None
        if good:
            good = alias_distance(float(b['tracking_absolute_baseband_cfo_hz']) - float(a['tracking_absolute_baseband_cfo_hz'])) < 2000
        if current:
            previous = int(current[-1]['visit_index'])
            continuous = good and index == previous + 1 and visit['target_index'] == current[-1]['target_index']
            if continuous:
                continuous = all(alias_distance(float(best[(index, rx)]['tracking_absolute_baseband_cfo_hz']) - float(best[(previous, rx)]['tracking_absolute_baseband_cfo_hz'])) < 2000 for rx in (0, 1))
            if not continuous:
                runs.append(current)
                current = []
        if good:
            current.append(visit)
    if current:
        runs.append(current)
    runs.sort(key=lambda run: (len(run), sum(min(float(v['rx0_best_margin']), float(v['rx1_best_margin'])) for v in run)), reverse=True)
    selected = runs[0]
    indices = [int(v['visit_index']) for v in selected]
    origin = int(selected[0]['valid_start_counter'])
    seed = float(best[(indices[0], 1)]['tracking_absolute_baseband_cfo_hz']) - float(best[(indices[0], 0)]['tracking_absolute_baseband_cfo_hz'])
    source = Path('/srv/bulk/leo/scanner-adaptive-recordings/scan-fw-32a202b6e55630ec')
    manifest = json.loads((source/'manifest.json').read_text())['manifest']
    taper = np.hanning(WINDOW)**2
    rows = []
    for visit in selected:
        index = int(visit['visit_index'])
        chunk = manifest['chunks'][index]
        raw = zstandard.ZstdDecompressor().decompress((source/chunk['relative_path']).read_bytes(), max_output_size=chunk['uncompressed_bytes'])
        assert 'sha256:' + hashlib.sha256(raw).hexdigest() == chunk['uncompressed_sha256']
        iq = np.frombuffer(raw, dtype='<i2').reshape(-1, 2, 2)
        x = iq[..., 0].astype(float) + 1j * iq[..., 1].astype(float)
        counter = int(visit['valid_start_counter'])
        for start in range(0, len(x)-WINDOW+1, WINDOW):
            t = (counter-origin+np.arange(start, start+WINDOW))/RATE
            a, b = x[start:start+WINDOW, 0], x[start:start+WINDOW, 1]
            product = np.conj(a)*b*taper
            raw_product = product.sum()
            corrected = np.sum(product*np.exp(-2j*np.pi*seed*t))
            denominator = np.sqrt(np.sum(abs(a)**2*taper)*np.sum(abs(b)**2*taper))
            rows.append(dict(visit_index=index, time_s=float(t.mean()), phase_difference_deg=float(np.angle(corrected, deg=True)), raw_phase_difference_deg=float(np.angle(raw_product, deg=True)), coherence=float(abs(corrected)/denominator), raw_coherence=float(abs(raw_product)/denominator)))
    with (OUT/'phase-vs-time.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    selection = dict(visit_indices=indices, channel=int(selected[0]['channel']), relative_cfo_seed_hz=seed,
                     origin_device_counter=origin, sample_rate_hz=RATE, window_samples=WINDOW,
                     policy='Longest consecutive same-target run with dual-RX passing GLRT and <2 kHz alias-aware inter-RX and temporal CFO differences; tie by summed weaker-RX margin. No phase used.',
                     candidate_rows=[best[(i, rx)] for i in indices for rx in (0, 1)])
    (OUT/'selection.json').write_text(json.dumps(selection, indent=2)+'\n')
    fig, axes = plt.subplots(3, 1, figsize=(12, 8), sharex=True, constrained_layout=True, gridspec_kw={'height_ratios':[2, 1, 1]})
    t = np.array([r['time_s'] for r in rows])
    phase = np.array([r['phase_difference_deg'] for r in rows])
    coherence = np.array([r['coherence'] for r in rows])
    points = axes[0].scatter(t, phase, c=coherence, cmap='viridis', s=13, vmin=0, vmax=max(.1, float(np.quantile(coherence,.98))))
    fig.colorbar(points, ax=axes[0], label='Normalized cross-coherence', pad=.01)
    axes[0].set(ylabel='RX1 − RX0 phase (degrees)', ylim=(-185,185), yticks=[-180,-90,0,90,180])
    axes[1].plot(t, coherence, '.', ms=3, label='Fixed GLRT frequency correction')
    axes[1].plot(t, [r['raw_coherence'] for r in rows], '.', ms=2, alpha=.55, label='Uncorrected IQ')
    axes[1].set(ylabel='Cross-coherence', ylim=(0,None))
    axes[1].legend(loc='upper right', fontsize=8)
    for rx, color in [(0,'#397da8'),(1,'#bd763f')]:
        starts=np.array([(int(v['valid_start_counter'])-origin)/RATE for v in selected])
        margins=[float(best[(i,rx)]['fractional_margin']) for i in indices]
        axes[2].scatter(starts+.01, margins, color=color, label=f'RX{rx}', s=30)
        axes[2].hlines(margins, starts, starts+.02, color=color, linewidth=2)
    axes[2].axhline(.025, color='gray', ls='--', label='Comparison gate 0.025')
    axes[2].set(ylabel='GLRT exact − control', xlabel='Seconds from first selected dwell (device counter)')
    axes[2].legend(loc='upper right', fontsize=8)
    for visit in selected:
        begin=(int(visit['valid_start_counter'])-origin)/RATE
        for ax in axes:
            ax.axvline(begin, color='gray', alpha=.35, lw=.7)
            ax.axvspan(begin,begin+.02,color='#74a9cf',alpha=.08)
        axes[0].text(begin+.06,174,visit['visit_index'],ha='center',fontsize=8)
    fig.suptitle(f"Strong paired GLRT segment · CH{selected[0]['channel']} upper · visits {indices[0]}–{indices[-1]}\nscan-fw-32a202b6e55630ec",fontsize=14)
    fig.supxlabel(f'1.6384 ms non-overlapping windows; fixed Δf = {seed:,.3f} Hz from first GLRT pair. No fitted phase offset/rate or gap unwrapping.',fontsize=9)
    for ext in ('png','svg'):
        fig.savefig(OUT/f'phase-vs-time.{ext}',dpi=180)
    duration=(int(selected[-1]['valid_start_counter'])-origin)/RATE+.12
    text=f'''# One strong paired-GLRT track segment

Selected CH{selected[0]['channel']} upper, visits {indices[0]}–{indices[-1]}: {len(indices)} consecutive dwells over {duration:.6f} s. This is the longest qualifying continuous candidate segment under the declared phase-blind rule, not a satellite identification or the full orbital track. Every visit has passing RX0 and RX1 sparse GLRT support. Selection and original candidate coordinates are in [selection.json](selection.json).

![RX phase difference versus time](phase-vs-time.png)

The plotted observable is arg(sum(w · conj(RX0) · RX1 · exp(-j 2π Δf t))), in degrees modulo 360. Δf={seed:.9f} Hz is fixed from the first selected RX1-minus-RX0 physical GLRT coordinates. The same device-counter time origin and correction are used throughout all five dwells. There is no phase-outcome alias search, fitted intercept, rate removal, response normalization, or unwrap across gaps. CSV also retains uncorrected phase and coherence. GLRT frequencies can have symbol-rate ambiguities; this shows the declared branch rather than claiming absolute geometric phase.

All saved IQ in each selected 120 ms dwell is plotted using non-overlapping 16,384-sample Hann-squared averages. Blue shading marks the first 20 ms actually probed by sparse GLRT; that acquisition is not evidence that the remaining 100 ms stays locked. Vertical lines mark dwell starts, with no lines joining phase points across boundaries. Same-target consecutive visits contain short unobserved device-counter gaps; this selection has no intervening different-target dwell. Low-coherence points are retained and their phase is less informative.

Raw chunk SHA-256 hashes were verified before extraction. [Numerical samples](phase-vs-time.csv) and [reproduction script](plot_track.py) are included. This broadband cross-phase can include other energy in the captured band; GLRT association alone does not isolate a unique emitter.
'''
    (OUT/'REPORT.md').write_text(text)
    print(json.dumps({'visits':indices,'duration_s':duration,'seed_hz':seed,'median_coherence':float(np.median(coherence)),'minimum_glrt_margin':min(float(best[(i,rx)]['fractional_margin']) for i in indices for rx in (0,1))},indent=2))


if __name__ == '__main__':
    main()
