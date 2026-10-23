"""RF-only replay of postfit coverage on paths excluded from fitting."""
from pathlib import Path
import hashlib
import signal
import numpy as np
import mechanism as m
from audit_ds23_algo01_coverage import retained_metrics
import evaluate_ds23_phase_refreshed as ext
from run_algo01_ds23_sample import read,write,sha

ROOT=Path(__file__).resolve().parents[1]

def run():
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('180s audit cap')));signal.alarm(180)
    rows=[];hashes={}
    for case in ['DS23-0232','DS23-0365']:
        source=ROOT/'raw'/case/'result.json';saved=read(source);hashes[str(source)]=sha(source)
        parent,kind,fragments,_=m.load(case);full=m.append(parent,fragments)
        reduced=dict(full,entries=saved['remaining_entries'])
        removed_keys=set(saved['excluded_keys']);removed_ids={o for e in saved['excluded_entries'] for o in e['observation_ids']}
        fitids={o for e in reduced['entries'] for o in e['observation_ids']}
        assert not removed_ids.intersection(fitids)
        for arm,summary in saved['refit_arms'].items():
            p=m.exp.paths.build(reduced,kind,arm,summary['phase_reference']);x=np.asarray(summary['endpoint_east_north_km'])
            replay=m.exp.paths.coverage(reduced,kind,arm,summary)
            frozen=saved['policy_final']['coverage'][arm]
            assert replay==frozen
            metrics=retained_metrics(p,x);state=p.state(x);result=p.calculate(x)
            curved=[r for r in metrics['tracks'] if r['compatible']]
            labels=sorted({r['candidate_index'] for r in curved});begin=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)
            supported_groups={(p.scan.tracks[i]['receiver'],int(p.scan.tracks[i]['channel']>4)) for i in p.members if p.scan.tracks[i]['key'] in {r['component'] for r in curved}}
            for entry in saved['excluded_entries']:
                i=entry['track_index'];track=p.scan.tracks[i];ix=p.scan.index[i];candidates=[]
                y=track['values']-p.scan.hardware(track,state['beta'])-track['rf_hz']/11.5e9*p.scan.rx_basis[i]@state['smooth'][track['receiver']-1]
                for j in labels:
                    phase=np.array([state['phases'][j]])
                    if abs(phase[0])>15:continue
                    bank=dict(time_s=p.scan.sky['time_s'],position_km=p.scan.sky['position_km'][[j]],velocity_km_s=p.scan.sky['velocity_km_s'][[j]])
                    f,e=ext.paired_phase_frequency(bank,p.scan.times,np.zeros(len(p.scan.times),int),phase,*ext.latlon(x))
                    local=p.labels.index(j)
                    if j in p.supported:
                        k=p.supported.index(j)
                        modes=dict(time_s=p.mode_bank['time_s'],position_km=p.mode_bank['position_km'][3*local:3*local+3],velocity_km_s=p.mode_bank['velocity_km_s'][3*local:3*local+3])
                        derivative=ext.paired_frequency_modes(bank,modes,p.scan.times,np.zeros(len(p.scan.times),int),phase,*ext.latlon(x))
                        f+=derivative@result['coefficient'][begin+3*k:begin+3*k+3]
                    terms=ext.profile(y,track['rf_hz']/11.5e9*f[ix],*p.scan.white[i]);noise=ext.batch_noise_screen(terms['innovations'],track['times'])
                    gates=dict(rms=bool(terms['rms'][0]<=450),bias=bool(abs(terms['bias'][0])<=3000),noise=bool(noise['noise_screen_pass'][0]),elevation=bool(e[ix].min()>=0),receiver_band_supported=(track['receiver'],int(track['channel']>4)) in supported_groups)
                    candidates.append(dict(norad=int(p.scan.norads[j]),candidate_index=j,phase_s=float(phase[0]),cost=float(terms['cost'][0]),rms_hz=float(terms['rms'][0]),bias_hz=float(terms['bias'][0]),alias=int(terms['alias'][0]),minimum_elevation_deg=float(e[ix].min()),noise={k:np.asarray(v)[0] for k,v in noise.items()},gates=gates,qualified=all(gates.values())))
                candidates.sort(key=lambda c:c['cost']);actual=[r for r in frozen['associations']['tracks'] if set(entry['observation_ids']).intersection(r['observation_ids'])]
                parentids=set(saved['graph_parent']['coverage'][arm]['accepted_observation_ids']);newids=set(frozen['accepted_observation_ids']);entryids=set(entry['observation_ids'])
                best=next((c for c in candidates if c['qualified']),None)
                assert bool(actual)==bool(best)
                if actual:assert actual[0]['norad']==best['norad']
                rows.append(dict(case=case,arm=arm,component=entry['component'],excluded_from_fitting=True,remaining_fit_ID_overlap=len(entryids&fitids),
                    excluded_points=len(entryids),parent_ID_overlap=len(entryids&parentids),coverage_readmitted=len(entryids&newids),
                    parent_IDs_lost=len(parentids-newids),new_coverage_IDs=len(newids-parentids),frozen_coverage_unique_IDs=len(newids),
                    strict_exclusion_ledger_unique_IDs=len(newids-entryids),total_GLRT=frozen['total_GLRT'],
                    frozen_coverage_percent=100*len(newids)/frozen['total_GLRT'],strict_exclusion_coverage_percent=100*len(newids-entryids)/frozen['total_GLRT'],
                    frozen_association=actual,
                    original_family_candidate=next((c for c in candidates if c['norad']==entry['norad']),None),best_qualified=best,candidates=candidates,coverage_exact_replay=True))
    signal.alarm(0)
    sensitivity=[]
    import csv
    for arm in m.ARMS:
        assembled=[r for r in csv.DictReader((ROOT/'tables/per_scan.csv').open()) if r['method']=='one_pass' and r['arm']==arm]
        total=sum(int(r['associated_unique']) for r in assembled);denominator=sum(int(r['total_GLRT']) for r in assembled)
        readmitted=sum(r['coverage_readmitted'] for r in rows if r['arm']==arm)
        sensitivity.append(dict(arm=arm,frozen_unique_IDs=total,strict_exclusion_ledger_unique_IDs=total-readmitted,total_GLRT=denominator,
            frozen_coverage_percent=100*total/denominator,strict_exclusion_coverage_percent=100*(total-readmitted)/denominator,
            delta_percentage_points=-100*readmitted/denominator,positions_unchanged=True,derived_reporting_only=True))
    write(ROOT/'reporting/readmission_audit.json',dict(status='complete',rows=rows,strict_exclusion_sensitivity=sensitivity,shared_remaining_predictive_fit_IDs_across_c_arms=True,
        conclusion='Exclusion removes fitting entries, not scan tracks or coverage candidates. Frozen-calibration extension can independently re-admit an excluded path in either c arm using its own RMS/bias/noise/elevation gates; it does not apply the predictive quadratic gate.0232 fitted_c re-admits9IDs;0232 c0 and0365 both arms do not.',
        validity='Consistent with current implementation; not a permanent exclusion blacklist. Existing postfit extension does not enforce paired linear gates, so full-pipeline whole-path rejection cannot be claimed. Fit masks match across c arms; coverage masks can differ. Strict exclusion sensitivity subtracts readmitted removed IDs from reporting only, leaving positions unchanged; not a new fit or frozen policy.',
        no_GPS_or_future_TLE_no_refit_no_frozen_result_change=True,input_hashes=hashes,
        source_hashes={str(Path(__file__)):sha(Path(__file__)),str(Path(ext.__file__)):sha(Path(ext.__file__)),str(Path(m.exp.paths.__file__)):sha(Path(m.exp.paths.__file__))}))

if __name__=='__main__':run()
