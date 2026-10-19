"""Measure past-TLE state disagreement outside ALGO01's four-mode orbit span."""

import argparse
from pathlib import Path

import numpy as np

from analyze_dsx01_fixed_site import ecef_states
from dsx01_causal_correlation import project_state_difference
from dsx01_structured_joint import eccentricity_bank
from investigate_algo01_ds23_0217 import problem
from run_algo01_ds23_sample import OUT as SOURCE,ROOT,final_scan,read,write,sha
from leo.analysis.research.orbit_phase_geometry import phase_shifted_states
from leo.sky.propagation import parse_element_sets,ElementSetCatalogue


def run(case):
    scan=final_scan(case);record=read(SOURCE/case/'result.json')
    p=problem(scan,record['final_node'],'c0',np.array(record['final_mask'],bool))
    previous=parse_element_sets(scan.previous_tle_path.read_text())
    lookup=dict(zip(previous.satellite_numbers,previous.satellites,strict=True))
    local=[k for k,j in enumerate(p.labels) if j in p.supported and int(scan.norads[j]) in lookup]
    numbers=[int(scan.norads[p.labels[k]]) for k in local]
    cat=ElementSetCatalogue(tuple(map(str,numbers)),tuple(numbers),tuple(lookup[n] for n in numbers))
    times=np.array([0.,150.,300.]);oldp,oldv,good=ecef_states(cat,scan.receipt['origin_utc_ns'],times)
    assert good.all()
    currentp,currentv=phase_shifted_states(p.sky,times,0.)
    plusp,plusv=phase_shifted_states(p.sky,times,.01);minusp,minusv=phase_shifted_states(p.sky,times,-.01)
    up,uv=phase_shifted_states(p.mode_bank,times,0.);up=up.reshape(len(p.labels),3,3,3);uv=uv.reshape(len(p.labels),3,3,3)
    eb,metadata=eccentricity_bank(scan,p.labels,p.supported)
    ep,ev=phase_shifted_states(eb,times,0.);ep=ep.reshape(len(p.labels),2,3,3);ev=ev.reshape(len(p.labels),2,3,3)
    rows=[]
    for a,k in enumerate(local):
        dp,dv=oldp[a]-currentp[k],oldv[a]-currentv[k]
        phasep=(plusp[k]-minusp[k])/.02*p.phase_sigma[k]
        phasev=(plusv[k]-minusv[k])/.02*p.phase_sigma[k]
        fourp=np.concatenate((phasep[None],up[k]));fourv=np.concatenate((phasev[None],uv[k]))
        four=project_state_difference(dp,dv,fourp,fourv)
        six=project_state_difference(dp,dv,np.concatenate((fourp,ep[k])),np.concatenate((fourv,ev[k])))
        rr=dp-np.einsum('k,ktd->td',four['coefficient'],fourp)
        rows.append(dict(norad=int(scan.norads[p.labels[k]]),four_mode=four,six_mode=six,
            missing_position_RMS_m=float(np.sqrt(np.mean(rr*rr))*1000),
            total_position_RMS_m=float(np.sqrt(np.mean(dp*dp))*1000),eccentricity_metadata=metadata[p.labels[k]]))
    out=ROOT/'reports/2026_10_18_ds23_orbit_span';out.mkdir(parents=True,exist_ok=True)
    write(out/(case+'.json'),dict(case=case,rows=rows,GPS_or_radio_used_in_state_projection=False,
        previous_TLE_is_disagreement_proxy_not_truth=True,source_sha256=sha(Path(__file__))))
    for r in rows:print(r['norad'],'outside4',round(r['missing_position_RMS_m'],2),'m',
        'fraction4',round(r['four_mode']['unexplained_fraction'],6),
        'fraction6',round(r['six_mode']['unexplained_fraction'],6),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    run(parser.parse_args().case)
