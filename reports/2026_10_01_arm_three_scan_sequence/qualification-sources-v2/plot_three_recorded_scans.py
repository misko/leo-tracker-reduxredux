"""Scientific scatter plots and stage timings from completed three-scan receipts."""
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    root=Path(__file__).resolve().parents[1];report=root/'reports/2026_10_01_arm_three_scan_sequence'
    results=json.loads((report/'stage-comparison.json').read_text())
    sys.path.insert(0,str(root/'reports/2026_09_30_arm_curvature_tracks/evaluation'))
    import compare_membership as m
    colors={1:'#3264ad',2:'#e58c2f',3:'#27916c',4:'#a354a1'}
    for i,result in enumerate(results):
        d=report/result['session'];out=d/'comparison';arm=report/f'arm-sequence-v1/scan-{i}'
        points=json.loads((out/'plot-points.json').read_text())
        fig,axes=plt.subplots(2,2,figsize=(14,7),sharex=True,sharey=True,layout='constrained')
        for col,label in enumerate(('server','arm')):
            for rx in (0,1):
                ax=axes[rx,col]
                for channel,color in colors.items():
                    rows=[p for p in points[label] if p['passing'] and p['rx']==rx and p['channel']==channel]
                    ax.scatter([p['time'] for p in rows],[p['cfo']/1000 for p in rows],s=3,alpha=.55,color=color,label=f'CH{channel}',rasterized=True)
                ax.set(title=f'{label.upper()} · RX{rx}',ylabel='Measured CFO (kHz)',xlim=(0,301))
                ax.grid(alpha=.15)
                if rx:ax.set_xlabel('Original time from first dwell (s)')
        axes[0,0].legend(ncols=4,fontsize=8)
        fig.suptitle(result['session']+' · passing GLRT candidates · margin ≥0.025')
        fig.savefig(out/'glrt-cfo.png',dpi=160);plt.close(fig)
        so=m.read_observations(d/'server-tracking/server-observations.tsv');ao=m.read_observations(arm/'observations.tsv')
        banks=[m.read_tracks(d/'server-tracking/server-tracks.tsv',so),m.read_tracks(arm/'results/tracks.stdout',ao)]
        origin=json.loads((d/'capture-manifest.json').read_text())['timing']['first_sample_estimate_utc_ns']
        fig,axes=plt.subplots(2,2,figsize=(14,7),sharex=True,sharey=True,layout='constrained')
        for col,(label,bank,observations) in enumerate(zip(('Server','ARM'),banks,(so,ao))):
            for track in bank.values:
                ax=axes[track.lane.receiver,col]
                ax.scatter([(observations[p.candidate].center_ns-origin)/1e9 for p in track.points],
                    [p.dealiased_cfo_hz/1000 for p in track.points],s=5,alpha=.65,
                    color=plt.get_cmap('tab20')(track.index%20),rasterized=True)
            for rx in (0,1):
                ax=axes[rx,col];ax.set(title=f'{label} · RX{rx}',ylabel='Normalized dealiased CFO (kHz)',xlim=(0,301));ax.grid(alpha=.15)
                if rx:ax.set_xlabel('Original sample UTC relative to scan origin (s)')
        fig.suptitle(result['session']+' · actual assigned points, colored by track')
        fig.supxlabel('No fitted straight lines or interpolation across gaps. Alias choices can shift a track vertically.',fontsize=9)
        fig.savefig(out/'tracks.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    x=np.arange(3);width=.18
    for k,name in enumerate(('detector','seeds','tracks','search')):
        axes[0].bar(x+(k-1.5)*width,[r['timings'][name]['cpu_s'] for r in results],width,label=name)
    axes[0].set(xticks=x,xticklabels=['Scan 1','Scan 2','Scan 3'],ylabel='Whole-process CPU seconds',title='ARM CPU cost per recording');axes[0].legend()
    axes[1].bar(x,[r['timings']['downstream']['wall_s'] for r in results],color=['#3264ad','#3264ad','#a2b6d2'])
    axes[1].axhline(300,color='#b53b42',linestyle='--',label='300 s scan cadence')
    axes[1].set(xticks=x,xticklabels=['Scan 1 loaded','Scan 2 loaded','Scan 3 drain'],ylabel='Elapsed seconds',title='Downstream chain under recorded load');axes[1].legend()
    fig.savefig(report/'stage-timing.png',dpi=160);plt.close(fig)
    events=[json.loads(l) for l in (report/'arm-sequence-v1/controller.stdout').read_text().splitlines()]
    origin=events[0]['origin_ns'];starts={}
    fig,axes=plt.subplots(2,1,figsize=(13,6),layout='constrained')
    scan_colors=['#3264ad','#e58c2f','#27916c']
    for event in events:
        if event['kind']=='launch':starts[event['scan'],event['detector']]=event['monotonic_ns']
        if event['kind']=='finish':
            start=starts[event['scan'],event['detector']]
            axes[0].barh(1 if event['detector'] else 0,(event['monotonic_ns']-start)/1e9,
                left=(start-origin)/1e9,height=.6,color=scan_colors[event['scan']],alpha=.8)
    for i,result in enumerate(results):
        d=report/result['session'];capture=json.loads((d/'capture-manifest.json').read_text())['receipt']['events']
        rows=[json.loads(l) for l in (report/f'arm-sequence-v1/scan-{i}/detector.stdout').read_text().splitlines()][:-1]
        xs=[i*300+(e['valid_start_counter']-capture[0]['valid_start_counter'])/2500000 for e in capture]
        axes[1].plot(xs,[r['due_to_finish_ms']/1000 for r in rows],color=scan_colors[i],linewidth=.7,label=f'Scan {i+1}')
        for ax in axes:ax.axvline(i*300,color='gray',linewidth=.6,alpha=.5)
    axes[0].set(yticks=[0,1],yticklabels=['Tracks + positioning','Paced IQ → GLRT'],xlabel='Time from first replay origin (s)',title='Physical ARM job lifetimes')
    axes[1].axhline(5,color='#b53b42',linestyle='--',label='5 s latency acceptance')
    axes[1].set(xlabel='Scheduled dwell arrival time (s)',ylabel='Arrival-to-finish latency (s)',title='Measured dwell latency including queueing');axes[1].legend(ncols=4)
    fig.savefig(report/'arm-cadence.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
