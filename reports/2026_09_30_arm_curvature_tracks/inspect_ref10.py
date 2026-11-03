"""Check the reference-10 branch using pre-divergence fits, not server labels."""
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '2026_09_30_arm_fast_tracks/server-baseline/output'
sys.path.insert(0, str(HERE / 'evaluation'))
import compare_membership as m


def main():
    so = m.read_observations(BASE/'server-observations.tsv')
    ao = m.read_observations(BASE/'arm-observations.tsv')
    refs = m.read_tracks(BASE/'server-tracks.tsv', so).values
    arm = m.read_tracks(HERE/'physical-arm-a250.tsv', ao).values
    origin = min(o.start_ns for o in so.values())
    def points(track, observations):
        values = sorted(((observations[p.candidate].center_ns-origin)*1e-9,
                         p.dealiased_cfo_hz) for p in track.points)
        return np.array(values).T
    t, f = points(refs[10], so)
    results = []
    for begin, end in [(36, 48), (38, 50), (40, 52)]:
        select = (t >= begin) & (t <= end)
        coefficients = np.polyfit(t[select]-end, f[select], 2)
        result = dict(fit_start_s=begin, fit_end_s=end, samples=int(sum(select)),
                      fitted_acceleration_hz_s2=float(2*coefficients[0]),
                      fitted_end_rate_hz_s=float(coefficients[1]),
                      fit_rms_hz=float(np.sqrt(np.mean((np.polyval(coefficients,t[select]-end)-f[select])**2))),
                      future_interval_s=[53,61.5], branches={})
        for index in [10,16]:
            tt, ff = points(refs[index], so)
            use = (tt >= 53) & (tt <= 61.5)
            residual = ff[use]-np.polyval(coefficients,tt[use]-end)
            result['branches'][str(index)] = dict(points=int(sum(use)),
                prediction_rms_hz=float(np.sqrt(np.mean(residual**2))))
        results.append(result)
    # Primary display uses the earliest of three checked windows.
    use = (t>=36)&(t<=48)
    c = np.polyfit(t[use]-48, f[use], 2)
    grid = np.linspace(35,65,400)
    spacing = 11.2e9/refs[10].lane.rf_hz/4.4e-6
    fig, (ax, residual_ax) = plt.subplots(2,1,figsize=(13,9),sharex=True,layout='constrained')
    obs = [o for o in so.values() if o.lane == refs[10].lane and
           35 <= (o.center_ns-origin)*1e-9 <= 65]
    ot = np.array([(o.center_ns-origin)*1e-9 for o in obs])
    of = np.array([o.measured_cfo_hz*11.2e9/o.lane.rf_hz for o in obs])
    pred = np.polyval(c,ot-48)
    of += np.round((pred-of)/spacing)*spacing
    ax.scatter(ot,of/1000,s=8,c='gray',alpha=.35,label='All passing server CFO candidates')
    for track, observations, color, label, marker in [
        (refs[10],so,'#1764a0','Server ref #10','o'),
        (refs[16],so,'#9b3ba3','Server ref #16','s'),
        (arm[0],ao,'#d76a10','ARM output #0','.')]:
        tt, ff = points(track,observations)
        mask = (tt>=35)&(tt<=65)
        tt,ff = tt[mask],ff[mask]
        ff += np.round((np.polyval(c,tt-48)-ff)/spacing)*spacing
        ax.plot(tt,ff/1000,marker=marker,markersize=4,lw=.8,color=color,
                markerfacecolor='none' if marker != '.' else color,label=label)
        residual_ax.plot(tt,(ff-np.polyval(c,tt-48))/1000,marker=marker,
                         markersize=4,lw=.8,color=color,markerfacecolor='none',label=label)
    ax.plot(grid,np.polyval(c,grid-48)/1000,'--',color='#23935a',lw=1.5,
            label='Quadratic continuation fitted only at 36–48 s')
    for a in (ax,residual_ax):
        a.axvspan(36,48,color='#23935a',alpha=.08)
        a.axvline(53,color='gray',ls=':',lw=.8)
        a.grid(alpha=.2)
        a.set_xlim(35,65)
    ax.set_ylim(-72,45)
    ax.set_ylabel('Alias-aligned normalized CFO (kHz)')
    ax.legend(fontsize=9)
    residual_ax.axhline(0,color='#23935a',ls='--')
    residual_ax.set_ylim(-2,11)
    residual_ax.set_ylabel('Residual from pre-divergence continuation (kHz)')
    residual_ax.set_xlabel('Seconds from first projected observation')
    fig.suptitle('Ref #10: the server tail departs from the smooth continuation\n'
                 'Channel 1 / RX0 · measured points · ARM follows the branch labeled server ref #16')
    dest=HERE/'longest-missing'
    fig.savefig(dest/'ref10-branch.png',dpi=170)
    fig.savefig(dest/'ref10-branch.pdf')
    plt.close(fig)
    (dest/'ref10-continuation.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__ == '__main__':
    main()
