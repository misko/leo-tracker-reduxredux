"""Correct zero-based raw receiver metadata and summarize held-out RF results."""

from pathlib import Path
import numpy as np
from probe_ds23_frequency_selective_pilot import OUT,SOURCE
from run_algo01_ds23_sample import ROOT,read,write,sha


def canonical_receiver(raw_index,track):
    receiver=int(track.split('-RX')[1].split('-')[0])
    if receiver not in (1,2) or int(raw_index)!=receiver-1:
        raise ValueError('raw zero-based receiver index differs from canonical track owner')
    return receiver


def main():
    protocol=read(OUT/'protocol.json');evaluation=read(OUT/'evaluation.json')
    if evaluation['protocol_sha256']!=sha(OUT/'protocol.json'):raise ValueError('RF protocol changed')
    for name,expected in protocol['source_sha256'].items():
        if sha(ROOT/'tools'/name)!=expected:raise ValueError('RF inference source changed')
    rows=[]
    for row in evaluation['rows']:
        if row['status']!='complete':raise ValueError('RF pilot has unfinished results')
        receiver=canonical_receiver(row['receiver'],row['track'])
        authority=read(SOURCE/(row['case']+'_tracks.json'))
        track=next(t for t in authority['panel_metadata']['tracks'] if t['key']==row['track'])
        if receiver!=track['receiver']:raise ValueError('receiver does not match sealed graph track')
        rows.append(dict(row,receiver=receiver,original_raw_receiver_index=row['receiver']))
    summary={}
    for rx in (1,2):
        selected=[r for r in rows if r['receiver']==rx]
        summary[str(rx)]=dict(n=len(selected),heldout_improves=sum(r['heldout_relative_error_change']<0 for r in selected),
            median_relative_heldout_error_change=float(np.median([r['heldout_relative_error_change'] for r in selected])),
            median_absolute_CFO_change_from_flat_hz=float(np.median([abs(r['CFO_change_from_flat_hz']) for r in selected])),
            median_absolute_split_CFO_difference_hz={name:float(np.median([abs(r['results'][name]['symbol_split_CFO_difference_hz']) for r in selected])) for name in ('flat','per_tone')},
            boundary_points=sum(any(f['frequency_search_boundary'] for f in r['results']['per_tone']['fits'].values()) for r in selected))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.7))
    for rx,color in [(1,'#197c91'),(2,'#c44c31')]:
        selected=[r for r in rows if r['receiver']==rx]
        axes[0].scatter([r['results']['flat']['symbol_split_CFO_difference_hz'] for r in selected],
            [r['results']['per_tone']['symbol_split_CFO_difference_hz'] for r in selected],label=f'RX{rx}',color=color)
        axes[1].scatter([r['CFO_change_from_flat_hz'] for r in selected],
            [100*r['heldout_relative_error_change'] for r in selected],label=f'RX{rx}',color=color)
    axes[0].plot([-35,35],[-35,35],'k--',lw=.7)
    axes[0].set(xlabel='Flat-channel symbol-split CFO difference (Hz)',ylabel='Per-tone symbol-split CFO difference (Hz)',title='Disjoint symbol estimates')
    axes[1].axhline(0,color='black',lw=.7);axes[1].set(xlabel='CFO change from flat-channel model (Hz)',ylabel='Held-out prediction SSE change (%)',title='Less than zero means better RF prediction')
    for ax in axes:ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Frequency-selective pilot model · 21 saved probes · no satellite or geographic input\nCommon epoch/code rate conditioned on prior RF fit; prediction quality does not prove absolute CFO accuracy')
    fig.tight_layout();fig.savefig(OUT/'corrected_RF_channel_comparison.png',dpi=175);plt.close(fig)
    result=dict(rows=rows,summary=summary,source_evaluation_sha256=sha(OUT/'evaluation.json'),
        evaluator_source_sha256=sha(Path(__file__)),
        correction='Original worker field receiver contains raw zero-based receiver_id. The original 1/2 summary accidentally omitted raw RX index 0 and labeled index 1 as RX1. This corrected summary binds canonical RX1/RX2 to sealed track owners; individual frequency fits are unchanged.',
        real_DS23_accuracy_gain=False)
    write(OUT/'corrected_evaluation.json',result)
    print('CORRECTED_RF_CHANNEL_COMPARISON',summary,flush=True)


if __name__=='__main__':main()
