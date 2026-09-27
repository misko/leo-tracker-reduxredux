"""Post-selection scoring and illustrations; only this script reads pose truth."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent


def distance_m(lat,lon,other_lat,other_lon):
    a,b,c,d=np.radians([lat,lon,other_lat,other_lon])
    h=np.sin((a-c)/2)**2+np.cos(a)*np.cos(c)*np.sin((b-d)/2)**2
    return float(2*6371008.8*np.arcsin(np.sqrt(np.clip(h,0,1))))


def main():
    result=json.loads((HERE/'results.json').read_text());rows=[]
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    for index,scan in enumerate(result['scans']):
        row=dict(session_id=scan['session_id'],paired_visits=sum(len(g['visits']) for g in scan['groups']),
                 max_centroid_separation_ms=1000*max(g['max_centroid_separation_s'] for g in scan['groups']),arms={})
        for name,arm in scan['arms'].items():
            a,b=arm['geometry'],arm['response_only']
            row['arms'][name]=dict(held_phase_geometry=a['held_phase_log_predictive'],held_phase_constant=b['held_phase_log_predictive'],
                geometry_minus_constant=a['held_phase_log_predictive']-b['held_phase_log_predictive'],
                phase_gain_in_own_cfo_target=a['held_cfo_log_predictive']-a['cfo_only_held_log_predictive'])
        rows.append(row)
        values=[row['arms']['absolute']['held_phase_geometry'],row['arms']['differential']['held_phase_geometry'],row['arms']['differential']['held_phase_constant']]
        axes[index].bar(['Absolute CFO\n+ geometry','Differential CFO\n+ geometry','Constant phase\nresponse'],values,color=['tab:gray','tab:blue','tab:orange'])
        axes[index].set(title=scan['session_id'][-8:],ylabel='Held phase log score relative to uniform')
    fig.suptitle('Same held phase target: differential CFO changes the candidate hypotheses')
    fig.savefig(HERE/'held-phase-comparison.png',dpi=160);plt.close(fig)
    position=json.loads((HERE/'position-results.json').read_text());assert position['complete']
    # No position coordinate is read until the training-selected search result
    # exists and is complete. This coordinate never enters either fitting script.
    authority=json.loads((ROOT/'2026_09_27_ds6_roof/pose-authority.json').read_text())
    lat,lon=authority['latitude_deg'],authority['longitude_deg']
    protocol=json.loads((HERE/'position-protocol.json').read_text());lat0,lon0=protocol['center_from_other_scan_cfo']
    scored={arm:dict(best,error_m=distance_m(best['latitude'],best['longitude'],lat,lon)) for arm,best in position['best'].items()}
    summary=dict(scans=rows,position=scored,position_scope='Two-scan conditional local search; both arms reach a boundary and remain unresolved. Operator position used only after selection.',
                 point_count=len(position['points']),search_elapsed_s=position['elapsed_s'])
    (HERE/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    e=np.array([p['east_km'] for p in position['points']]);n=np.array([p['north_km'] for p in position['points']])
    target_e=np.radians(lon-lon0)*6371.0088*np.cos(np.radians(lat0));target_n=np.radians(lat-lat0)*6371.0088
    fig,axes=plt.subplots(1,3,figsize=(14,4.7),layout='constrained')
    for ax,field,title in zip(axes,['cfo_train','phase_train','factor'],['Differential CFO training score','Differential CFO + phase training score','Phase contribution to training score']):
        values=np.array([p['phase_train']-p['cfo_train'] if field=='factor' else p[field] for p in position['points']])
        if field!='factor':values-=values.max()
        art=ax.tricontourf(e,n,values,levels=16);fig.colorbar(art,ax=ax,label='Log score'+(' relative to grid maximum' if field!='factor' else ''))
        ax.scatter(e,n,s=5,color='black',alpha=.3)
        ax.scatter([target_e],[target_n],marker='o',facecolors='none',edgecolors='red',s=65,label='Operator coordinate (scoring only)')
        ax.scatter([0],[0],marker='+',s=70,color='black',label='Previous CFO-derived centre')
        winner=position['best']['phase' if field!='cfo_train' else 'cfo']
        ax.scatter([winner['east_km']],[winner['north_km']],marker='*',s=100,color='white',edgecolors='black',label='Training-selected boundary point')
        ax.set(title=title,xlabel='East from search centre (km)',ylabel='North from search centre (km)',aspect='equal',xlim=(-13,13),ylim=(-13,13))
    axes[0].legend(fontsize=6,loc='upper left')
    fig.suptitle('Position test fails: both arms choose the same boundary, about 14 km from the operator coordinate\n49-point local grid; no boundary refinement or claim of a resolved optimum')
    fig.savefig(HERE/'position-search.png',dpi=160);plt.close(fig)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
