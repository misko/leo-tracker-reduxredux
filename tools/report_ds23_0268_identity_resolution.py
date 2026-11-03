"""Report-only matched identity comparison and nominal-orbit geometry audit.

No result from this module is fed to the fitter. GPS appears only in reported
position error. Radio-calibration sensitivity is exploratory, not validated.
"""

import argparse
import csv

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from algo02_scan import pair_passes
from analyze_dsx01_fixed_site import ecef_states
from audit_ds23_0268_sky_visibility import angular_separation
from debug_ds23_0268_visibility_reentry import OUT as PRIOR
from probe_algo03_frame_peak_recovery import SOURCE
from probe_ds23_0268_selected_identity_split import replay_proposal
from report_algo02_ds23 import position_error
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.sky.frames import look_angles,geodetic_to_ecef_km,ecef_to_enu_matrix
from leo.sky.propagation import parse_element_sets

OUT=ROOT/'reports/2026_10_20_ds23_0268_identity_resolution'
CAL=ROOT/'reports/2026_10_20_ds23_0268_radio_calibration_principal'
NAMES=dict(original='trials/interior_add_66797.json',
    split='selected_split_all_RX1_constrained.json',
    whole='whole_family_67953_constrained.json',
    split_CH2='selected_split_all_RX1_with_CH2_constrained.json',
    whole_CH2='whole_family_67953_with_CH2_constrained.json')
COLORS=dict(original='#b94d4d',split='#317bb2',whole='#9a63af')


def csv_write(path,rows):
    with path.open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(rows)


def load_models():
    old=next(r for r in read(PRIOR/'trial_coverage.json')['rows']
             if r['name']=='interior_add_66797')['arms']
    split=read(PRIOR/'accepted_identity_split_coverage.json')
    whole=read(PRIOR/'whole_family_identity_coverage.json')
    coverage=dict(original=old,
        split=split['selected_split_all_RX1_constrained'],
        split_CH2=split['selected_split_all_RX1_with_CH2_constrained'],
        whole=whole['whole_family_67953_constrained'],
        whole_CH2=whole['whole_family_67953_with_CH2_constrained'])
    records={name:read(PRIOR/path) for name,path in NAMES.items()}
    rows=[]
    for name,record in records.items():
        if not pair_passes(record['arms'],include_linear=True):
            raise ValueError('saved hypothesis fails paired gates')
        for arm,r in record['arms'].items():
            c=coverage[name][arm]
            base=set(old[arm]['associated_observation_ids'])
            selected=set(c['associated_observation_ids'])
            if not base<=selected or c['associated_additional_peaks']:
                raise ValueError('hypothesis lost points or changed original numerator')
            rows.append(dict(hypothesis=name,arm=arm,associated_points=len(selected),
                associated_percent=100*len(selected)/3165,tracks=c['associated_tracks'],
                satellites=len({t['norad'] for t in c['accepted_rows']}),
                position_error_km=position_error(r['endpoint_latlon']),
                negative_twice_RF_bound=r['negative_twice_elbo'],paired_gates=True,
                original_associations_lost=len(base-selected),
                additional_peaks_counted=c['associated_additional_peaks']))
    return records,coverage,rows


