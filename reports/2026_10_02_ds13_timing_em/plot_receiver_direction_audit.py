"""All final tracks: east/west geometry and original soft-association controls."""
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plot_all_glrt_doppler_overlay import load_archived_session

ROOT=Path(__file__).resolve().parent


def run():
    source=ROOT/'prior-position-audit/pointing-evidence.json'
    evidence=json.loads(source.read_text());tracks=evidence['tracks'];loaded={};rows=[]
    for t in tracks:
        scan=t['scan'];sid=next(c['pose']['session_id'] for c in evidence['captures'] if c['scan']==scan)
        if scan not in loaded:loaded[scan]=load_archived_session(sid)[0]
        a=loaded[scan];column=list(a['catalog_numbers']).index(t['satellite'])
        mask=(a['receiver']==1-t['receiver'])&(a['times_s']>=min(t['time_s']))&(a['times_s']<=max(t['time_s']))
        indices=np.flatnonzero(mask);groups=np.unique(a['group'][indices]);support=[]
        for group in groups:
            rr=indices[a['group'][indices]==group]
            support.append(float(np.sum(a['posterior'][rr,column])))
        opposite=np.array(t['east_component'])>0 if t['receiver']==0 else np.array(t['east_component'])<0
        directions=np.array(t['east_component'])
        # Angular distance to the east/west dividing vertical plane.
        deep=np.degrees(np.arcsin(np.clip(abs(directions),0,1)))>10
        rows.append(dict(scan=scan,satellite=t['satellite'],receiver=t['receiver'],points=t['points'],
            west_percent=100*t['west_count']/t['points'],east_percent=100*t['east_count']/t['points'],
            other_receiver_final_track=t['other_rx_has_final_track'],
            opposite_side_points=int(opposite.sum()),opposite_side_over_10deg_points=int(np.sum(opposite&deep)),
            other_rx_original_groups_tested=len(groups),other_rx_original_target_support_ge90=sum(s>=.9 for s in support),
            other_rx_original_target_support_ge50=sum(s>=.5 for s in support),
            nominal_off_axis_min_deg=t['nominal_off_axis_min_median_max_deg'][0],
            nominal_off_axis_max_deg=t['nominal_off_axis_min_median_max_deg'][2]))
    fig,axes=plt.subplots(1,2,figsize=(13,7))
    for ax,scan in zip(axes,('A','B')):
        selected=[r for r in rows if r['scan']==scan];y=np.arange(len(selected))
        west=np.array([r['west_percent'] for r in selected]);east=100-west
        ax.barh(y,west,color='#4878a8',label='West of local meridian')
        ax.barh(y,east,left=west,color='#e6a143',label='East of local meridian')
        ax.set_yticks(y,[f"{r['satellite']} / RX{r['receiver']}"+(' *' if r['other_receiver_final_track'] else '') for r in selected])
        ax.invert_yaxis();ax.set_xlim(0,100);ax.set_title('Scan '+scan);ax.set_xlabel('% of assigned GLRT points')
        for j,r in enumerate(selected):
            if r['opposite_side_points'] and not r['other_receiver_final_track']:
                ax.text(101,j,f"{r['opposite_side_points']} opposite",va='center',fontsize=8,color='#a03030')
    axes[0].legend(loc='upper center',bbox_to_anchor=(.5,-.12),fontsize=9)
    fig.suptitle('All 22 final receiver tracks · capture-bound roof location\nRX0 nominally west; RX1 nominally east · * satellite has final tracks on both RXs')
    fig.text(.5,.015,'Assigned-track membership is not a raw-signal nondetection test. Directional overlap is allowed; no measured beam boundary.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.07,.95,.92))
    output=ROOT/'receiver-direction-audit';output.mkdir(exist_ok=False)
    fig.savefig(output/'all-tracks.png',dpi=160)
    with (output/'all-tracks.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (output/'receipt.json').write_text(json.dumps(dict(tracks=rows,pointing_evidence=str(source),
        scope='All 22 final receiver tracks. Sky positions at capture-bound roof location and fitted latest-TLE timing. '
        'Other-RX support uses original archived soft posteriors summed across alias-family rows, no residual gate; '
        'these are model-conditioned associations, not independent detection or identity proof.'),indent=2))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':run()
