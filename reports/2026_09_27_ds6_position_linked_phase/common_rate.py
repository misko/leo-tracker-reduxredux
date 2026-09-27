"""Training-only shared receiver rate, preserving free per-source phases."""
import json
import hashlib
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

HERE = Path(__file__).resolve().parent


def fit_rate(t, z, labels):
    """Profile independent circular intercepts; only the rate is shared.

    The +/-375 Hz interval is the principal alias interval for 750 Hz pilots.
    Equal phasor weights prevent source amplitude from choosing the result.
    """
    modes = np.unique(labels)
    def loss(f):
        rotated = z * np.exp(-2j*np.pi*f*t)
        return -sum(abs(rotated[labels == m].sum()) for m in modes)
    grid = np.linspace(-375., 375., 151)
    k = int(np.argmin([loss(f) for f in grid]))
    candidates = [grid[k]]
    lo, hi = grid[max(0,k-1)], grid[min(len(grid)-1,k+1)]
    candidates.append(minimize_scalar(loss, bounds=(lo,hi),method='bounded').x)
    rate = min(candidates,key=loss)
    intercepts = {int(m): float(np.angle(np.sum(
        z[labels==m]*np.exp(-2j*np.pi*rate*t[labels==m])))) for m in modes}
    return float(rate), intercepts


def estimate(data, shared):
    fit, evaluation = data['fit'], data['evaluation']
    labels = fit['s'].astype(int)
    rates, intercepts = {}, {}
    for mode_set in [np.unique(labels)] if shared else [[m] for m in np.unique(labels)]:
        mask = np.isin(labels,mode_set)
        rate, phases = fit_rate(fit['t'][mask],fit['z'][mask],labels[mask])
        rates.update({int(m):rate for m in mode_set})
        intercepts.update(phases)
    held_phases, errors = {}, []
    for m in np.unique(labels):
        take = evaluation['s'].astype(int)==m
        rotated = evaluation['z'][take]*np.exp(-2j*np.pi*rates[int(m)]*evaluation['t'][take])
        held_phases[int(m)] = float(np.angle(np.sum(rotated)))
        errors.extend(np.angle(rotated*np.exp(-1j*intercepts[int(m)])).tolist())
    return dict(rates_hz=rates,train_dd=float(np.angle(np.exp(1j*(intercepts[1]-intercepts[-1])))),
                evaluation_dd=float(np.angle(np.exp(1j*(held_phases[1]-held_phases[-1])))),
                held_frame_errors_rad=errors)


def main():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore
    sys.path.insert(0,str(HERE.parent/'2026_09_27_ds6_dwell_phase'))
    from experiment import frames
    plan=json.loads((HERE/'plan.json').read_text())
    replay=json.loads((HERE/'replay.json').read_text())
    assert replay['complete']
    assert replay['plan_sha256']==hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest()
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
    cap=store.inspect(plan['session_id']);assert cap.manifest_sha256==plan['input_manifest_sha256']
    rows=[]
    with store.reader(plan['session_id'],expected=cap) as reader:
        for v in plan['selected']:
            selected=[r for r in replay['rows'] if r['visit']==v['visit'] and r['group']==v['group'] and r['original']['both_qualified']]
            event,raw=reader.read_visit_ci16(v['visit'])
            assert event.event.valid_start_counter==v['valid_start_counter']
            iq=raw[...,0].astype(float)+1j*raw[...,1].astype(float)
            for row in selected:
                start=round(plan['rate_hz']*row['start_ms']/1000)
                n=round(plan['rate_hz']*plan['width_ms']/1000)
                data=frames(iq[start:start+n],v,plan['rate_hz'],start,row['original'])['data']
                rows.append(dict(visit=v['visit'],group=v['group'],partition=v['partition'],time_s=row['time_s'],start_ms=row['start_ms'],
                                 shared=estimate(data,True),independent=estimate(data,False)))
    store.close()
    summary=[]
    for g in plan['selected_groups']:
        selected=[r for r in rows if r['group']==g['group']]
        item=dict(group=g['group'],windows=len(selected))
        for arm in ['shared','independent']:
            errors=[e for r in selected for e in r[arm]['held_frame_errors_rad']]
            dwells=[]
            for visit in g['selected_visits']:
                rr=[r for r in selected if r['visit']==visit]
                dd=np.array([r[arm]['evaluation_dd'] for r in rr])
                dwells.append(dict(visit=visit,n=len(rr),R=float(abs(np.mean(np.exp(1j*dd)))),phase=float(np.angle(np.mean(np.exp(1j*dd))))))
            item[arm]=dict(held_frame_rms_deg=float(np.degrees(np.sqrt(np.mean(np.square(errors))))),dwells=dwells)
        summary.append(item)
    out=dict(scope='Post-result prototype; same qualified windows and disjoint fit/evaluation samples. Free source intercepts, common rate only.',
             plan_sha256=hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest(),
             replay_sha256=hashlib.sha256((HERE/'replay.json').read_bytes()).hexdigest(),
             rate_alias_interval_hz=[-375,375],rows=rows,summary=summary)
    (HERE/'common-rate-results.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in s.items() if k not in ['shared','independent']} | {a:s[a]['held_frame_rms_deg'] for a in ['shared','independent']} for s in summary],indent=2))


if __name__=='__main__':
    main()
