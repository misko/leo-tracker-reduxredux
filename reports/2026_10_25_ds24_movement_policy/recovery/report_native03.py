"""Native-ID CFO source views; supersedes mixed-branch DBG01 figures only."""

import csv
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import recovery as r
import repair01 as repair
import eligibility02 as eligibility

OUT=r.HERE/'report_native03'
PERIOD=1/4.4e-6


def native_source(track, use, lookup, recovered):
    points=[]
    for oid,time_s,active in zip(track['observation_ids'],track['times'],use,strict=True):
        if not active:continue
        row=lookup[oid]
        if abs(float(row['time_s'])-float(time_s))>1e-6:raise ValueError('native ID time mismatch')
        if row['receiver']!=track['receiver'] or row['channel']!=track['channel']:
            raise ValueError('native ID owner mismatch')
        points.append(dict(observation_id=oid,component=track['key'],receiver=row['receiver'],channel=row['channel'],
            track_time_s=float(time_s),native_time_s=float(row['time_s']),
            native_CFO_hz=float(row['measured_cfo_hz']),plotted_CFO_hz=float(row['measured_cfo_hz']),
            recovered_source=bool(recovered),line_break_before=False))
    for before,after in zip(points,points[1:]):
        after['line_break_before']=bool(abs(after['native_CFO_hz']-before['native_CFO_hz'])>PERIOD/2 or
            after['native_time_s']-before['native_time_s']>10.)
    return points


def plot(d,p,coverage,label,recovered,destination):
    lookup={o['observation_id']:o for o in d['observations']}
    if len(lookup)!=len(d['observations']):raise ValueError('duplicate native observation ID')
    owned=set(coverage['accepted_observation_ids']);channels=sorted({o['channel'] for o in d['observations']})
    fig,axes=plt.subplots(2,len(channels),figsize=(3.5*len(channels),8.2),squeeze=False)
    checks=[]
    for rx in (1,2):
        for col,ch in enumerate(channels):
            ax=axes[rx-1,col]
            rows=[o for o in d['observations'] if (o['receiver'],o['channel'])==(rx,ch)]
            unused=[o for o in rows if o['observation_id'] not in owned]
            ax.scatter([o['time_s'] for o in rows],[o['measured_cfo_hz']/1000 for o in rows],s=6,c='.78',zorder=1)
            ax.scatter([o['time_s'] for o in unused],[o['measured_cfo_hz']/1000 for o in unused],s=9,c='crimson',zorder=2)
            for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
                track=d['scan'].tracks[i]
                if (track['receiver'],track['channel'])!=(rx,ch) or not p.keep[sl].any():continue
                added=track['key'] in recovered
                points=native_source(track,p.keep[sl],lookup,added);checks.extend(points)
                x=np.array([v['native_time_s'] for v in points]);y=np.array([v['plotted_CFO_hz']/1000 for v in points])
                boundaries=np.flatnonzero([v['line_break_before'] for v in points])
                for index in np.split(np.arange(len(points)),boundaries):
                    ax.plot(x[index],y[index],'.-',color='darkorange' if added else 'royalblue',
                        lw=2.2 if added else .8,ms=4.5 if added else 2.2,alpha=1 if added else .75,zorder=5 if added else 3)
            ax.set(title=f'RX{rx} CH{ch}',xlabel='Time in scan (s)',ylabel='Native measured CFO (kHz)')
            ax.grid(alpha=.2)
    if not all(v['native_CFO_hz']==v['plotted_CFO_hz'] for v in checks):raise ValueError('plotted native CFO mismatch')
    if len(checks)!=coverage['curved_points'] or len({v['observation_id'] for v in checks})!=len(checks):
        raise ValueError('plotted active-source ID count mismatch')
    fig.suptitle(f"{d['case']} · {label}\nCompatible original GLRT: {coverage['associated']}/{coverage['total_GLRT']} "
        f"({coverage['percent']:.2f}%, includes post-fit-only associations) · Position likelihood: {coverage['likelihood_points']}/{coverage['total_GLRT']} "
        f"({coverage['curved_points']} curved + {coverage['predictive_points']} predictive)\n"
        'Gray: all native GLRT · Red: unassociated · Blue: incumbent curved source observations · Orange: recovered curved source observations',fontsize=13)
    fig.tight_layout(rect=[0,0,1,.91]);fig.savefig(destination.with_suffix('.png'),dpi=150);plt.close(fig)
    with destination.with_suffix('.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(checks[0]));writer.writeheader();writer.writerows(checks)
    return dict(points=len(checks),recovered_points=sum(v['recovered_source'] for v in checks),
        max_native_time_difference_s=max(abs(v['track_time_s']-v['native_time_s']) for v in checks),
        max_native_CFO_difference_hz=max(abs(v['native_CFO_hz']-v['plotted_CFO_hz']) for v in checks),
        branch_or_gap_line_breaks=sum(v['line_break_before'] for v in checks),
        no_wrapped_track_CFO_used=True,no_polynomial_or_orbit_curve_claimed=True)


def main():
    repair.verify()
    scientific=r.read(eligibility.OUT/'scientific_seal.json')
    for name,digest in scientific['files'].items():
        if r.sha(eligibility.OUT/name)!=digest:raise ValueError('RF result changed')
    OUT.mkdir(exist_ok=False);r.build=repair.corrected_build;checks=[]
    for case in r.CASES:
        d=r.context(case);parent=r.read(r.HERE/case/'parent.json');graph=r.read(r.HERE/case/'graph/result.json');control=r.read(eligibility.OUT/case/'result.json')
        policies=[('baseline','Saved baseline','graph',None,parent['arms'],parent['coverage'])]
        for key,label,kind,result in [('graph_policy','Graph reentry policy (baseline fallback)','graph',graph),
            ('support_control','Support-aware curved recovery','support',control)]:
            selected=result['selected'];policies.append((key,label,kind,selected,result['policy_arms'],selected['coverage'] if selected else parent['coverage']))
        case_dir=OUT/case;case_dir.mkdir()
        for key,label,kind,selected,arms,coverage in policies:
            dd=d if selected is None else dict(d,node=selected['node'],keep=np.asarray(selected['mask'],bool),means=np.asarray(selected['means']),entries=selected['entries'])
            p=r.build(dd,'fitted_c',arms['fitted_c']['phase_reference'],kind if selected else 'graph')
            recovered={v['component'] for v in selected['additions']} if selected else set()
            receipt=plot(dd,p,coverage['fitted_c'],label,recovered,case_dir/(key+'_native_DBG01'))
            checks.append(dict(case=case,policy=key,**receipt))
    superseded=sorted(str(p.relative_to(r.HERE)) for p in (r.HERE/'diagnostics_repair01').rglob('*DBG01.png'))
    r.write_new(OUT/'manifest.json',dict(no_GPS=True,no_refits=True,
        source_sha256=r.sha(Path(__file__)),test_source_sha256=r.sha(r.HERE/'test_report_native03.py'),
        source_scientific_seal_sha256=r.sha(eligibility.OUT/'scientific_seal.json'),native_coordinate_checks=checks,
        superseded_DBG01_files=superseded,
        superseded_reason='old views mixed native CFO scatter with alias-wrapped track CFO; do not publish as primary',
        existing_residual_and_information_artifacts_remain_valid=True,
        line_rule='join observed source samples; break at >half alias-period CFO jump or >10s gap; no interpolated observations',
        files={str(p.relative_to(OUT)):r.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()}))


if __name__=='__main__':main()
