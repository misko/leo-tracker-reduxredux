"""Residual structure and nominal antenna orientation for frozen associations."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from cohort import ROOF,digest
from discovery import ARMS,FoldCalibration


def residual_statistics(times,errors,channels):
    times,errors,channels=map(np.asarray,(times,errors,channels))
    if len(times)<3 or np.ptp(times)<=0:
        return None
    t=times-np.mean(times)
    columns=np.column_stack([np.ones(len(t)),t,t*t])
    values=[]
    coefficients=[]
    for count in (1,2,3):
        beta=np.linalg.lstsq(columns[:,:count],errors,rcond=None)[0]
        coefficients.append(beta)
        values.append(float(np.sqrt(np.mean((errors-columns[:,:count]@beta)**2))))
    indicators=np.column_stack([channels==c for c in np.unique(channels)]).astype(float)
    controlled=[]
    for degree in (1,2):
        design=np.column_stack([indicators,*[t**i for i in range(1,degree+1)]])
        residual=errors-design@np.linalg.lstsq(design,errors,rcond=None)[0]
        controlled.append(float(np.sqrt(np.mean(residual**2))))
    ratio=lambda a,b:float(a/b) if b>1e-8 else None
    return dict(rms_hz=float(np.sqrt(np.mean(errors**2))),mean_hz=float(np.mean(errors)),
                centered_rms_hz=values[0],linear_rms_hz=values[1],quadratic_rms_hz=values[2],
                curvature_ratio=ratio(values[1],values[2]),
                channel_controlled_linear_rms_hz=controlled[0],channel_controlled_quadratic_rms_hz=controlled[1],
                channel_controlled_curvature_ratio=ratio(*controlled),
                pooled_slope_hz_s=float(coefficients[1][1]),quadratic_coefficient_hz_s2=float(coefficients[2][2]))


def angles(data,index,times,rx):
    """Geometric az/el and angle to nominal 70° elevation west/east axes."""
    from joint_inputs import _ecef
    positions=np.column_stack([np.interp(times,data.nodes,data.position[index,:,axis]) for axis in range(3)])
    vector=positions-_ecef(*ROOF)
    vector/=np.linalg.norm(vector,axis=1)[:,None]
    lat,lon=np.deg2rad(ROOF)
    east=np.array([-np.sin(lon),np.cos(lon),0.])
    north=np.array([-np.sin(lat)*np.cos(lon),-np.sin(lat)*np.sin(lon),np.cos(lat)])
    up=np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)])
    e,n,u=vector@east,vector@north,vector@up
    azimuth=np.mod(np.rad2deg(np.arctan2(e,n)),360.)
    elevation=np.rad2deg(np.arcsin(np.clip(u,-1,1)))
    az,el=np.deg2rad([270 if rx==0 else 90,70])
    axis=np.cos(el)*np.sin(az)*east+np.cos(el)*np.cos(az)*north+np.sin(el)*up
    off_axis=np.rad2deg(np.arccos(np.clip(vector@axis,-1,1)))
    opposite=e>0 if rx==0 else e<0
    return azimuth,elevation,off_axis,opposite


def run(directory,output,method='alternatives'):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cal=FoldCalibration(directory,permit_warning=True)
    d=cal.data
    source=directory/'selection-p10-g600-t1.json'
    saved=json.loads(source.read_text())
    pool=json.loads((directory/'discovery/candidate-pool.json').read_text())
    output.mkdir(exist_ok=True,parents=True)
    all_rows=[]
    for arm in ARMS:
        result=saved['arms'][arm][method]['final']
        assignments=result['assignments']
        ordered=sorted(result['selected'],key=lambda r:(-r['count'],r['catalog_number']))
        panels=[]
        for selected in ordered:
            number=selected['catalog_number']
            mode=pool['arms'][arm][selected['mode_index']]
            chosen=[a for a in assignments if a['catalog_number']==number]
            rr=np.array([a['row_index'] for a in chosen],int)
            native=np.array([a['residual_hz'] for a in chosen])
            for rx in (0,1):
                mask=d.receiver[rr]==rx
                if not np.any(mask):
                    continue
                rows=rr[mask]
                errors=native[mask]*11.085e9/d.rf[rows]
                stats=residual_statistics(d.times[rows],errors,d.channel[rows])
                if stats is None:
                    continue
                query=np.empty(len(rows))
                for _,part,models in cal.parts:
                    use=np.isin(d.group[rows],part.group)
                    query[use]=d.times[rows[use]]+models[arm][1]+mode['offset_s']
                az,el,off,opposite=angles(d,mode['satellite_index'],query,rx)
                row=dict(scan=directory.name,arm=arm,method=method,satellite=number,receiver=rx,
                         windows=len(rows),start_s=float(min(d.times[rows])),end_s=float(max(d.times[rows])),
                         length_s=float(np.ptp(d.times[rows])),native_rms_hz=float(np.sqrt(np.mean(native[mask]**2))),
                         **stats,median_elevation_deg=float(np.median(el)),median_off_axis_deg=float(np.median(off)),
                         opposite_east_west_fraction=float(np.mean(opposite)),behind_nominal_axis_fraction=float(np.mean(off>90)),
                         timing_relative_s=mode['offset_s'])
                all_rows.append(row)
                panels.append((row,rows,errors))
        fig,axes=plt.subplots(int(np.ceil(len(panels)/2)),2,figsize=(15,max(4,2.1*np.ceil(len(panels)/2))),squeeze=False)
        colors=('#0072b2','#e69f00','#009e73','#cc79a7')
        for ax,(row,rows,errors) in zip(axes.flat,panels):
            t=d.times[rows]
            for channel in sorted(set(d.channel[rows])):
                use=d.channel[rows]==channel
                ax.scatter(t[use],errors[use],s=9,color=colors[(int(channel)-1)%4],label=f'CH{channel}',alpha=.75)
            grid=np.linspace(min(t),max(t),100)
            for degree,style,color in ((1,'--','#333333'),(2,'-','#d55e00')):
                coef=np.polyfit(t-np.mean(t),errors,degree)
                ax.plot(grid,np.polyval(coef,grid-np.mean(t)),style,color=color,lw=1.1)
            ax.axhline(0,color='#999999',lw=.7)
            ax.grid(alpha=.15)
            ratio=row['curvature_ratio']
            ax.set_title(f"{row['satellite']} / RX{row['receiver']} · {row['windows']} windows · {row['length_s']:.1f} s\nRMS {row['rms_hz']:.1f} Hz; linear/quad {ratio:.3f}×" if ratio is not None else f"{row['satellite']} / RX{row['receiver']} · degenerate quadratic",fontsize=9)
            ax.set_ylabel('Residual at 11.085 GHz (Hz)',fontsize=8)
            ax.set_xlabel('Receive time (s)',fontsize=8)
            ax.tick_params(labelsize=8)
        for ax in list(axes.flat)[len(panels):]:
            ax.set_visible(False)
        title=f'{directory.name} · {method} · {arm} · frozen association residuals'
        if cal.warnings:
            title+='\nCalibration convergence warning: diagnostic only'
        fig.suptitle(title,fontsize=14)
        fig.tight_layout(rect=(0,.012,1,.98))
        fig.text(.5,.003,'Pooled-channel line (dashed) and quadratic (orange); in-sample structure diagnostic, not orbit correction. Membership is fixed.',ha='center',fontsize=9)
        fig.savefig(output/f'{method}-{arm}-residuals.png',dpi=130)
        plt.close(fig)
    csv_path=output/f'{method}-track-statistics.csv'
    with csv_path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5))
    for ax,arm in zip(axes,ARMS):
        rows=[r for r in all_rows if r['arm']==arm]
        for rx,color in ((0,'#0072b2'),(1,'#d55e00')):
            use=[r for r in rows if r['receiver']==rx]
            ax.scatter([r['opposite_east_west_fraction']*100 for r in use],[r['median_off_axis_deg'] for r in use],
                       s=[15+1.2*r['windows'] for r in use],alpha=.6,color=color,label=f'RX{rx}')
        ax.axhline(90,color='#777777',ls=':')
        ax.set(xlabel='Windows on opposite east/west half (%)',ylabel='Median angle from nominal pointing axis (°)',title=arm,xlim=(-5,105))
        ax.grid(alpha=.2)
        ax.legend()
    fig.suptitle(f'{directory.name} · nominal orientation check · marker area follows window support')
    fig.text(.5,.018,'RX0 west / RX1 east, 70° elevation assumed from the 40° mount. Not measured beam patterns.\nOpposite east/west half is not synonymous with behind the antenna, and is not used as a hard rejection.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.09,1,.93))
    fig.savefig(output/f'{method}-orientation.png',dpi=150)
    plt.close(fig)
    (output/f'{method}-diagnostics.json').write_text(json.dumps(dict(rows=all_rows,calibration_warnings=cal.warnings,
        source_sha256=digest(source.read_bytes()),sources=cal.sources,scope=__doc__),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--method',choices=('greedy','replacement','alternatives'),default='alternatives')
    a=p.parse_args()
    run(a.directory,a.output,a.method)