def compare_plot(rows):
    fig,axes=plt.subplots(1,3,figsize=(16,5))
    for offset,arm,color in ((-.16,'c0','#648bb5'),(.16,'fitted_c','#b56d99')):
        original=next(r for r in rows if r['hypothesis']=='original' and r['arm']==arm)
        for k,name in enumerate(NAMES):
            r=next(r for r in rows if r['hypothesis']==name and r['arm']==arm)
            axes[0].bar(k+offset,r['associated_percent'],width=.3,color=color,label=arm if k==0 else None)
            axes[1].bar(k+offset,r['position_error_km'],width=.3,color=color)
            reference=(next(s for s in rows if s['hypothesis']=='split_CH2' and s['arm']==arm)
                       if name.endswith('CH2') else original)
            axes[2].bar(k+offset,r['negative_twice_RF_bound']-reference['negative_twice_RF_bound'],
                        width=.3,color=color)
    labels=['53923\nall RX','RX1 split','67953\nall RX','RX1 split\n+ CH2','67953 all\n+ CH2']
    for ax in axes:
        ax.set_xticks(range(len(NAMES)),labels,fontsize=8);ax.grid(axis='y',alpha=.15)
    axes[0].set_ylabel('Associated original GLRT (%)');axes[0].axhline(70,color='gray',ls='--');axes[0].legend()
    axes[1].set_ylabel('Position error (km; evaluation only)')
    axes[2].set_ylabel('RF bound difference; lower is better')
    axes[2].axvline(2.5,color='black',ls=':');axes[2].axhline(0,color='gray',lw=.8)
    axes[2].text(.02,.98,'First 3: relative to original\nLast 2: relative to split + CH2\nDifferent observation masks: do not compare groups',
                 transform=axes[2].transAxes,va='top',fontsize=8)
    fig.suptitle('DS23-0268: association target passed; satellite identity remains ambiguous\n'
                 'Both c arms use matched observations, priors and search budgets within each hypothesis')
    fig.tight_layout(rect=(0,0,1,.9));fig.savefig(OUT/'identity_comparison.png',dpi=175);plt.close(fig)


def residual_plot(records):
    panels={};title={}
    for name in ('original','split','whole'):
        p,x=replay_proposal(records[name],'c0')
        values=p.calculate(x)['conditional_residual_hz']
        for i,sl in zip(p.members,p.slices,strict=True):
            track=p.scan.tracks[i]
            if not any(r['component']==track['key'] and r['norad']==53923
                       for r in records['original']['arms']['c0']['gates']['tracks']):continue
            use=p.keep[sl]
            panels.setdefault(track['key'],{})[name]=(track['times'][use],values[sl][use])
            title[track['key']]=f"RX{track['receiver']} CH{track['channel']} {track['key'].split('-T')[1].split('-')[0]}"
    fig,axes=plt.subplots(3,2,figsize=(15,10))
    for ax,(key,curves) in zip(axes.flat,panels.items(),strict=True):
        for name,(t,r) in curves.items():
            ax.plot(t,r,'.-',ms=3,lw=.8,color=COLORS[name],label=name)
        ax.axhline(0,color='black',lw=.7);ax.set_title(title[key]);ax.grid(alpha=.15)
        ax.set(xlabel='Scan time (s)',ylabel='Conditional residual (Hz)')
    axes[0,0].legend(ncol=3)
    fig.suptitle('Same six disputed curved tracks; three joint identity/calibration fits (c = 0)\n'
                 'Includes existing receiver, band, phase and orbital corrections; all three pass original gates')
    fig.tight_layout(rect=(0,0,1,.92));fig.savefig(OUT/'disputed_track_residuals.png',dpi=175);plt.close(fig)


