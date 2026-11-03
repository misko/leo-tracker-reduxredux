"""Read-only, fixed-membership identity screen for tracks lasting >=70 seconds."""
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT.parent/'2026_10_02_multiscan_localization'),
                str(ROOT.parent/'2026_10_02_localization_benchmark')]


def run():
    from all_visible_bank import load_expanded_scan
    from finite_set_fit import assert_snapshot_unchanged, snapshot_files
    from finite_set_likelihood import circular_residual
    from rf_calibration_diagnostic import rf_features
    from scipy.optimize import minimize_scalar
    from satellite65745_identity_search import local_minima
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    source = ROOT/'later-tle-timing-aligned-v2/receipt.json'
    receipt = json.loads(source.read_text())
    tracks = sorted([t for t in receipt['tracks'] if np.ptp(t['time_s']) >= 70],
                    key=lambda t: -np.ptp(t['time_s']))
    output = ROOT/'long-track-identity-audit'
    output.mkdir(exist_ok=False)
    hashes = snapshot_files([__file__, source])
    results = []
    fig, axes = plt.subplots(len(tracks), 1, figsize=(13, 3*len(tracks)))
    loaded = {}
    for index, track in enumerate(tracks):
        started = time.monotonic()
        session = track['session']
        if session not in loaded:
            profile_path = ROOT/'pruned-position-profile-grid'/f'{session}.json'
            archive_path = ROOT/'tle-doppler-overlay'/f'{session}-plot-data.npz'
            profile = json.loads(profile_path.read_text())
            hashes.update(profile['source_hashes'])
            hashes.update(snapshot_files([profile_path, archive_path]))
            assert_snapshot_unchanged(hashes)
            data = load_expanded_scan(session)
            archive = np.load(archive_path)
            fit = next(p['best'] for p in profile['positions'] if p['label']=='truth')
            _, features = rf_features(data.rf, data.receiver, False)
            rf = (features @ np.asarray(fit['rf_coefficient_hz_per_ghz'])).ravel()
            loaded[session] = data, archive, rf
        data, archive, rf = loaded[session]
        rows = np.asarray(track['rows'])
        factor = 11.085e9/data.rf[rows]
        parameters = archive['parameters'].copy()
        satellites = np.arange(len(data.numbers))
        paired_rows = np.broadcast_to(rows, (len(satellites), len(rows)))
        paired_satellites = np.broadcast_to(satellites[:, None], paired_rows.shape)
        offsets = np.linspace(-10, 10, 201)
        costs = np.empty((len(satellites), len(offsets)))
        for j, offset in enumerate(offsets):
            parameters[6:] = offset
            prediction, visible = data.predict(parameters, paired_rows, paired_satellites)
            residual = circular_residual(data.measured[rows], prediction+rf[rows])*factor
            costs[:, j] = np.mean(np.where(visible, residual**2, 1e12), axis=1)
        # Refine every sampled local minimum, not just the lowest grid sample.
        candidates = []
        for satellite, number in enumerate(data.numbers):
            def evaluate(offset, details=False):
                parameters[6+satellite] = offset
                prediction, visible = data.predict(parameters, rows, np.full(len(rows), satellite))
                residual = circular_residual(data.measured[rows], prediction+rf[rows])*factor
                cost = float(np.mean(np.where(visible, residual**2, 1e12)))
                return (cost, residual, visible) if details else cost
            best = int(np.argmin(costs[satellite]))
            tau, cost = float(offsets[best]), float(costs[satellite,best])
            for j in local_minima(costs[satellite]):
                lo, hi = offsets[max(0,j-1)], offsets[min(len(offsets)-1,j+1)]
                if lo == hi: continue
                result = minimize_scalar(evaluate, bounds=(lo,hi), method='bounded',
                                         options={'xatol':1e-6,'maxiter':32})
                if result.fun < cost: tau, cost = float(result.x), float(result.fun)
            _, residual, visible = evaluate(tau, True)
            candidates.append(dict(satellite=int(number), timing_s=tau,
                rms_hz=float(np.sqrt(np.mean(residual**2))), all_visible=bool(np.all(visible)),
                boundary_hit=bool(abs(tau)>9.999),
                first_half_rms_hz=float(np.sqrt(np.mean(residual[:len(rows)//2]**2))),
                second_half_rms_hz=float(np.sqrt(np.mean(residual[len(rows)//2:]**2)))))
        candidates.sort(key=lambda c:(not c['all_visible'],c['rms_hz']))
        target = next(c for c in candidates if c['satellite']==track['catalog_number'])
        alternatives = [c for c in candidates if c['all_visible'] and c['satellite']!=track['catalog_number']]
        t = np.asarray(track['time_s'])
        r = dict(scan=track['scan'],satellite=track['catalog_number'],receiver=track['receiver'],
                 duration_s=float(np.ptp(t)),points=len(rows),target=target,
                 candidates=candidates,old_stats=track['old_stats'],latest_stats=track['later_stats'],
                 maximum_gap_s=float(np.max(np.diff(np.sort(t)))),elapsed_s=time.monotonic()-started)
        results.append(r)
        ax=axes[index]
        ax.scatter(t,track['old_residual_hz'],s=10,label='Original TLE / sealed fit',alpha=.65)
        ax.scatter(t,track['later_residual_hz'],s=10,label='Latest available TLE / same fit freedoms',alpha=.65)
        ax.axhline(0,color='gray',lw=.8)
        ax.set_title(f"{track['scan']} · {track['catalog_number']} / RX{track['receiver']} · {np.ptp(t):.1f} s | "
                     f"Timing-refit target {target['rms_hz']:.1f} Hz; best other {alternatives[0]['satellite']}: "
                     f"{alternatives[0]['rms_hz']/1000:.2f} kHz")
        ax.set_ylabel('Residual (Hz)');ax.grid(alpha=.2)
        print(json.dumps({k:v for k,v in r.items() if k!='candidates'}),flush=True)
    axes[0].legend(fontsize=9);axes[-1].set_xlabel('Receive time (s)')
    fig.suptitle('Longest tracks: residual structure is not by itself evidence of a wrong satellite')
    fig.tight_layout(rect=(0,0,1,.98));fig.savefig(output/'residuals.png',dpi=160)
    assert_snapshot_unchanged(hashes)
    result=dict(tracks=results,source_hashes=hashes,scope=(
        'Fixed final GLRT rows; all candidates use ORIGINAL archived TLE bank and original RX/RF calibration. '
        'Equal-point RMS normalized to 11.085 GHz. Absolute satellite timing +/-10s, 0.1s grid and '
        'refinement of all sampled minima; no candidate offset/slope or membership changes. '
        'Aliases permitted as in original likelihood. Alternatives must be visible at every point. '
        'Conditional on selected observations, reference location and bank coverage; not independent identity proof. '
        'Latest residuals plotted for context only, not mixed into candidate ranking.'))
    (output/'receipt.json').write_text(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':
    run()
