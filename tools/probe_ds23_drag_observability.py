"""Measure a causal Bstar tangent before adding a satellite drag nuisance.

No GPS or position fit: evaluate the published RF endpoints, with the original
observations and phases. A large total Doppler displacement can be an existing
phase/mean-motion direction. Test the independent direction explicitly.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import time

import numpy as np
from sgp4.api import Satrec

from analyze_dsx01_fixed_site import ecef_states
from ds23_direction_projection import project_direction
from ds23_frequency_events import make_event_problem
from fit_s01_69333_tle_parameter import perturb
from probe_ds23_fft_grid_position import setup
from probe_algo03_frame_peak_recovery import SOURCE
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import ROOT, read, write, sha
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.sky.propagation import ElementSetCatalogue, parse_element_sets

OUT = ROOT / 'reports/2026_10_20_ds23_drag_observability'
ARMS = ('c0', 'fitted_c')


def hashes():
    return {str(p.relative_to(ROOT)): sha(p) for p in (
        Path(__file__), ROOT/'tools/ds23_direction_projection.py',
        ROOT/'tools/fit_s01_69333_tle_parameter.py',
        ROOT/'src/leo/analysis/research/orbit_uncertainty.py')}


def prepare():
    OUT.mkdir(exist_ok=True)
    path = OUT/'protocol.json'
    if path.exists():
        protocol = read(path)
        if protocol['source_sha256'] != hashes():
            raise ValueError('sealed sensitivity source changed')
        return protocol
    cohort = read(ROOT/'reports/2026_10_20_ds23_excluded_catalogue/calibration_protocol.json')
    protocol = dict(development_cases=cohort['development_cases'],
        confirmation_cases=cohort['confirmation_cases'], pilot_cases=cohort['pilot_cases'],
        source_sha256=hashes(), workers=24,
        hypothesis='causal Bstar disagreement adds a Doppler direction independent of existing orbital phase and three physical modes',
        Bstar_sigma='max(abs(latest minus previous distinct causal Bstar),1e-5); engineering sensitivity, not a calibrated confidence interval',
        finite_difference_step=1e-5, half_step_control=5e-6,
        minimum_derivative_absolute_tolerance_hz=.001,
        derivative_relative_tolerance=.01,
        tangent_projection='same-family phase, supported mean-motion/inclination/RAAN, and one constant per original fragment',
        projection_rank_rcond=1e-10, noise_primary='original pre-fit pointwise radio sigma',
        noise_secondary='published endpoint power times fitted precision; no new weighting fit',
        conditional_on_published_RF_endpoint=True,
        no_GPS_new_position_fit_new_RF_or_future_TLE=True,
        c_pair='same observations, labels, Bstar scale and step; evaluate each published RF endpoint',
        advance_to_position_test='at least 10% of supported families in EACH cohort have independent noise norm >=1 in BOTH c arms, with finite differences agreeing within 1% or 1mHz',
        inability_to_advance_does_not_validate_existing_covariance=True,
        geometry_projection_is_not_a_posterior_or_identity_test=True,
        full_goal_population=413)
    write(path, protocol)
    return protocol


def run(case):
    protocol = read(OUT/'protocol.json')
    if protocol['source_sha256'] != hashes():
        raise ValueError('sensitivity source changed')
    path = OUT/(case+'.json')
    if path.exists():
        return dict(case=case, cached=True)
    began = time.monotonic()
    scan,node,mask,base,old,signed,binding,model,powers,means,entries = setup(case)
    previous_path = scan.previous_tle_path
    previous_receipt = read(previous_path.with_name('previous_receipt.json'))
    if previous_receipt['catalogue_sha256'] != sha(previous_path):
        raise ValueError('previous causal elements changed')
    cutoff = scan.receipt['cutoff_utc_ns']
    if any(max(r['epoch_utc_ns'],r['collected_utc_ns']) > cutoff
           for r in previous_receipt['sources'].values()):
        raise ValueError('previous catalogue contains future information')
    previous = parse_element_sets(previous_path.read_text())
    by_norad = dict(zip(previous.satellite_numbers, previous.satellites, strict=True))
    shape = (len(base.labels), len(scan.sky['time_s']), 3)
    banks = {h: dict(time_s=scan.sky['time_s'],position_km=np.zeros(shape),velocity_km_s=np.zeros(shape))
             for h in (1e-5,5e-6)}
    metadata = {}
    for local,j in enumerate(base.labels):
        norad = int(scan.norads[j])
        if j not in base.supported or norad not in by_norad:
            continue
        nominal = Satrec.twoline2rv(*scan.elements[str(norad)]['lines'])
        prior = by_norad[norad]
        sigma = max(abs(nominal.bstar-prior.bstar),1e-5)
        if previous_receipt['sources'][str(norad)]['epoch_utc_ns'] >= scan.elements[str(norad)]['provenance']['element_epoch_utc_ns']:
            raise ValueError('previous element is not a distinct older epoch')
        satellites = tuple(perturb(nominal,'bstar',delta) for delta in (1e-5,-1e-5,5e-6,-5e-6))
        catalogue = ElementSetCatalogue((str(norad),)*4,(norad,)*4,satellites)
        pos,vel,good = ecef_states(catalogue,scan.receipt['origin_utc_ns'],scan.sky['time_s'])
        if not good.all():
            raise ValueError('perturbed drag propagation failed')
        for h,k in ((1e-5,0),(5e-6,2)):
            banks[h]['position_km'][local]=(pos[k]-pos[k+1])/(2*h)*sigma
            banks[h]['velocity_km_s'][local]=(vel[k]-vel[k+1])/(2*h)*sigma
        metadata[j] = dict(norad=norad,latest_Bstar=nominal.bstar,previous_Bstar=prior.bstar,
            Bstar_sigma=sigma,TLE_age_hours=(scan.receipt['origin_utc_ns']-
                scan.elements[str(norad)]['provenance']['element_epoch_utc_ns'])/3.6e12)
    results = {}
    for arm in ARMS:
        saved = signed['policy_arms'][arm]
        p=make_event_problem(scan,node,mask,arm,np.asarray(saved['phase_reference']),powers,means,model,[])
        x=np.asarray(saved['endpoint_east_north_km'])
        c=p.calculate(x)
        # The predictive objective changes the total score, not this curved design.
        from ds23_frequency_events import attach_event_predictive
        attach_event_predictive(p,entries,powers)
        delta=p.calculate(x)['negative_twice_elbo']-saved['negative_twice_elbo']
        if abs(delta)>1e-3:
            raise ValueError('published RF endpoint changed')
        modes={h:p.q*paired_frequency_modes(p.sky,b,p.flat_times,p.flat_labels,p.reference,*latlon(x))[:,0]
               for h,b in banks.items()}
        start=p.hardware.shape[1]+p.smooth.shape[1]
        rows=[]
        for j,info in metadata.items():
            local=p.labels.index(j)
            use=mask & (p.flat_labels==local)
            if not use.any():
                continue
            columns=[start+local]
            k=p.supported.index(j)
            columns+=list(range(start+len(p.labels)+3*k,start+len(p.labels)+3*k+3))
            columns+=list(range(c['features'].shape[1]-len(p.members),c['features'].shape[1]))
            existing=c['features'][use][:,columns]
            nominal_noise=p.point_noise[use]
            effective_noise=nominal_noise/np.sqrt(powers[p.noise_groups[use]]*c['noise_precision'][p.noise_groups[use]])
            full=project_direction(modes[1e-5][use],existing,nominal_noise)
            robust=project_direction(modes[1e-5][use],existing,effective_noise)
            half=project_direction(modes[5e-6][use],existing,nominal_noise)
            difference=float(np.max(abs(modes[1e-5][use]-modes[5e-6][use])))
            tolerance=max(.001,.01*float(np.max(abs(modes[1e-5][use]))))
            row=dict(info,points=int(use.sum()),
                nominal_noise_projection=full,effective_noise_projection=robust,
                half_step_independent_noise_norm=half['independent_noise_norm'],
                maximum_finite_difference_discrepancy_hz=difference,
                finite_difference_qualified=difference<=tolerance,
                RF_endpoint_east_north_km=x)
            rows.append(row)
        results[arm]=dict(families=rows,incumbent_RF_replay_difference=delta)
    write(path,dict(case=case,arms=results,source_sha256=hashes(),incumbent_binding=binding,
        previous_catalogue_sha256=sha(previous_path),
        nominal_elements_sha256=sha(SOURCE/case/'nominal_elements.json'),
        seconds=time.monotonic()-began,GPS_used=False,new_position_fit=False))
    receipt=dict(case=case,families=len(metadata),seconds=time.monotonic()-began)
    print(receipt,flush=True)
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=('prepare','pilot','cohort'),required=True)
    stage=parser.parse_args().stage
    protocol=prepare()
    if stage!='prepare':
        cases=(protocol['pilot_cases'] if stage=='pilot' else
               protocol['development_cases']+protocol['confirmation_cases'])
        receipts=[]
        with ProcessPoolExecutor(max_workers=min(24,len(cases))) as pool:
            futures={pool.submit(run,c):c for c in cases}
            for f in as_completed(futures):
                try:
                    receipts.append(f.result())
                except Exception as exc:
                    receipts.append(dict(case=futures[f],error=repr(exc)))
                write(OUT/(stage+'_progress.json'),dict(receipts=receipts,total=len(cases)))
        write(OUT/(stage+'_execution.json'),dict(all_terminal=True,receipts=receipts,
            errors=[r for r in receipts if 'error' in r]))
        print('Terminal',len(receipts),'errors',[r for r in receipts if 'error' in r],flush=True)
