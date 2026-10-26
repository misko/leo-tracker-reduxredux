"""Preparation figure and counts only; no target detections or RF scoring."""
from collections import Counter
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import study

HERE=Path(__file__).resolve().parent


def main():
    blocks=study.read(HERE/'blocks.json')['blocks'];panel=study.read(HERE/'panel.json')
    packets=study.read(HERE/'prediction_packets.json')['rows']
    source=study.read(HERE/'predictions.json')['rows'];lookup={r['header']['prediction_id']:r for r in packets}
    fig,axes=plt.subplots(4,1,figsize=(10,7),layout='constrained',sharex=True)
    summaries=[]
    for ax,block in zip(axes,blocks):
        slots=[s for s in panel['slots']if block['block_id']in s['block_ids']]
        counts=Counter()
        for slot in slots:
            for cell in slot['cells']:
                h=cell['header'];row=lookup[h['prediction_id']];available=bool(row['forecast']['modes'])
                counts['available'if available else'no_donor']+=1
                x=(h['start_counter']+100000-block['center_counter'])/h['sample_rate_hz']
                ax.scatter(x,h['receiver_id'],c='#2166ac'if available else'#e08214',s=13,marker='o'if available else'x')
        ax.axvline(0,c='.4',ls='--',lw=.7);ax.set(yticks=[0,1],yticklabels=['RX0','RX1'],ylim=(-.4,1.4),
            title=f"{block['case']} CH{block['channel']}, nomination RX{block['nominating_receiver_id']}: {len(slots)} paired visits, {counts['available']}/{2*len(slots)} forecast cells")
        summaries.append(dict(block_id=block['block_id'],case=block['case'],channel=block['channel'],
            nominating_receiver_id=block['nominating_receiver_id'],paired_windows=len(slots),receiver_cells=2*len(slots),
            forecast_available=counts['available'],no_donor=counts['no_donor'],seed_observation_id=block['seed_observation_id']))
    axes[-1].set(xlabel='Native midpoint seconds from RF-selected seed',xlim=(-12.3,12.3))
    fig.suptitle('Exact R01 earlier-only forecast availability; blue available / orange no donor\nNo raw target evidence or new scoring in this preparation')
    for ext in ['png','pdf']:fig.savefig(HERE/f'expansion_panel.{ext}',dpi=180,bbox_inches='tight')
    study.write(HERE/'summary.json',dict(blocks=summaries,paired_windows=263,receiver_cells=526,
        forecast_statuses=dict(Counter(r['forecast']['status']for r in source)),
        overlap_original_sparse_paired_windows=panel['overlap_original_sparse_paired_windows'],
        new_paired_source_windows=263-panel['overlap_original_sparse_paired_windows'],raw_IQ_reads=0,scoring_calls=0,
        exact_R01_predictor_sha256=study.sha(study.R01/'predictor.py'),R02_forecasts_used=False))


if __name__=='__main__':main()
