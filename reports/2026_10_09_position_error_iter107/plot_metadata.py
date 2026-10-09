"""Render source coverage from saved metadata only."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def main():
    plan=json.loads((HERE/'source-plan.json').read_text());names=['DS16','DS17','DS18','POST18-development'];members=[];blocked=[];documents=[]
    for name in names:
        rows=[m for m in plan['members'] if m.get('dataset',m['member'].get('dataset'))==name]
        members.append(len(rows));documents.append(sum(len(m['sources']) for m in rows))
        blocked.append(sum(any(any(k!='application/regional_position_report.py' for k in s['source_compatibility']['current_source_mismatches']) for s in m['sources']) for m in rows))
    fig,axs=plt.subplots(1,2,figsize=(10,4.2));x=list(range(4));labels=['DS16','DS17','DS18','Newer dev.']
    axs[0].bar(x,members,color='#245e78');axs[0].set_title('Full 193-member source coverage');axs[0].set_ylabel('Recordings')
    compatible=[a-b for a,b in zip(members,blocked)]
    axs[1].bar(x,compatible,color='#245e78',label='No detected numerical source mismatch');axs[1].bar(x,blocked,bottom=compatible,color='#d48039',label='Numerical source mismatch; reuse unapproved');axs[1].set_title('Source compatibility is a metadata gate');axs[1].legend(fontsize=8)
    for ax in axs:ax.set_xticks(x,labels);ax.spines[['top','right']].set_visible(False);ax.set_ylim(0,76)
    for i in x:axs[0].text(i,members[i]+.5,f'{members[i]} members\n{documents[i]} docs',ha='center',fontsize=9);axs[1].text(i,members[i]+.5,str(members[i]),ha='center')
    fig.text(.5,.01,'489 metadata documents; 49 historical failed-region bootstrap receipts verified. No fits or accuracy claim.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.04,1,1));fig.savefig(HERE/'source_coverage.png',dpi=160);plt.close(fig)


if __name__=='__main__':main()