def sky_audit(records,coverage):
    elements=read(SOURCE/'DS23-0268/nominal_elements.json')
    observations={r['observation_id']:r for r in read(SOURCE/'DS23-0268/observations.json')}
    station_path=ROOT/'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json'
    station=read(station_path)
    radio_id=read(SOURCE/'DS23-0268/tracking.json')['source']['radio_id']
    if radio_id not in (station['radio_id'],station['radio_serial']):
        raise ValueError('station authority radio mismatch')
    axes={r['receiver_id']+1:(r['azimuth_deg'],r['elevation_deg'] if r['elevation_deg'] is not None
                            else 90-station['nominal_outward_tilt_deg']) for r in station['receivers']}
    rows=[]
    for name,record in records.items():
        for arm,result in record['arms'].items():
            p,x=replay_proposal(record,arm)
            origin,cutoff=p.scan.receipt['origin_utc_ns'],p.scan.receipt['cutoff_utc_ns']
            if not station['valid_from_utc_ns']<=origin<station['valid_until_utc_ns']:
                raise ValueError('station authority validity mismatch')
            for item in elements.values():
                provenance=item['provenance']
                if max(provenance['element_epoch_utc_ns'],provenance['collected_utc_ns'])>cutoff:
                    raise ValueError('noncausal element in catalogue')
            group=[]
            for accepted in coverage[name][arm]['accepted_rows']:
                track=next(t for t in p.scan.tracks if t['key']==accepted['component'])
                ids=accepted.get('observation_ids',track['observation_ids'])
                for oid in ids:
                    obs=observations[oid]
                    if (obs['receiver'],obs['channel'])!=(track['receiver'],track['channel']):
                        raise ValueError('original observation ownership mismatch')
                    group.append(dict(oid=oid,time=obs['time_s'],rx=obs['receiver'],norad=accepted['norad']))
            if len(group)!=len({g['oid'] for g in group}) or len(group)!=coverage[name][arm]['associated_original_winners']:
                raise ValueError('sky ledger has duplicate or missing original points')
            location=result['endpoint_latlon']
            for norad in sorted({g['norad'] for g in group}):
                selected=[g for g in group if g['norad']==norad]
                catalogue=parse_element_sets('\n'.join(elements[str(norad)]['lines']))
                positions,velocities,usable=ecef_states(catalogue,origin,np.array([g['time'] for g in selected]))
                if not usable.all():raise ValueError('nominal propagation failure')
                az,el,_,_=look_angles(positions[0],velocities[0],geodetic_to_ecef_km(*location,0.),ecef_to_enu_matrix(*location))
                for g,a,e in zip(selected,az,el,strict=True):
                    rows.append(dict(hypothesis=name,arm=arm,observation_id=g['oid'],norad=norad,
                        receiver=g['rx'],time_s=g['time'],azimuth_deg=float(a),elevation_deg=float(e),
                        nominal_off_axis_deg=float(angular_separation(a,e,*axes[g['rx']]))))
    csv_write(OUT/'nominal_sky_points.csv',rows)
    summaries=[]
    for name in records:
        for arm in ('c0','fitted_c'):
            chosen=[r for r in rows if r['hypothesis']==name and r['arm']==arm]
            summaries.append(dict(hypothesis=name,arm=arm,points=len(chosen),
                minimum_elevation_deg=min(r['elevation_deg'] for r in chosen),
                maximum_nominal_off_axis_deg=max(r['nominal_off_axis_deg'] for r in chosen),
                below_horizon=sum(r['elevation_deg']<0 for r in chosen),
                behind_nominal_axis=sum(r['nominal_off_axis_deg']>90 for r in chosen),
                outside_45deg=sum(r['nominal_off_axis_deg']>45 for r in chosen)))
    write(OUT/'nominal_sky_audit.json',dict(summaries=summaries,
        station_authority_sha256=sha(station_path),all_catalogue_epochs_and_collections_causal=True,
        actual_installed_boresights_beamwidth_and_obstructions_unknown=True,
        zero_fitted_phase_and_orbit_corrections=True,altitude_assumed_m=0))
    return summaries


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('figures','calibration'),required=True)
    args=parser.parse_args();OUT.mkdir(exist_ok=True)
    if args.stage=='figures':
        records,coverage,rows=load_models();csv_write(OUT/'identity_comparison.csv',rows)
        compare_plot(rows);residual_plot(records);sky=sky_audit(records,coverage)
        write(OUT/'evidence.json',dict(models={k:sha(PRIOR/v) for k,v in NAMES.items()},
            sky=sky,source_sha256=sha(ROOT/'tools/report_ds23_0268_identity_resolution.py'),
            supplied_GPS_used_only_for_reported_error=True))
        print('Matched identity figures and all-five-model nominal sky audit complete',flush=True)
    else:
        from audit_ds23_algo01_coverage import coverage as measure_coverage
        from ds23_frequency_events import extend_event_associations
        from probe_ds23_0268_radio_calibration import make
        from probe_ds23_frequency_events import summary
        execution=read(CAL/'constrained_execution.json')
        if not execution['all_terminal'] or any('error' in r for r in execution['receipts']):
            raise ValueError('calibration trials incomplete or errored')
        rows=[]
        originals={o['observation_id'] for o in read(SOURCE/'DS23-0268/observations.json')}
        for path in sorted(CAL.glob('*_constrained.json')):
            record=read(path)
            for arm,r in record['arms'].items():
                p,entries=make(record['hypothesis'],arm,np.asarray(r['phase_reference']),record['measurements'])
                x=np.asarray(r['endpoint_east_north_km'])
                fresh=summary(p,x,entries)
                if abs(fresh['negative_twice_elbo']-r['negative_twice_elbo'])>1e-3:
                    raise ValueError('calibration endpoint replay changed')
                extension=extend_event_associations(p,x,fresh['gates'])
                accepted={t['component']:t for t in extension['tracks'] if t['compatible']}
                for t in fresh['gates']['tracks']+fresh['linear_gates']:
                    if t['compatible']:accepted[t['component']]=t
                cov=measure_coverage(list(accepted.values()),p.scan.tracks,originals)
                rows.append(dict(hypothesis=record['hypothesis'],sigma_hz=record['sigma_hz'],arm=arm,
                    paired_valid=record['paired_valid'],position_error_km=position_error(r['endpoint_latlon']),
                    negative_twice_RF_bound=r['negative_twice_elbo'],
                    calibration_residual_hz=r['calibration_residual_hz'][0],
                    minimum_gate_slack=r['minimum_gate_slack'],
                    associated_original_GLRT=cov['associated_original_winners'],
                    associated_original_percent=cov['associated_original_percent'],
                    associated_tracks=cov['associated_tracks']))
        if len(rows)!=12:raise ValueError('expected six matched calibration pairs')
        csv_write(OUT/'calibration_sensitivity.csv',rows)
        write(OUT/'calibration_evaluation.json',dict(rows=rows,exploratory_not_an_identity_probability=True,
            qualification_and_uncertainty_not_calibrated=True,measurement_branch_conditional=True,
            raw_IQ_and_GLRT_errors_not_proven_independent=True))
        fig,axes=plt.subplots(1,2,figsize=(12,4.5))
        for k,sigma in enumerate((100.,300.)):
            original=next(r for r in rows if r['hypothesis']=='original' and r['arm']=='fitted_c' and r['sigma_hz']==sigma)
            for j,name in enumerate(('original','split','whole')):
                r=next(r for r in rows if r['hypothesis']==name and r['arm']=='fitted_c' and r['sigma_hz']==sigma)
                axes[0].bar(4*k+j,r['negative_twice_RF_bound']-original['negative_twice_RF_bound'],color=COLORS[name])
                axes[1].bar(4*k+j,r['calibration_residual_hz'],color=COLORS[name])
        ticks=[0,1,2,4,5,6];labels=['original','split','whole']*2
        for ax in axes:
            ax.set_xticks(ticks,labels);ax.axhline(0,color='black',lw=.7);ax.axvline(3,color='gray',ls=':')
            ax.grid(axis='y',alpha=.15)
        axes[0].set_ylabel('RF bound relative to original; lower is better')
        axes[1].set_ylabel('Measured − fitted RX2/RX1 contrast (Hz)')
        fig.suptitle('Single-window RF calibration sensitivity (fitted c)\n'
            'Left group: 100 Hz uncertainty; right: 300 Hz · identity still not unique')
        fig.tight_layout(rect=(0,0,1,.88));fig.savefig(OUT/'calibration_sensitivity.png',dpi=175);plt.close(fig)
        print(rows,flush=True)


if __name__=='__main__':main()
