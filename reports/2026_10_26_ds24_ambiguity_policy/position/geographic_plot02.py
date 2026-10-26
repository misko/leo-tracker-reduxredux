"""Readability-only geographic figure from the already sealed table."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent
OUT=HERE/'geographic'
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    seal=json.loads((OUT/'seal.json').read_bytes())
    for name,digest in seal['files'].items():
        if sha(name)!=digest:raise ValueError('geographic file changed: '+name)
    with (OUT/'outcomes.csv').open() as stream:rows=list(csv.DictReader(stream))
    fig,axes=plt.subplots(1,2,figsize=(10,4.5),layout='constrained')
    for ax,arm in zip(axes,('c0','fitted_c'),strict=True):
        group=[row for row in rows if row['arm']==arm]
        for x,row in enumerate(group):
            if row['final_endpoint_available']=='True':
                error=float(row['raw_position_error_km'])
                ax.bar(x,error,width=.55,color='#333333' if row['method']=='no_addition' else '#b34c32')
                ax.text(x,error,f'{error:.3f}',ha='center',va='bottom',fontsize=9)
            else:ax.text(x,.1,'No final\nendpoint',ha='center',va='bottom',fontsize=9)
        ax.axhline(float(group[0]['original_reference_error_km']),color='#00796b',ls='--',label='Unchanged operational policy')
        ax.set_xticks(range(3),['No addition','Hard 58175','Mixture']);ax.set_xlim(-.6,2.6)
        ax.set_ylim(0,max(float(row['raw_position_error_km'] or 0) for row in group)*1.18)
        ax.set_ylabel('Position error (km)');ax.set_title('c=0' if arm=='c0' else 'fitted c')
        ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('DS24-0011: completed raw diagnostics and exact reference fallback\nAdded-source methods remain unqualified; partial mixture epochs are not scored.',fontsize=10)
    path=OUT/'paired_position_errors02.png';fig.savefig(path,dpi=180);plt.close(fig)
    bindings={str(path):sha(path),str(Path(__file__)):sha(__file__),str(OUT/'seal.json'):sha(OUT/'seal.json'),str(OUT/'outcomes.csv'):sha(OUT/'outcomes.csv')}
    with (OUT/'plot02_seal.json').open('x') as stream:json.dump(dict(files=bindings,new_distance_evaluations=0),stream,indent=2);stream.write('\n')


if __name__=='__main__':main()
