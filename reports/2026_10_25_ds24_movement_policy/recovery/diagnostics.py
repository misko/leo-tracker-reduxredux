"""RF-only saved-endpoint diagnostics; no refits and no geographic truth."""

import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import recovery as r
from ds23_height_problem import geometry_features
from ds23_position_information import marginal_position_information, ellipse_scales


def information(d, saved, arm, kind):
    p = r.build(d, arm, saved['phase_reference'], kind)
    x = np.asarray(saved['endpoint_east_north_km'])
    c = p.calculate(x)
    coefficient = c['coefficient'].copy()
    def derivative(step):
        def prediction(z):
            g = geometry_features(p, z, 0.)
            return p.q*g['intercept']+g['features']@coefficient
        return np.column_stack([(prediction(x+v)-prediction(x-v))/(2*step) for v in np.eye(2)*step])[p.keep]
    j, check = derivative(.02), derivative(.01)
    relative = float(np.linalg.norm(j-check)/np.linalg.norm(j))
    if relative > 1e-5:
        raise ValueError('information derivative check failed')
    g = p.noise_groups[p.keep]
    w = d['powers'][g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
    u, prior = c['features'][p.keep], c['coefficient_prior_precision']
    info = marginal_position_information(j, u, w, prior)
    eigenvalues, axes = np.linalg.eigh(info)
    weak = axes[:, 0]
    row_family = np.concatenate([np.full(int(p.keep[sl].sum()), row['candidate_index'])
        for row, sl in zip(p.rows, p.slices, strict=True)])
    residual = c['conditional_residual_hz'][p.keep]
    family = []
    for index in sorted(set(row_family.tolist())):
        keep = row_family != index
        removed = marginal_position_information(j[keep], u[keep], w[keep], prior)
        family.append(dict(candidate_index=index, norad=int(d['scan'].norads[index]),
            points=int((~keep).sum()),
            weak_direction_information_gain=float(weak@(info-removed)@weak),
            fixed_coefficient_data_loss_derivative_per_km=float(-2*np.sum(residual[~keep]*w[~keep]*(j[~keep]@weak))),
            RMS_hz=float(np.sqrt(np.mean(residual[~keep]**2)))))
    return dict(information_hz_weighted_per_km2=info, weak_axis_east_north=weak,
        **ellipse_scales(info), derivative_relative_change=relative,
        family_influence=family, conditional_on_Gamma_and_labels=True,
        curved_only=True, not_calibrated_confidence=True,
        influence_definition='remove one curved family at fixed endpoint/noise/prior; reproject nuisance, no position refit',
        data_derivative_is_not_full_marginal_objective_derivative=True), p, c


def views(d, saved, coverage, p, c, destination, label):
    channels = sorted({o['channel'] for o in d['observations']})
    owned = set(coverage['accepted_observation_ids'])
    fig, axes = plt.subplots(2, len(channels), figsize=(3.3*len(channels), 7), squeeze=False)
    for rx in (1,2):
        for col, channel in enumerate(channels):
            ax = axes[rx-1,col]
            rows = [o for o in d['observations'] if (o['receiver'],o['channel']) == (rx,channel)]
            unused = [o for o in rows if o['observation_id'] not in owned]
            ax.scatter([o['time_s'] for o in rows],[o['measured_cfo_hz']/1000 for o in rows],s=4,c='.82')
            ax.scatter([o['time_s'] for o in unused],[o['measured_cfo_hz']/1000 for o in unused],s=6,c='crimson')
            for k,(row,i,sl) in enumerate(zip(p.rows,p.members,p.slices,strict=True)):
                track=d['scan'].tracks[i]
                if (track['receiver'],track['channel']) != (rx,channel) or not p.keep[sl].any():
                    continue
                use=p.keep[sl]
                value=track['values'][use]
                value=(value+1/4.4e-6/2)%(1/4.4e-6)-1/4.4e-6/2
                ax.plot(track['times'][use],value/1000,lw=1,alpha=.8)
            ax.set(title=f'RX{rx} CH{channel}',xlabel='Time in scan (s)',ylabel='CFO (kHz)')
            ax.grid(alpha=.2)
    fig.suptitle(f"{d['case']} {label}: {coverage['associated']}/{coverage['total_GLRT']} associations\nGray: all GLRT; red: unassociated; lines: active curved graph sources")
    fig.tight_layout()
    fig.savefig(destination/(label+'_DBG01.png'),dpi=140)
    plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(13,8),squeeze=False)
    residual_rows=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        t=d['scan'].tracks[i];use=p.keep[sl]
        if not use.any():continue
        residual=c['conditional_residual_hz'][sl][use]
        ax=axes[t['receiver']-1,int(t['channel']>4)]
        ax.plot(t['times'][use],residual,'.-',ms=2,lw=.6,alpha=.8)
        for oid,time_s,value,sigma in zip(np.asarray(t['observation_ids'])[use],t['times'][use],residual,p.point_noise[sl][use],strict=True):
            residual_rows.append(dict(observation_id=oid,time_s=float(time_s),residual_hz=float(value),sigma_hz=float(sigma),
                receiver=t['receiver'],channel=t['channel'],component=t['key'],candidate_index=row['candidate_index'],norad=int(d['scan'].norads[row['candidate_index']])))
    for rx in (1,2):
        for band in (0,1):
            axes[rx-1,band].set(title=f"RX{rx} {'high' if band else 'low'}",xlabel='Time in scan (s)',ylabel='Conditional residual (Hz)')
            axes[rx-1,band].grid(alpha=.2)
    fig.suptitle(f"{d['case']} {label}: fitted-c curved residuals")
    fig.tight_layout();fig.savefig(destination/(label+'_residuals.png'),dpi=140);plt.close(fig)
    with (destination/(label+'_residuals.csv')).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(residual_rows[0]));writer.writeheader();writer.writerows(residual_rows)


