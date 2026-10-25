"""Render sealed ownership/time/RF metadata; does not load source CFO/labels."""
from pathlib import Path
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    seal=json.loads((HERE/'report_seal.json').read_text())
    for name,h in seal['files'].items():assert sha(HERE/name)==h
    data=json.loads((HERE/'inventory.json').read_text())
    rows=sorted((r for r in data['rows'] if r['receiver']=='RX2'),
                key=lambda r:(r['channel'],r['start_s'],r['component']))
    references=data['references']
    assert len(rows)==65 and data['counts']['primary_eligible']==0
    assert sum(r['secondary_noncurved_eligible'] for r in rows)==2
    fig=plt.figure(figsize=(12.4,15.6),layout='constrained')
    gs=fig.add_gridspec(2,1,height_ratios=(5,65),hspace=.025)
    refax=fig.add_subplot(gs[0]);ax=fig.add_subplot(gs[1],sharex=refax)
    ends=[r['end_s'] for r in rows+references];starts=[r['start_s'] for r in rows+references]
    xmin,xmax=min(starts)-3,max(ends)+3
    for i,r in enumerate(references):
        refax.hlines(i,r['start_s'],r['end_s'],color='#7d5ca2',lw=4)
        refax.plot([r['start_s'],r['end_s']],[i,i],'|',color='#7d5ca2',ms=8)
    refax.set(yticks=range(len(references)),
        yticklabels=[f"RX1 CH{r['channel']} · {r['points']} points · {r['rf_hz']/1e9:.6f} GHz" for r in references],
        ylim=(len(references)-.5,-.5),xlim=(xmin,xmax))
    refax.tick_params(axis='x',labelbottom=False)
    refax.set_title('Historical reference intervals only; the 53+85+36+15 RX1 comparisons are not repeated',fontsize=10)
    labels=[]
    for i,r in enumerate(rows):
        occupied=any(r['original_accepted_ID_overlap'].values())
        color='#a3a3a3' if occupied else '#2879ab' if r['canonical_curved'] else '#bf7a20'
        style='-' if r['canonical_curved'] else (0,(2,1.5))
        ax.hlines(i,r['start_s'],r['end_s'],colors=color,linestyles=style,lw=2.1)
        ax.plot([r['start_s'],r['end_s']],[i,i],color=color,marker='|',linestyle='none',ms=4)
        suffix=''
        if r['secondary_noncurved_eligible']:
            ax.axhspan(i-.42,i+.42,color='#fbecd0',zorder=-2)
            ax.plot((r['start_s']+r['end_s'])/2,i,marker='o',ms=7,mfc='none',mec='#6c4206',mew=1.2)
            suffix='  secondary only'
        name=r['component'].split('-')[-2]
        labels.append(f"CH{r['channel']} {name} · n={r['points']}{suffix}")
    ax.set(yticks=range(len(rows)),yticklabels=labels,ylim=(len(rows)-.5,-.5),
        xlabel='Archived scan time (s)',ylabel='Every complete RX2 native owner, sorted by channel and start time')
    ax.tick_params(axis='y',labelsize=7)
    ax.grid(axis='x',color='.9',lw=.6)
    occupied_count=sum(any(r['original_accepted_ID_overlap'].values()) for r in rows)
    unused_curved=sum(not any(r['original_accepted_ID_overlap'].values()) and r['canonical_curved'] for r in rows)
    unused_linear=len(rows)-occupied_count-unused_curved
    legend=[Line2D([0],[0],color='#a3a3a3',lw=3,label=f'Contains old accepted IDs: {occupied_count}'),
        Line2D([0],[0],color='#2879ab',lw=3,label=f'Unused curved: {unused_curved} (no required time support)'),
        Line2D([0],[0],color='#bf7a20',lw=3,ls='--',label=f'Unused noncurved: {unused_linear}'),
        Line2D([0],[0],marker='o',mfc='none',mec='#6c4206',ls='none',label='Secondary time-supported only: 2'),
        Line2D([0],[0],color='.3',lw=2,label='Solid = curved'),
        Line2D([0],[0],color='.3',lw=2,ls='--',label='Dashed = noncurved')]
    fig.legend(handles=legend,loc='outside lower center',ncol=2,frameon=False,fontsize=8.5)
    fig.suptitle('DS24-0013: metadata-only receiver witness availability\n'
        '0 eligible unused curved RX2 sources; 2 noncurved cross-carrier candidates, no RF test or acceptance',fontsize=13)
    for suffix in ('png','pdf'):fig.savefig(HERE/f'availability.{suffix}',dpi=155)
    plt.close(fig)
    payload=dict(files={n:sha(HERE/n) for n in ('plot_availability.py','availability.png','availability.pdf')},
        inventory_report_seal_sha256=sha(HERE/'report_seal.json'),
        counts=dict(old_accepted_overlap=occupied_count,unused_curved=unused_curved,unused_noncurved=unused_linear,
                    primary_eligible=0,secondary_only=2),
        metadata_only=True,CFO_or_candidate_label_fields_read=False,new_RF_scores=0)
    with (HERE/'availability_seal.json').open('x') as f:json.dump(payload,f,indent=2);f.write('\n')


if __name__=='__main__':main()
