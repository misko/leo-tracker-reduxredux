"""Plot measured recorded-load latency, process overlap and sampled RSS."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path);parser.add_argument('manifest',type=Path)
    args=parser.parse_args();report=args.report
    rows=[json.loads(x) for x in (report/'controller.stdout').read_text().splitlines()]
    header=rows[0];origin=header['origin_ns'];period=header['period_ns']/1e9
    offsets=[int(line.split('\t')[1])/1e9 for line in args.manifest.read_text().splitlines()]
    execution=json.loads((report/'execution.json').read_text())
    complete=execution.get('exit_code')==0
    fig,axes=plt.subplots(3,1,figsize=(12,8),sharex=True,gridspec_kw={'height_ratios':[2,1,1]})
    plotted=False
    for i in range(header['scans']):
        path=report/f'scan-{i}/detector.stdout'
        if not path.is_file():continue
        records=[json.loads(x) for x in path.read_text().splitlines()]
        arrivals=[r for r in records if 'sequence' in r]
        accepted=[r for r in arrivals if r['accepted']]
        x=[i*period+offsets[r['sequence']] for r in accepted]
        axes[0].plot(x,[r['due_to_finish_ms']/1000 for r in accepted],color='#2673b8',lw=.7,
                     label='Arrival to completion' if not plotted else None)
        axes[0].plot(x,[r['queue_ms']/1000 for r in accepted],color='#e58a18',lw=.7,
                     label='Detector queue wait' if not plotted else None)
        rejected=[i*period+offsets[r['sequence']] for r in arrivals if not r['accepted']]
        if rejected:axes[0].scatter(rejected,[0]*len(rejected),color='crimson',marker='x',s=25,label=f'Scan {i+1} rejected dwells')
        plotted|=bool(accepted)
    launches={};end=max(r.get('monotonic_ns',origin) for r in rows)
    for row in rows:
        if row['kind']=='launch':launches[row['scan'],row['detector']]=row
        elif row['kind']=='finish':
            start=launches.pop((row['scan'],row['detector']))
            y=1 if row['detector'] else 0
            axes[1].barh(y,(row['monotonic_ns']-start['monotonic_ns'])/1e9,
                         left=(start['monotonic_ns']-origin)/1e9,height=.5,
                         color=('#2673b8' if y else '#35905c') if row['exit_code']==0 else 'crimson',alpha=.7)
    for row in launches.values():
        axes[1].barh(1 if row['detector'] else 0,(end-row['monotonic_ns'])/1e9,
                     left=(row['monotonic_ns']-origin)/1e9,height=.5,color='crimson',alpha=.3,hatch='//')
    memory=[r for r in rows if r['kind']=='memory']
    axes[2].plot([(r['monotonic_ns']-origin)/1e9 for r in memory],
                 [r['process_tree_rss_kib']/1024 for r in memory],color='#7554a3',lw=1)
    axes[0].set_ylabel('Seconds');axes[0].legend(loc='upper right',fontsize=8)
    axes[1].set_yticks([0,1],['Downstream','Detector']);axes[1].set_ylim(-.7,1.7)
    axes[2].set_ylabel('Sampled RSS\nMiB');axes[2].set_xlabel('Seconds from first scan origin')
    for ax in axes:
        for i in range(header['scans']+1):ax.axvline(i*period,color='gray',ls=':',lw=.6)
        ax.grid(axis='y',alpha=.2)
    axes[-1].set_xlim(-10,(end-origin)/1e9+10)
    fig.suptitle('Repeated DS9 recorded load — '+('execution completed; see numerical evaluation' if complete else 'failed / cancelled execution'))
    fig.text(.01,.01,'Detector bars include initialization lead and final drain. First scan and final downstream drain have different contention.\nRSS sums shared pages and samples may miss peaks. Repeated recording; no live-RF or longer-history claim.',fontsize=8)
    fig.tight_layout(rect=(0,.065,1,.95));fig.savefig(report/'cadence.png',dpi=150);fig.savefig(report/'cadence.pdf')


if __name__=='__main__':main()