def main():
    r.verify()
    seal = r.read(r.HERE/'scientific_seal.json')
    for name,digest in seal['files'].items():
        if r.sha(r.HERE/name) != digest:raise ValueError('scientific result changed')
    output = r.HERE/'diagnostics'
    output.mkdir(exist_ok=False)
    records=[]
    for case in r.CASES:
        d=r.context(case);parent=r.read(r.HERE/case/'parent.json');policies=[('baseline','graph',None,parent['arms'],parent['coverage'])]
        for stage in ('graph','support'):
            result=r.read(r.HERE/case/stage/'result.json');selected=result['selected']
            policies.append((stage+'_policy',stage,selected,result['policy_arms'],selected['coverage'] if selected else parent['coverage']))
        case_dir=output/case;case_dir.mkdir()
        for label,kind,selected,arms,coverage in policies:
            dd=d if selected is None else dict(d,node=selected['node'],keep=np.asarray(selected['mask'],bool),means=np.asarray(selected['means']),entries=selected['entries'])
            effective_kind=kind if selected is not None else 'graph'
            for arm in r.ARMS:
                info,p,c=information(dd,arms[arm],arm,effective_kind)
                r.write_new(case_dir/(label+'_'+arm+'_information.json'),info)
                records.append(dict(case=case,policy=label,arm=arm,**{k:info[k] for k in ('major_local_sigma_km','minor_local_sigma_km')}))
                if arm=='fitted_c':
                    views(dd,arms[arm],coverage[arm],p,c,case_dir,label)
    r.write_new(output/'summary.json',dict(rows=records,no_GPS=True,no_position_refits=True,
        source_scientific_seal_sha256=r.sha(r.HERE/'scientific_seal.json')))
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,case in zip(axes,r.CASES,strict=True):
        rows=[v for v in records if v['case']==case and v['arm']=='fitted_c']
        ax.bar(range(len(rows)),[v['major_local_sigma_km'] for v in rows])
        ax.set_xticks(range(len(rows)),[v['policy'] for v in rows],rotation=15)
        ax.set(title=case,ylabel='Conditional curved weak-axis scale (km)');ax.grid(axis='y',alpha=.2)
    fig.tight_layout();fig.savefig(output/'weak_direction_information.png',dpi=150);plt.close(fig)
    r.write_new(output/'seal.json',dict(files={str(p.relative_to(output)):r.sha(p) for p in sorted(output.rglob('*')) if p.is_file()}))


if __name__=='__main__':main()
