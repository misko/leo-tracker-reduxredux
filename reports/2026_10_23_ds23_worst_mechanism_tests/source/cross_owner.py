"""Held RX/channel prediction of 58590 with no held-point phase fitting."""
from pathlib import Path
import numpy as np
from diagnose_family import cavity, profile, AUDIT
from probe_ds23_worst_association_bottleneck import setup
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write

OUT=Path(__file__).resolve().parents[1]


def conditional_holdout(covariance, train, held, residual):
    cross=covariance[np.ix_(held,train)]
    solved=np.linalg.solve(covariance[np.ix_(train,train)],residual[train])
    innovation=residual[held]-cross@solved
    covariance_held=covariance[np.ix_(held,held)]-cross@np.linalg.solve(covariance[np.ix_(train,train)],cross.T)
    return innovation,covariance_held


def main():
    d=setup('DS23-0081');j=list(d['scan'].norads).index(58590)
    bank=dict(time_s=d['scan'].sky['time_s'],position_km=d['scan'].sky['position_km'][[j]],
        velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
    audit=read(AUDIT);rows=[]
    for arm in ('c0','fitted_c'):
        for location in ('endpoint','diagnostic_point'):
            saved=audit['arms'][arm][location];x=saved['endpoint_east_north_km']
            data=cavity(d,arm,x,saved['phase_reference'],58590)
            for kind in ('receiver','channel'):
                owner=np.array([data['members'][g][kind] for g in data['groups']])
                for training_owner in sorted(set(owner)):
                    train=np.flatnonzero(owner==training_owner);held=np.flatnonzero(owner!=training_owner)
                    fit=profile(data['times'][train],data['values'][train],data['q'][train],
                        data['covariance'][np.ix_(train,train)],data['noise'][train],bank,x)
                    f,e=phase_frequency_grid(bank,data['times'],*latlon(x),phase_seconds=fit['phase_s'])
                    residual=data['values']-data['q']*f[0]
                    innovation,cov=conditional_holdout(data['covariance'],train,held,residual)
                    rows.append(dict(arm=arm,location=location,split=kind,training_owner=int(training_owner),
                        training_points=len(train),held_points=len(held),phase_s=fit['phase_s'],
                        held_times=data['times'][held],held_groups=data['groups'][held],members=data['members'],
                        held_innovation_hz=innovation,held_prediction_sd_hz=np.sqrt(np.diag(cov)),
                        held_RMS_hz=float(np.sqrt(np.mean(innovation**2))),
                        held_quadratic=float(innovation@np.linalg.solve(cov,innovation)),
                        held_minimum_elevation_deg=float(e[:,held].min()),
                        no_held_points_used_for_phase_or_radio_update=True,
                        training_phase_treated_fixed_uncertainty_not_included=True))
    write(OUT/'evidence/cross_owner_58590.json',dict(rows=rows,
        conditional_diagnostic_not_an_acceptance_gate=True,no_position_fit_or_model_adoption=True))
    for r in rows:print(r['arm'],r['location'],r['split'],r['training_owner'],round(r['phase_s'],3),round(r['held_RMS_hz'],2),flush=True)


if __name__=='__main__':main()
