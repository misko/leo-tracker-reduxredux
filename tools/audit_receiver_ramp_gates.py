"""Replay prototype endpoints and distinguish residual failures from owner gates."""
import argparse
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from diagnose_all_large_tracks import context
from include_curved_family_annotations import configuration
from annotate_track_predictively import prior_means
from ds23_frequency_events import make_event_problem,attach_event_predictive
from probe_ds23_frequency_events import cached
from leo.analysis.research.retained_track_likelihood import profile,whitening
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.orbital_support import requires_multiple_orbital_owners


def run(args):
    results=[];protocol=read(args.ramps/'protocol.json')
    for job in protocol['jobs']:
        tid=job['track_id'];d=context(read(Path(job['inventory'])));base,_=d['problems']['c0']
        for path in sorted((args.ramps/tid).glob('*_target.json')):
            result=read(path)
            if result['paired_valid']:continue
            extras=result['target_entries'];node,keep=configuration(d['node'],d['keep'],base.slices,extras);means,_=prior_means(d,node)
            for arm,v in result['arms'].items():
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],node,keep,arm,np.array(v['phase_reference']),d['powers'],means,d['model'],result['events'],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);cached(p);x=np.array(v['endpoint_east_north_km']);calc=p.calculate(x)
                if abs(calc['negative_twice_elbo']-v['negative_twice_elbo'])>1e-5:raise ValueError('rejection endpoint does not replay')
                state=p.state(x);frequency,elevation=p.conditional_frequency(x)
                gates={g['component']:g for g in v['gates']['tracks']};rows=[]
                for r,i,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
                    t=p.scan.tracks[i];active=p.keep[sl]
                    if not active.any():continue
                    g=gates[t['key']];q=t['rf_hz']/11.5e9
                    y=t['values']-p.scan.hardware(t,state['beta'])-q*p.scan.rx_basis[i]@state['smooth'][t['receiver']-1]
                    terms=profile(y[active],q*frequency[sl][active],*whitening(t['times'][active]))
                    noise=batch_noise_screen(terms['innovations'],t['times'][active]);low=float(elevation[sl][active].min())
                    causes=[]
                    if terms['rms'][0]>450:causes.append('profile_RMS')
                    if abs(terms['bias'][0])>3000:causes.append('profile_bias')
                    if not noise['noise_screen_pass'][0]:causes.append('profile_noise_structure')
                    if not g['conditional_residual_gate']['compatible']:causes.append('conditional_residual')
                    if int(terms['alias'][0])!=alias:causes.append('alias')
                    if low<0:causes.append('elevation')
                    prepass=not causes
                    if prepass and not g['compatible']:
                        if not requires_multiple_orbital_owners(p,r['candidate_index']):raise ValueError('unexplained qualification failure')
                        causes.append('multiple_orbital_owners_required')
                    rows.append(dict(component=t['key'],norad=r['candidate_norad'],receiver=t['receiver'],channel=t['channel'],
                        compatible=g['compatible'],residual_and_geometry_pass=prepass,failures=causes,
                        requires_multiple_owners=requires_multiple_orbital_owners(p,r['candidate_index']),
                        profile_noise={key:float(value[0]) for key,value in noise.items()},conditional=g['conditional_residual_gate'],
                        target=t['key'] in {e['component'] for e in extras}))
                linear=[]
                for entry,sl in zip(d['entries'],getattr(p,'linear_slices',[]),strict=True):
                    track=p.scan.tracks[entry['track_index']]
                    terms=profile(calc['linear_raw_prediction_residual_hz'][sl],np.zeros(len(track['times'])),*p.scan.white[entry['track_index']],bias_sigma=300.)
                    noise=batch_noise_screen(terms['innovations'],track['times']);causes=[]
                    if terms['rms'][0]>450:causes.append('predictive_RMS')
                    if abs(terms['bias'][0])>3000:causes.append('predictive_bias')
                    if int(terms['alias'][0])!=0:causes.append('predictive_alias')
                    if not noise['noise_screen_pass'][0]:causes.append('predictive_noise_structure')
                    if calc['linear_elevation'][sl].min()<0:causes.append('predictive_elevation')
                    linear.append(dict(component=entry['component'],norad=entry['norad'],compatible=not causes,failures=causes,
                        RMS_hz=float(terms['rms'][0]),profile_noise={key:float(value[0]) for key,value in noise.items()}))
                results.append(dict(scan=job['label'],track_id=tid,model=result['model'],arm=arm,source=str(path),rows=rows,linear_rows=linear))
    write(args.output,dict(results=results,no_acceptance_changes=True))
    for r in results:
        if r['arm']=='fitted_c' and r['model']!='original':
            print(r['scan'],r['model'],[(v['component'],v['failures']) for v in r['rows']+r['linear_rows'] if not v['compatible']],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ramps',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
