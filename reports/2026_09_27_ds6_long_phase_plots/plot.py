"""Plot held-sample pilot phases without smoothing or cross-visit unwrapping."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode(data):
    return {k: np.array(v['real'])+1j*np.array(v['imag']) if isinstance(v,dict)
            else np.array(v) for k,v in data.items()}


def main():
    protocol = json.loads((HERE/'protocol.json').read_text())
    loaded = {}
    for rec in protocol['selected']:
        sid = rec['session_id']
        plan = json.loads((HERE/f'{sid}-plan.json').read_text())
        replay = json.loads((HERE/f'{sid}-replay.json').read_text())
        assert replay['complete'] and replay['plan_sha256'] == sha(HERE/f'{sid}-plan.json')
        assert plan['protocol_sha256'] == sha(HERE/'protocol.json')
        frames = json.loads((HERE/f'{sid}-frames.json').read_text())
        cache = {(r['group'],r['visit'],r['start_ms']):r['frame'] for r in frames}
        assert len(replay['rows']) == 6*len(plan['selected'])
        loaded[sid] = (plan,replay,cache)
    fig,axes = plt.subplots(3,1,figsize=(12,11),constrained_layout=True)
    rawfig,rawaxes = plt.subplots(3,1,figsize=(12,11),constrained_layout=True)
    groups=[]; table=[]; windows=[]
    colors = {2:'#1677b8',4:'#a143af'}
    for index,(g,ax,rawax) in enumerate(zip(protocol['groups'],axes,rawaxes),1):
        sid = g['session_id']; plan,replay,cache = loaded[sid]
        visits = [v for v in plan['selected'] if v['group']==g['group']]
        origin = min(v['valid_start_counter'] for v in visits)
        channel = visits[0]['channel']; color=colors[channel]
        rows = [r for r in replay['rows'] if r['group']==g['group']]
        qualified = [r for r in rows if r['original']['both_qualified']]
        points=[]
        for row in qualified:
            frame=cache[g['group'],row['visit'],row['start_ms']]
            data=decode(frame['data']['evaluation']); phases=[]
            for source in [-1,1]:
                take=data['s']==source; rate=row['shared']['rates_hz'][str(source)]
                z=data['z'][take]*np.exp(-2j*np.pi*rate*data['t'][take])
                phases.append(float(np.angle(np.mean(z))))
            dd=float(np.angle(np.exp(1j*(phases[1]-phases[0]))))
            assert abs(np.angle(np.exp(1j*(dd-row['shared']['evaluation_dd']))))<1e-10
            t=row['time_s']-(origin-plan['timing']['session_start_device_sample_counter'])/plan['rate_hz']
            point=dict(pair=index,session_id=sid,group=g['group'],visit=row['visit'],
                time_s=t,start_ms=row['start_ms'],phase_a_deg=float(np.degrees(phases[0])),
                phase_b_deg=float(np.degrees(phases[1])),dd_deg=float(np.degrees(dd)))
            points.append(point);windows.append(point)
        summaries=[]
        for visit in visits:
            pp=[p for p in points if p['visit']==visit['visit']]
            t=(visit['valid_start_counter']-origin)/plan['rate_hz']+.056
            z=np.mean([np.exp(1j*np.radians(p['dd_deg'])) for p in pp]) if pp else None
            R=float(abs(z)) if pp else None
            item=dict(pair=index,session_id=sid,visit=visit['visit'],channel=channel,
                time_s=t,qualified_windows=len(pp),phase_deg=float(np.degrees(np.angle(z))) if pp else None,
                R=R,window_circular_sd_deg=float(np.degrees(np.sqrt(-2*np.log(max(R,1e-30))))) if pp else None)
            summaries.append(item);table.append(item)
            if pp:
                # Error bars summarize window dispersion, not a physical confidence interval.
                # Draw all equivalent copies so the +/-180 boundary clips correctly.
                for turn in [-360,0,360]:
                    ax.errorbar(t,item['phase_deg']+turn,yerr=item['window_circular_sd_deg'],
                        fmt='o',color=color,capsize=3,markersize=5,alpha=.95)
            else:
                ax.scatter(t,-174,marker='x',c='crimson',s=40)
        ax.scatter([p['time_s'] for p in points],[p['dd_deg'] for p in points],
                   s=13,c=color,alpha=.25,label='Qualified 7 ms windows')
        ax.plot([],[],color=color,marker='o',linestyle='',label='Visit circular mean; bars = window spread')
        if any(not v['qualified_windows'] for v in summaries):
            ax.scatter([],[],marker='x',c='crimson',label='No qualified window (bottom row)')
        for source,label,c,marker in [('a','Track A','#1677b8','o'),('b','Track B','#dd8123','x')]:
            rawax.scatter([p['time_s'] for p in points],[p[f'phase_{source}_deg'] for p in points],
                          c=c,s=18,alpha=.6,marker=marker,label=label)
        title=f'Pair {index} · {sid} · channel {channel} · {g["span_s"]:.1f} s · {g["support"]} joint-support visits'
        ax.set(title=title,ylabel='Double difference B − A (°)',ylim=(-180,180),yticks=[-180,-90,0,90,180])
        rawax.set(title=title,ylabel='RX1 − RX0 phase (°)',ylim=(-190,190),yticks=[-180,-90,0,90,180])
        for a in [ax,rawax]:
            a.set_xlabel('Time from first selected visit (seconds)');a.grid(alpha=.2);a.legend(loc='upper right',fontsize=8)
        if index == 2:
            ax.legend(loc='center left',fontsize=8)
        errors={arm:float(np.degrees(np.sqrt(np.mean([np.mean(np.square(r[arm]['held_frame_errors_rad'])) for r in qualified])))) if qualified else None for arm in ['shared','independent']}
        controls=[c for c in replay['controls'] if c['group']==g['group']]
        groups.append(dict(**g,pair=index,channel=channel,track_ids=[m['rx0_track_id'] for m in visits[0]['modes']],
            qualified_windows=len(qualified),examined_windows=len(rows),usable_visits=sum(bool(v['qualified_windows']) for v in summaries),
            median_R=float(np.median([v['R'] for v in summaries if v['R'] is not None])) if qualified else None,
            controls=len(controls),controls_qualified=sum(c['both_qualified'] for c in controls),
            held_frame_rms_deg=errors,visits=summaries))
    fig.suptitle('Shared-rate pilot phase estimator: receiver-common phase cancelled\nWrapped measurements; no smoothing, detrending or phase connection across visits',fontsize=14)
    rawfig.suptitle('Individual track RX phase differences at each window midpoint\nCommon receiver phase remains; points are not connected across gaps',fontsize=14)
    fig.savefig(HERE/'phase_difference.png',dpi=170);fig.savefig(HERE/'phase_difference.svg')
    svg=HERE/'phase_difference.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    rawfig.savefig(HERE/'individual_rx_phase.png',dpi=170)
    for filename,records in [('visits.csv',table),('windows.csv',windows)]:
        with (HERE/filename).open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]),lineterminator='\n');writer.writeheader();writer.writerows(records)
    result=dict(complete=True,protocol_sha256=sha(HERE/'protocol.json'),groups=groups,
                clipped_rows=sum(a['clipped_rows'] for _,r,_ in loaded.values() for a in r['audits']))
    (HERE/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps([{k:v for k,v in g.items() if k not in ['visits','selected_visits','group','track_ids']} for g in groups],indent=2))


if __name__=='__main__':
    main()
