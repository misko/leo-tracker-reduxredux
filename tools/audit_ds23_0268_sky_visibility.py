"""Report-side sky audit. Station coordinates never enter RF inference."""

import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from debug_ds23_0268_visibility_reentry import OUT,replay
from investigate_ds23_0268_remaining_tracks import OUT as PREVIOUS,CASE,load
from run_algo01_ds23_sample import ROOT,read,write,sha
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.continuous_curve_fit import paired_phase_states
from leo.sky.frames import look_angles,geodetic_to_ecef_km,ecef_to_enu_matrix


def angular_separation(azimuth,elevation,axis_azimuth,axis_elevation):
    a,e,b,h=np.deg2rad(np.broadcast_arrays(azimuth,elevation,axis_azimuth,axis_elevation))
    return np.rad2deg(np.arccos(np.clip(np.sin(e)*np.sin(h)+np.cos(e)*np.cos(h)*np.cos(a-b),-1,1)))


def horizon(p,x,norad,times,position=None,nominal=False):
    scan=p.scan;j=int(np.flatnonzero(scan.norads==norad)[0]);state=p.state(x);times=np.asarray(times)
    phases=np.zeros_like(state['phases']) if nominal else state['phases']
    pos,vel=paired_phase_states(scan.sky,times,np.full(len(times),j),phases)
    if not nominal and j in p.supported:
        local=p.labels.index(j);k=p.supported.index(j)
        begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
        coefficients=p.calculate(x)['coefficient'][begin+3*k:begin+3*k+3]
        dp,dv=paired_phase_states(p.mode_bank,np.repeat(times,3),np.tile(3*local+np.arange(3),len(times)),np.repeat(state['phases'][p.labels],3))
        pos+=np.einsum('nkd,k->nd',dp.reshape(-1,3,3),coefficients)
        vel+=np.einsum('nkd,k->nd',dv.reshape(-1,3,3),coefficients)
    location=latlon(x) if position is None else position
    az,el,_,_=look_angles(pos,vel,geodetic_to_ecef_km(*location,0),ecef_to_enu_matrix(*location))
    return az,el


def summarize(p,x,accepted):
    rows=[]
    for row in accepted:
        track=next(t for t in p.scan.tracks if t['key']==row['component'])
        owned=set(row.get('observation_ids',track['observation_ids']))
        use=np.asarray([oid in owned for oid in track['observation_ids']]);times=track['times'][use]
        az,el=horizon(p,x,row['norad'],times)
        axis=270 if track['receiver']==1 else 90
        separation=angular_separation(az,el,axis,70)
        nominal_az,nominal_el=horizon(p,x,row['norad'],times,nominal=True)
        nominal_separation=angular_separation(nominal_az,nominal_el,axis,70)
        rows.append(dict(component=track['key'],norad=row['norad'],receiver=track['receiver'],channel=track['channel'],
            points=len(times),times_s=times,azimuth_deg=az,elevation_deg=el,boresight_separation_deg=separation,
            minimum_elevation_deg=float(el.min()),maximum_boresight_separation_deg=float(separation.max()),
            nominal_TLE_minimum_elevation_deg=float(nominal_el.min()),
            nominal_TLE_maximum_boresight_separation_deg=float(nominal_separation.max()),
            above_horizon=bool(el.min()>=0),required_cone_half_angle_deg=float(separation.max()),
            outside_30deg=int(np.sum(separation>30)),outside_45deg=int(np.sum(separation>45)),
            outside_60deg=int(np.sum(separation>60)),outside_front_90deg=int(np.sum(separation>90))))
    return rows


