"""Reporting-only geographic caption clarification; RF outputs unchanged."""

import json
import numpy as np
import report as original


def main():
    root=original.HERE
    previous=original.read(root/'report_seal.json')
    for path,digest in previous['files'].items():
        if original.sha(path)!=digest:raise ValueError('previous reporting artifact changed')
    rows=original.read(root/'evaluation_summary.json')['rows']
    fig,axes=original.plt.subplots(1,2,figsize=(12,5))
    for ax,arm in zip(axes,('c0','fitted_c')):
        selected=[row for row in rows if row['arm']==arm]
        at=np.arange(len(selected))
        ax.bar(at-.18,[row['baseline_error_km'] for row in selected],.36,label='Saved baseline',color='0.6')
        bars=ax.bar(at+.18,[row['diagnostic_error_km'] or 0 for row in selected],.36,label='Diagnostic predictive prior',color='#0072B2')
        for bar,row in zip(bars,selected):
            if not row['original_parent_accepted_IDs_preserved']:
                bar.set_hatch('///');bar.set_alpha(.45)
        ax.set_xticks(at,[row['case'].replace('DS24-','') for row in selected])
        ax.set(title=arm,ylabel='Geographic error (km)');ax.grid(axis='y',alpha=.2)
    axes[0].legend(fontsize=9)
    fig.suptitle('Chronological transfer panel: every attempted outcome retained')
    original.save(fig,'geographic_transfer_caption02',
        'Hatching marks failure to preserve original accepted IDs. All target identities remain unqualified; operational errors equal baseline.\n'
        'Geography was evaluated after RF sealing; four previously exposed same-site scans, no new-location claim.')
    paths=[root/'figures/geographic_transfer_caption02.png',root/'figures/geographic_transfer_caption02.pdf']
    with (root/'report_caption02_seal.json').open('x') as stream:
        json.dump(dict(previous_report_seal_sha256=original.sha(root/'report_seal.json'),
            RF_seal_sha256=original.sha(root/'RF_seal.json'),source_sha256=original.sha(__file__),
            files={str(path):original.sha(path) for path in paths},
            supersedes='geographic_transfer figure caption only; original artifacts preserved'),stream,indent=2)
        stream.write('\n')


if __name__=='__main__':main()
