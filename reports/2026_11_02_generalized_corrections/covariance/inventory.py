"""Bounded provenance inventory and orbit-only covariance derivation, no fits."""
import argparse
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from causal_covariance import (POLICY,project_disagreements,sha,shrunk_covariance,validate_and_select)

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
MANIFEST=REPO/'reports/2026_11_02_algo07_top10_outliers/run_manifest.json'
PREVIOUS=REPO/'reports/2026_11_02_family_reliability/population/cases'


def inventory(derive=False):
    manifest=json.loads(MANIFEST.read_text())
    result=[]
    for row in sorted(manifest['rows'],key=lambda r:r['case']):
        z=json.loads(Path(row['input_path']).read_text())
        native=Path(z['native_path'])
        path=native.parent/'causal_phase_history'/(native.name+'.json')
        past=json.loads((PREVIOUS/row['case']/'result.json').read_text())
        family=past.get('selected_family')
        rec=dict(case=row['case'],dataset=row['dataset'],history_exists=path.exists(),
                 selected_family=family,status='unavailable',history_path=str(path),
                 input_path=row['input_path'],input_sha256=sha(row['input_path']))
        try:
            raw=json.loads(path.read_text())
            rec.update(history_sha256=sha(path),raw_satellites=len(raw['past_versions']),
                       raw_version_count=sum(map(len,raw['past_versions'].values())),
                       cutoff_utc_ns=raw['cutoff_utc_ns'],origin_utc_ns=raw['origin_utc_ns'])
            sources={(s['collected_utc_ns'],s['sha256']) for s in raw['sources']}
            cutoff=z['scan_receipt']['cutoff_utc_ns']
            all_rows=[r for versions in raw['past_versions'].values() for r in versions]
            if any(r['epoch']>cutoff or r.get('collected_utc_ns',cutoff+1)>cutoff or
                   (r['collected_utc_ns'],r.get('snapshot_sha256')) not in sources for r in all_rows):
                raise ValueError('Archive availability chronology/source receipt failure')
            nominal_path=native/'nominal_elements.json'
            if raw['latest_elements_sha256']!=sha(nominal_path):
                raise ValueError('Nominal binding failure')
            rec.update(all_history_availability_verified=True,nominal_elements_sha256=sha(nominal_path))
            if family is None:
                rec.update(status='no_RF_target',reason=past['status'])
            else:
                nominal=json.loads(nominal_path.read_text())[str(family)]
                rows,info=validate_and_select(raw,nominal,cutoff,z['scan_receipt']['origin_utc_ns'],family)
                rec.update(info,status='history_supported' if rows else 'history_insufficient')
                if derive and rows:
                    from build_dsx01_orbit_modes import build_modes
                    from analyze_dsx01_fixed_site import ecef_states
                    from sgp4.api import Satrec
                    from leo.sky.propagation import ElementSetCatalogue
                    # Reuse the baseline bank's grid but propagate only this target.
                    with np.load(native/'bank.npz') as bank:
                        times=bank['time_s']
                    cat=ElementSetCatalogue((str(family),),(family,),(Satrec.twoline2rv(*nominal['lines']),))
                    p,v,valid=ecef_states(cat,rec['origin_utc_ns'],times)
                    if not valid.all():raise ValueError('Invalid nominal propagation')
                    receipt=json.loads((native.parent/'causal_prior'/native.name/'receipt.json').read_text())
                    scan=SimpleNamespace(case=native.name,norads=np.array([family]),sky=dict(time_s=times,position_km=p,velocity_km_s=v),
                        elements={str(family):nominal},receipt=receipt,
                        previous_tle_path=native.parent/'causal_prior'/native.name/'previous.tle')
                    bank,mode_metadata=build_modes(scan,[0],[0],'physical')
                    obs=native/'observations.json'
                    ts=np.array([r['time_s'] for r in json.loads(obs.read_text())])
                    projection_times=np.array([ts.min(),(ts.min()+ts.max())/2,ts.max()])
                    a,projection=project_disagreements(scan,0,bank,nominal,rows,projection_times)
                    covariance,details=shrunk_covariance(a)
                    rec.update(projection)
                    rec.update(details,coefficient_covariance=covariance.tolist(),
                               projection_times_s=projection_times.tolist(),mode_metadata=mode_metadata[0],
                               status='ready' if projection['represented_energy_fraction']>=POLICY['minimum_represented_energy_fraction'] else 'projection_unsupported')
        except (ValueError,KeyError,OSError) as exc:
            rec.update(status='invalid_or_missing',reason=str(exc))
        result.append(rec)
    output=dict(policy=POLICY,manifest_sha256=sha(MANIFEST),rows=result,
                counts=dict(Counter(r['status'] for r in result)),
                per_dataset={d:dict(Counter(r['status'] for r in result if r['dataset']==d)) for d in sorted({r['dataset'] for r in result})},
                derivations_are_RF_GPS_free=True,selection='previous frozen generic RF nomination; rechecked in fitting harness')
    target=ROOT/('derived_inventory.json' if derive else 'availability_inventory.json')
    target.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:output[k] for k in ['counts','per_dataset']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--derive',action='store_true')
    inventory(p.parse_args().derive)
