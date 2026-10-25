"""Compare the forecast state basis with the existing engine, using TLE inputs only."""
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from sgp4.alpha5 import from_alpha5

from causal_joint_prior import physical_basis, stack, write, OUT
from build_dsx01_orbit_modes import build_modes
from leo.analysis.research.orbit_phase_geometry import phase_shifted_states


def main():
    root=Path('/srv/bulk/leo/research/ds25-20261024/DS24-0010')
    bank=np.load(root/'bank.npz')
    scan=SimpleNamespace(case='DS24-0010',
        sky={k:bank[k] for k in ['time_s','position_km','velocity_km_s','phase_sigma_s']},
        norads=bank['norad'],receipt=json.loads((root/'receipt.json').read_text()),
        elements=json.loads((root/'nominal_elements.json').read_text()),previous_tle_path=root/'previous.tle')
    receipts=json.loads((root/'previous_receipt.json').read_text())['sources']
    lines=(root/'previous.tle').read_text().splitlines()
    previous={}
    for index,line in enumerate(lines):
        if line.startswith('1 '):
            number=from_alpha5(line[2:7]);receipt=receipts[str(number)]
            previous[number]=dict(lines=[line,lines[index+1]],epoch=receipt['epoch_utc_ns'],
                collected_utc_ns=receipt['collected_utc_ns'])
    labels=[j for j,n in enumerate(scan.norads) if int(n) in previous][:12]
    modes,_=build_modes(scan,labels,labels,'physical')
    times=np.array([0.,150.,300.])
    mp,mv=phase_shifted_states(modes,times,0.)
    nominal=dict(time_s=scan.sky['time_s'],position_km=scan.sky['position_km'][labels],
        velocity_km_s=scan.sky['velocity_km_s'][labels])
    pp,vp=phase_shifted_states(nominal,times,.01)
    pm,vm=phase_shifted_states(nominal,times,-.01)
    results=[]
    for k,j in enumerate(labels):
        n=int(scan.norads[j]);element=scan.elements[str(n)]
        b=dict(lines=element['lines'],epoch=element['provenance']['element_epoch_utc_ns'],
            collected_utc_ns=element['provenance']['collected_utc_ns'])
        projected=physical_basis(previous[n],b,scan.receipt['origin_utc_ns'])
        native=np.column_stack([stack((pp[k]-pm[k])/.02,(vp[k]-vm[k])/.02),
            *[stack(mp[3*k+mode],mv[3*k+mode]) for mode in range(3)]])
        relative=np.linalg.norm(projected['design']-native,axis=0)/np.linalg.norm(native,axis=0)
        results.append(dict(norad=n,column_relative_difference=relative))
    maximum=float(max(max(r['column_relative_difference']) for r in results))
    write(OUT/'basis_audit.json',dict(case='DS24-0010',rows=results,
        maximum_column_relative_difference=maximum,
        note='Direct SGP4 forecast coordinates versus engine one-second state interpolation; engineering scales and phase units are the same.',
        all_inputs_causal_TLE_bank_and_receipts_only=True,no_RF_GPS_or_position_fit=True))
    print('basis maximum relative difference',maximum,flush=True)


if __name__=='__main__':
    main()
