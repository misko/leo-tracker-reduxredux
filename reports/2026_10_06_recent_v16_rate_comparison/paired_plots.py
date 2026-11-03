"""Matched within-scan switches; no averaging over unequal cohorts."""
FIELDS=('scan','refinement','model','cone','arm')


def matched(rows,axis,before,after,fixed):
    available=[r for r in rows if r['status']=='complete' and
               all(r[k]==v for k,v in fixed.items())]
    lookup={tuple(r[k] for k in FIELDS):r for r in available}
    if len(lookup)!=len(available):raise ValueError('Duplicate position case')
    pairs=[]
    for key,row in lookup.items():
        if row[axis]!=before:continue
        other=list(key);other[FIELDS.index(axis)]=after
        if tuple(other) in lookup:pairs.append((row,lookup[tuple(other)]))
    return sorted(pairs,key=lambda p:p[0]['scan'])


def plot(rows,destination):
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    contrasts=[('refinement','original','refined',dict(model='V16',cone='off'),
                'Refinement · V16, cones off','Original measurements','Refined measurements'),
               ('model','T1AT','V16',dict(refinement='refined',cone='off'),
                'Position score · refined, cones off','T1-AT','V16'),
               ('cone','off','on',dict(refinement='refined',model='V16'),
                'Cone prior · refined, V16','Cones off','Cones on')]
    fig,axes=plt.subplots(2,3,figsize=(16,10),sharex=True,sharey=True,layout='constrained')
    for row_axes,arm in zip(axes,('fitted-c','zero-c')):
        for ax,(axis,before,after,fixed,title,xlabel,ylabel) in zip(row_axes,contrasts):
            pairs=matched(rows,axis,before,after,dict(fixed,arm=arm))
            good=0;labelled=[]
            for a,b in pairs:
                boundary=a['boundary'] or b['boundary'];converged=a['converged'] and b['converged']
                good+=int(converged and not boundary)
                color='#0072B2' if a['rate_msps']==2.5 else '#D55E00'
                x,y=a['distance_m'],b['distance_m']
                ax.scatter(x,y,c=color,marker='^' if boundary else 'o',s=52,alpha=.85)
                if not converged:ax.scatter(x,y,c='black',marker='x',s=40)
                nearby=any((x-u)**2+(y-v)**2<350**2 for u,v in labelled)
                ax.annotate(a['scan'],(x,y),xytext=(4,-12 if nearby else 4),
                            textcoords='offset points',fontsize=6.5)
                labelled.append((x,y))
            ax.plot([0,4000],[0,4000],color='gray',linestyle='--',linewidth=1)
            ax.set_xlim(-100,4350);ax.set_ylim(-100,4350);ax.set_aspect('equal');ax.grid(alpha=.18)
            ax.set_xlabel(xlabel+' error (m)');ax.set_ylabel(ylabel+' error (m)')
            ax.set_title(f'{title}\n{arm}: {len(pairs)}/16 pairs; {good} converged interior',fontsize=10)
    fig.legend(handles=[Line2D([],[],marker='o',color='#0072B2',linestyle='none',label='2.5 MS/s'),
                        Line2D([],[],marker='o',color='#D55E00',linestyle='none',label='10 MS/s'),
                        Line2D([],[],marker='x',color='black',linestyle='none',label='Either fit unconverged'),
                        Line2D([],[],marker='^',color='gray',linestyle='none',label='Either fit at boundary')],
               loc='outside lower center',ncol=4)
    fig.suptitle('Recent scans · paired position-error comparisons\nBelow diagonal = improved; every point is the same scan before and after',fontsize=16)
    fig.savefig(destination,dpi=150);plt.close(fig)
