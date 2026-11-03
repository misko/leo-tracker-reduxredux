"""Reference-location/receive-time diagnostic sky; no inference or satellite ID."""
import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from mark import geometry_flags

HERE=Path(__file__).resolve().parent
COLORS=('#2477B3','#7953A8','#E8922A','#C92836')

def sky(unit):
    unit=np.asarray(unit);h=np.hypot(unit[...,0],unit[...,1]);radius=2/np.pi*np.arctan2(h,unit[...,2]);factor=np.divide(radius,h,out=np.zeros_like(h),where=h>1e-12)
    return unit[...,:2]*factor[...,None]

def boundary(theta,frame,rx):
    a,b,_,*roll=theta;up,az,bore=frame;c,s=np.cos(roll[rx]),np.sin(roll[rx]);e1=c*up+s*az;e2=-s*up+c*az;phase=np.linspace(0,2*np.pi,361)
    u=bore+np.tan(a)*np.cos(phase)[:,None]*e1+np.tan(b)*np.sin(phase)[:,None]*e2
    return u/np.linalg.norm(u,axis=1)[:,None]

def plot(case):
    with np.load(HERE/('plotdata-'+case+'.npz')) as data:
        theta,frames,receiver,times=data['theta'],data['frames'],data['receiver'],data['times_s'];fig,axes=plt.subplots(2,2,figsize=(12,12))
        for row,option in enumerate(('control','cone100')):
            unit,weights,numbers=data[option+'_unit'],data[option+'_weights'],data[option+'_numbers'];flags=geometry_flags(unit,theta,frames);xy=sky(unit)
            for rx in (0,1):
                ax=axes[row,rx];mask=receiver==rx;phase=np.linspace(0,2*np.pi,361);ax.plot(np.cos(phase),np.sin(phase),color='.3',lw=1)
                for radius in (.333333,.666667):ax.plot(radius*np.cos(phase),radius*np.sin(phase),color='.8',lw=.6)
                ax.axhline(0,color='.85',lw=.7);ax.axvline(0,color='.85',lw=.7);ax.scatter([0],[0],color='.3',s=12)
                edge=boundary(theta,frames[rx],rx);edge_xy=sky(edge);edge_xy[edge[:,2]<0]=np.nan;ax.plot(*edge_xy.T,color='black',lw=1.6,label='Frozen empirical ellipse')
                bore=sky(frames[rx,2]);ax.scatter(*bore,marker='*',s=180,c='black',zorder=8)
                candidates=[]
                for j,number in enumerate(numbers):
                    mass=float(weights[mask,j].sum())
                    if mass<10:continue
                    eligible=mask&(weights[:,j]>=.25);inds=np.flatnonzero(eligible);inds=inds[np.argsort(times[inds])]
                    if not len(inds):continue
                    categories=np.zeros(len(inds),int);categories[flags['opposite_east_west'][inds,j,rx]]=1;categories[flags['outside_empirical_ellipse'][inds,j,rx]]=2;categories[flags['behind_nominal_boresight'][inds,j,rx]]=3
                    # Thin observed segments; breaks prevent lines over unsupported gaps.
                    coords=xy[inds,j].copy();coords/=np.maximum(1,np.linalg.norm(coords,axis=1))[:,None];below=flags['below_horizon'][inds,j,rx];gaps=np.diff(times[inds])>5
                    for start,end in zip(np.r_[0,np.flatnonzero(gaps)+1],np.r_[np.flatnonzero(gaps)+1,len(inds)]):
                        ax.plot(coords[start:end,0],coords[start:end,1],color='.55',lw=.5,alpha=.5,zorder=1)
                    ax.scatter(coords[~below,0],coords[~below,1],c=[COLORS[k] for k in categories[~below]],s=7,alpha=.85,zorder=3)
                    ax.scatter(coords[below,0],coords[below,1],marker='x',color='black',s=22,linewidths=.9,zorder=5)
                    flagged=flags['opposite_east_west'][:,j,rx]|flags['outside_empirical_ellipse'][:,j,rx]|flags['behind_nominal_boresight'][:,j,rx]|flags['below_horizon'][:,j,rx];flagmass=float(weights[mask,j]@flagged[mask]);peak=np.argmax(weights[inds,j]);candidates.append((flagmass,mass,int(number),coords[peak]))
                # Uniform right-side gutter guarantees that numeric IDs never overlap.
                labels=sorted(sorted(candidates,key=lambda c:(c[0],c[1]),reverse=True)[:6],key=lambda c:c[3][1],reverse=True)
                for (_,_,number,point),height in zip(labels,np.linspace(.80,-.80,len(labels))):
                    ax.annotate(str(number),point,xytext=(1.10,height),textcoords='data',fontsize=9,ha='left',va='center',arrowprops=dict(arrowstyle='-',color='.45',lw=.55),bbox=dict(facecolor='white',alpha=.85,edgecolor='none',pad=.7))
                ax.set(xlim=(-1.08,1.43),ylim=(-1.08,1.08),aspect='equal',title=f'{option} fitted-c · RX{rx} '+('west' if rx==0 else 'east'),xlabel='West ← east-coordinate → East',ylabel='South ← north-coordinate → North' if rx==0 else '')
        local_time={'1939':'12:39 PDT','2139':'14:39 PDT'}[case]
        fig.suptitle(f'Oct 6 {local_time} · Candidate satellite hypotheses\nKnown-reference position / receive-time geometry DIAGNOSTIC',fontsize=15)
        legend=[Line2D([],[],marker='o',ls='',color=COLORS[3],label='Behind nominal axis'),Line2D([],[],marker='o',ls='',color=COLORS[2],label='Outside empirical ellipse (front)'),Line2D([],[],marker='o',ls='',color=COLORS[1],label='Opposite E/W half, inside ellipse'),Line2D([],[],marker='o',ls='',color=COLORS[0],label='Inside ellipse, own E/W half'),Line2D([],[],marker='*',ls='',color='black',label='Nominal boresight'),Line2D([],[],marker='x',ls='',color='black',label='Below diagnostic horizon (clipped to rim)')]
        fig.legend(handles=legend,loc='lower center',bbox_to_anchor=(.5,.045),ncol=2,fontsize=9)
        fig.text(.5,.012,'Opposite half is not impossible reception. Nominal pose/mapping provisional; empirical cone is not hardware beamwidth.\nOnly responsibility ≥0.25 and satellite/RX mass ≥10 shown. Weights from selected fit; reference never used in fitting.',ha='center',fontsize=9)
        fig.subplots_adjust(top=.90,bottom=.16,hspace=.25,wspace=.15)
        for suffix in ('png','svg'):fig.savefig(HERE/('sky-'+case+'.'+suffix),dpi=170)
        plt.close(fig)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=('1939','2139'),required=True);args=parser.parse_args();plot(args.case)
