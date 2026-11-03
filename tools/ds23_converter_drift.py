"""Change only existing receiver-smooth loadings to recorded mixer references.

Loading RMS is matched on the immutable configured target list, independent
of observed point counts, satellite nominations or receiver position.
"""

import copy
import numpy as np


def target_loadings(geometry,law):
    if law not in ('RF','LNB','tuner'):raise ValueError('unknown converter drift law')
    targets=geometry['targets'];rf=np.array([t['rf_center_hz'] for t in targets],float)
    lo=np.array([t['lnb_lo_hz'] for t in targets],float)
    intermediate=np.array([t['if_center_hz'] for t in targets],float)
    if not len(targets) or not np.isfinite(rf).all() or np.any(lo<=0) or np.any(intermediate<=0) or not np.allclose(rf,lo+intermediate,rtol=0,atol=1e-6):
        raise ValueError('positive, consistent recorded mixer targets required')
    scale={'RF':rf,'LNB':lo,'tuner':intermediate}[law]
    normalizer=1/11.5e9 if law=='RF' else float(np.sqrt(np.mean((rf/11.5e9)**2)/np.mean(scale**2)))
    return scale*normalizer,normalizer


def change_scan(scan,geometry,law):
    loads,normalizer=target_loadings(geometry,law)
    by_channel={}
    for target in geometry['targets']:
        by_channel.setdefault(target['channel'],set()).add(target['lnb_lo_hz'])
    if any(len(v)!=1 for v in by_channel.values()):
        raise ValueError('one LNB reference per channel required for original track contract')
    changed=copy.copy(scan);changed.rx_basis=[];ratios=[]
    for track,basis in zip(scan.tracks,scan.rx_basis,strict=True):
        rf=float(track['rf_hz']);lo=float(next(iter(by_channel[track['channel']])))
        if not rf>lo:raise ValueError('track RF is inconsistent with recorded mixer reference')
        physical={'RF':rf,'LNB':lo,'tuner':rf-lo}[law]*normalizer
        ratio=1. if law=='RF' else physical/(rf/11.5e9)
        changed.rx_basis.append(np.asarray(basis).copy()*ratio);ratios.append(ratio)
    return changed,dict(law=law,normalizer=normalizer,per_track_basis_ratios=ratios,
        configured_target_loading_RMS=float(np.sqrt(np.mean(loads**2))),
        configured_target_RF_loading_RMS=float(np.sqrt(np.mean([(t['rf_center_hz']/11.5e9)**2 for t in geometry['targets']]))),
        nuisance_coordinate_count_unchanged=True,orbital_Doppler_RF_scale_unchanged=True)
