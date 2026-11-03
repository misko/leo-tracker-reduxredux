"""Summarize fitted subset memberships without implying continuous coverage."""
from pathlib import Path
import csv
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / 'exhaustive-subset'


def main():
    summary = []
    for scan in 'AB':
        receipt = json.loads((OUT/f'{scan}-receipt.json').read_text())
        original = set(receipt['baseline']['catalog_numbers'])
        rows = list(csv.DictReader((OUT/f'{scan}-fitted-c-assignments.csv').open()))
        old = list(csv.DictReader((HERE/'baseline'/f'{scan}-assignments.csv').open()))
        keys = {(int(r['catalog_number']), int(r['receiver'])) for r in rows+old}
        keys = sorted(keys, key=lambda key: min(float(r['time_s']) for r in rows+old if (int(r['catalog_number']),int(r['receiver']))==key))
        fig, ax = plt.subplots(figsize=(13, max(6, .44*len(keys)+2)))
        for y, (sat, rx) in enumerate(keys):
            matching = [r for r in rows if int(r['catalog_number'])==sat and int(r['receiver'])==rx]
            initial = [float(r['time_s']) for r in old if int(r['catalog_number'])==sat and int(r['receiver'])==rx]
            times = [float(r['time_s']) for r in matching]
            ax.scatter(initial, np.full(len(initial),y+.12), c='.7', marker='|', s=35)
            ax.scatter(times, np.full(len(times),y-.12), c='#0072B2' if sat in original else '#D55E00', s=10)
            if matching:
                summary.append(dict(scan=scan,catalog_number=sat,receiver=rx,new=sat not in original,
                                    assigned_groups=len(matching), start_s=min(times), end_s=max(times),
                                    span_s=max(times)-min(times),
                                    rms_normalized_hz=float(np.sqrt(np.mean([float(r['residual_hz'])**2 for r in matching])))))
        ax.set_yticks(range(len(keys)), [f'{sat} / RX{rx}'+('  NEW' if sat not in original else '') for sat,rx in keys])
        ax.invert_yaxis()
        ax.set_xlim(0,300)
        ax.set_xlabel('Receive time since capture start (s)')
        ax.grid(axis='x', alpha=.2)
        ax.set_title(f'DS13 scan {scan} · full-bank subset fit\n{len(receipt["catalog_numbers"])} selected satellites; ≥10 exclusive probe groups per satellite')
        ax.legend(handles=[Line2D([],[],color='.7',marker='|',ls='',label='Previous baseline assignments'),
                           Line2D([],[],color='#0072B2',marker='o',ls='',label='Refitted existing satellite'),
                           Line2D([],[],color='#D55E00',marker='o',ls='',label='Newly admitted satellite')],
                  loc='upper center',bbox_to_anchor=(.5,-.1),ncol=3)
        fig.text(.5,.012,'Individual assigned peaks shown—not continuous tracks. Fixed known position; in-sample fitted-c result.',ha='center',fontsize=9)
        fig.tight_layout(rect=(0,.07,1,1))
        fig.savefig(OUT/f'{scan}-membership.png',dpi=160)
        plt.close(fig)
    with (OUT/'tracks.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)


if __name__ == '__main__':
    main()
