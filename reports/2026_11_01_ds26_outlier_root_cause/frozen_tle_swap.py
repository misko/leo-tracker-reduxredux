"""Paired first-post TLE diagnostic with all causal fitted corrections frozen."""
import csv
import numpy as np
from sgp4.api import Satrec
from diagnose import ROOT,INPUT,CASES,ARMS,read,write
from leo.sky.propagation import ElementSetCatalogue
from analyze_dsx01_fixed_site import ecef_states
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from prototype_dsx01_continuous_position import latlon
from leo.analysis.research.retained_track_likelihood import PERIOD

def run(case):
    out=ROOT/case;z=read(INPUT/(case+'.json'));ledger=read(out/'tle-ledger.json');audit=read(out/'audit.json');rows=[]
    for target in read(out/'targets.json'):
        for arm in ARMS:
            rr=[r for r in target['results'] if r['regime']=='causal' and r['model']=='L3_phase' and r['arm']==arm]
            chosen=next((r for r in rr if r['norad']==target['meta']['assigned_norad']),min(rr,key=lambda r:r['score']))
            n=chosen['norad'];post=ledger['later'].get(str(n))
            if post is None:
                rows.append(dict(target=target['index'],arm=arm,norad=n,status='no_first_post_elements'));continue
            t=np.array(target['times_s']);grid=np.arange(-40.,341.)
            cat=ElementSetCatalogue((str(n),),(n,),(Satrec.twoline2rv(*post['lines']),));p,v,ok=ecef_states(cat,z['scan_receipt']['origin_utc_ns'],grid)
            if not ok.all():raise ValueError('first post propagation failed')
            f,e=paired_phase_frequency(dict(time_s=grid,position_km=p,velocity_km_s=v),t,np.zeros(len(t),int),np.array([chosen['phase_s']]),*latlon(audit['arms'][arm]['x']))
            residual=np.array(target['corrected_hz'][arm])+chosen['alias']*PERIOD-target['rf_hz']/11.5e9*f-chosen['bias_hz']-chosen['rate_hz_s']*(t-t.mean())
            refitted=next((r for r in target['results'] if r['regime']=='later' and r['model']=='L3_phase' and r['arm']==arm and r['norad']==n),None)
            rows.append(dict(target=target['index'],arm=arm,norad=n,status='paired',causal_rms_hz=chosen['rms_hz'],
                later_frozen_corrections_rms_hz=float(np.sqrt(np.mean(residual**2))),later_refitted_rms_hz=refitted['rms_hz'] if refitted else None,
                causal_phase_s=chosen['phase_s'],later_refitted_phase_s=refitted['phase_s'] if refitted else None,
                later_epoch_hours_after_scan=(post['element_epoch_utc_ns']-z['scan_receipt']['origin_utc_ns'])/3.6e12,
                times_s=t,later_frozen_residual_hz=residual))
    write(out/'frozen_tle_swap.json',rows)

if __name__=='__main__':
    for case in CASES:run(case)