def render(rows,label):
    families=sorted({r['norad'] for r in rows});colors=plt.get_cmap('tab20');fig,axes=plt.subplots(1,2,figsize=(16,8),subplot_kw=dict(projection='polar'))
    for rx,ax in enumerate(axes,1):
        for row in rows:
            if row['receiver']!=rx:continue
            ax.plot(np.deg2rad(row['azimuth_deg']),90-np.asarray(row['elevation_deg']),'.-',ms=3,lw=.7,
                color=colors(families.index(row['norad'])%20),label=str(row['norad']))
        az=np.linspace(0,360,721);el=np.linspace(0,90,181);aa,ee=np.meshgrid(az,el);axis=270 if rx==1 else 90
        sep=angular_separation(aa,ee,axis,70)
        contour=ax.contour(np.deg2rad(aa),90-ee,sep,levels=[30,45,60],colors='gray',linewidths=.7,linestyles='dashed')
        ax.clabel(contour,fmt=lambda x:f'{x:g}° off-axis',fontsize=8)
        ax.scatter(np.deg2rad(axis),20,color='black',marker='*',s=150,zorder=6,label='Nominal mount axis')
        ax.set_theta_zero_location('N');ax.set_theta_direction(-1);ax.set_ylim(0,90);ax.set_yticks([0,30,60,90],['90°','60°','30°','0°'])
        ax.set_title(f'RX{rx} · {"west" if rx==1 else "east"} · nominal 70° elevation')
        handles,labels=ax.get_legend_handles_labels();unique=dict(zip(labels,handles));ax.legend(unique.values(),unique.keys(),fontsize=7,loc='lower left',bbox_to_anchor=(-.12,-.19),ncol=4)
    fig.suptitle('DS23-0268 · All associated tracks in the sky · '+label+'\n'
        'Azimuth clockwise from north; radial labels are elevation · dashed contours are sensitivity, not a measured beam',fontsize=13)
    fig.tight_layout(rect=(0,.06,1,.91));fig.savefig(OUT/('sky_'+label+'.png'),dpi=180,bbox_inches='tight');plt.close(fig)


def main():
    OUT.mkdir(parents=True,exist_ok=True);authority=ROOT/'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json';mount=read(authority)
    # Deliberately exclude its location fields: orientation does not define a position prior.
    evidence={k:mount[k] for k in ('revision','radio_serial','receivers','fixture_part_id','fixture_evidence','orientation_evidence','nominal_outward_tilt_deg')}
    evidence.update(authority_sha256=sha(authority),station_position_fields_used=False,
        installed_RF_elevation_and_beam_pattern_unknown=True,physical_receiver_mapping_provisional=True)
    initial=read(OUT/'trials/interior_add_66797.json');cover=read(OUT/'trial_coverage.json')
    selected=next(r for r in cover['rows'] if r['name']=='interior_add_66797');results={}
    for arm in ('c0','fitted_c'):
        p,x=replay(initial,arm);rows=summarize(p,x,selected['arms'][arm]['accepted_rows'])
        results[arm]=dict(rows=rows,all_above_horizon=all(r['above_horizon'] for r in rows),
            maximum_required_nominal_half_angle_deg=max(r['required_cone_half_angle_deg'] for r in rows),
            unadjusted_causal_TLE_all_above_horizon=all(r['nominal_TLE_minimum_elevation_deg']>=0 for r in rows),
            unadjusted_causal_TLE_maximum_half_angle_deg=max(r['nominal_TLE_maximum_boresight_separation_deg'] for r in rows),
            outside_nominal_front=sum(r['outside_front_90deg'] for r in rows))
        if arm=='c0':render(rows,'selected_71percent_c0')
    # Explicit evaluation-only comparison; these coordinates never enter a fit or nomination.
    from report_algo02_ds23 import REFERENCE
    reference_check={}
    for arm in ('c0','fitted_c'):
        p,x=replay(initial,arm);maximum_angle_change=0.;maximum_separation=0.;minimum_elevation=90.
        for row in results[arm]['rows']:
            az,el=horizon(p,x,row['norad'],row['times_s'],position=REFERENCE)
            axis=270 if row['receiver']==1 else 90;separation=angular_separation(az,el,axis,70)
            maximum_angle_change=max(maximum_angle_change,float(angular_separation(az,el,row['azimuth_deg'],row['elevation_deg']).max()))
            maximum_separation=max(maximum_separation,float(separation.max()));minimum_elevation=min(minimum_elevation,float(el.min()))
        reference_check[arm]=dict(maximum_sky_direction_change_deg=maximum_angle_change,
            maximum_required_nominal_half_angle_deg=maximum_separation,minimum_elevation_deg=minimum_elevation,
            all_above_horizon=minimum_elevation>=0,evaluation_reference_only_not_an_inference_input=True)
    write(OUT/'sky_visibility.json',dict(case=CASE,orientation=evidence,arms=results,reference_geometry_diagnostic=reference_check,
        interpretation='Horizon verified; antenna visibility conditional on unmeasured beam width, installed pose and receiver mapping. No azimuth-hemisphere veto.'))
    compact=[]
    for arm,r in results.items():
        compact.extend(dict(arm=arm,**{k:v for k,v in row.items() if k not in ('times_s','azimuth_deg','elevation_deg','boresight_separation_deg')}) for row in r['rows'])
    with (OUT/'sky_visibility.csv').open('w') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(compact[0]));writer.writeheader();writer.writerows(compact)
    print({arm:{k:v for k,v in r.items() if k!='rows'} for arm,r in results.items()},flush=True)


if __name__=='__main__':main()
