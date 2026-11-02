"""Orbit-only pre-RF support ledger for the immutable prior nominations."""
import argparse
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from age_covariance import POLICY,base,make_covariance,select_pairs,sha

ROOT=Path(__file__).resolve().parent
ROSTER=ROOT.parent/'evaluation/rf_roster.json'


def inventory(derive=False):
    roster=json.loads(ROSTER.read_text());rows=[]
    for record in roster['cases']:
        family=record.get('target_family')
        result=dict(case=record['case'],dataset=record['dataset'],target_family=family,status='no_prior_target')
        if family is None:rows.append(result);continue
        try:
            z=json.loads(Path(record['input_path']).read_text());native=Path(z['native_path'])
            history=native.parent/'causal_phase_history'/(native.name+'.json')
            raw=json.loads(history.read_text());nominal_path=native/'nominal_elements.json'
            nominal=json.loads(nominal_path.read_text())[str(family)]
            timestamps=[v['time_s'] for v in json.loads((native/'observations.json').read_text())]
            mid=(min(timestamps)+max(timestamps))/2
            horizon=(z['scan_receipt']['origin_utc_ns']+round(mid*1e9)-base.tle_epoch(nominal['lines']))/3.6e12
            args=(raw,nominal,z['scan_receipt']['cutoff_utc_ns'],z['scan_receipt']['origin_utc_ns'],family,horizon)
            _,without=select_pairs(*args,require_forecast=False)
            pairs,info=select_pairs(*args)
            result.update(info,history_path=str(history),history_sha256=sha(history),nominal_elements_sha256=sha(nominal_path),
                pair_count_without_historical_forecast_availability=without['pair_count'],
                status='history_eligible' if len(pairs)>=2 else 'insufficient_history',
                primary_history_eligible=len(pairs)>=3,exploratory_history_eligible=len(pairs)>=2,
                selected_pairs=[dict(older_epoch_utc_ns=p['older']['epoch'],newer_epoch_utc_ns=p['newer']['epoch'],
                    older_element_sha256=base.element_sha(p['older']['lines']),newer_element_sha256=base.element_sha(p['newer']['lines']),
                    older_collected_utc_ns=p['older']['collected_utc_ns'],newer_collected_utc_ns=p['newer']['collected_utc_ns'],
                    horizon_hours=p['horizon_hours'],absolute_horizon_error_hours=p['absolute_horizon_error_hours']) for p in pairs])
            if derive and len(pairs)>=2:
                from sgp4.api import Satrec
                from leo.sky.propagation import ElementSetCatalogue
                from analyze_dsx01_fixed_site import ecef_states
                from build_dsx01_orbit_modes import build_modes
                with np.load(native/'bank.npz') as bank:times=bank['time_s']
                cat=ElementSetCatalogue((str(family),),(family,),(Satrec.twoline2rv(*nominal['lines']),))
                p,v,valid=ecef_states(cat,z['scan_receipt']['origin_utc_ns'],times)
                if not valid.all():raise ValueError('Nominal propagation invalid')
                receipt=json.loads((native.parent/'causal_prior'/native.name/'receipt.json').read_text())
                scan=SimpleNamespace(case=native.name,norads=np.array([family]),elements={str(family):nominal},
                    sky=dict(time_s=times,position_km=p,velocity_km_s=v),receipt=receipt,
                    previous_tle_path=native.parent/'causal_prior'/native.name/'previous.tle')
                mode_bank,metadata=build_modes(scan,[0],[0],'physical')
                problem=SimpleNamespace(labels=[0],supported=[0],mode_metadata=metadata,mode_bank=mode_bank)
                covariance,details=make_covariance(scan,problem,z,family)
                result.update(details,status='ready' if covariance is not None else 'projection_fallback')
        except (ValueError,KeyError,OSError) as exc:result.update(status='invalid',reason=str(exc))
        rows.append(result)
    packet=dict(policy=POLICY,roster_path=str(ROSTER),roster_sha256=sha(ROSTER),
        covariance_source_sha256=sha(ROOT/'age_covariance.py'),rows=rows,
        status_counts=dict(Counter(r['status'] for r in rows)),
        pair_count_histogram=dict(Counter(str(r.get('pair_count','no_target')) for r in rows)),
        per_dataset={d:dict(Counter(r['status'] for r in rows if r['dataset']==d)) for d in sorted({r['dataset'] for r in rows})},
        RF_or_GPS_or_position_fit_used=False)
    target=ROOT/('derived_inventory.json' if derive else 'support_inventory.json')
    target.write_text(json.dumps(packet,indent=2,allow_nan=False,default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v))+'\n')
    print(json.dumps({k:packet[k] for k in ['status_counts','pair_count_histogram','per_dataset']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--derive',action='store_true');inventory(p.parse_args().derive)
