"""Frozen ALGO07 science; source provenance is recorded in origin_manifest.json."""
import numpy as np
from sgp4.api import Satrec
from leo.sky.propagation import ElementSetCatalogue
from analyze_dsx01_fixed_site import ecef_states


def bank_for(records,origin):
    nums=np.array(sorted(map(int,records)));grid=np.arange(-40.,341.,1.)
    cat=ElementSetCatalogue(tuple(map(str,nums)),tuple(map(int,nums)),tuple(Satrec.twoline2rv(*records[str(n)]['lines']) for n in nums))
    pos,vel,good=ecef_states(cat,origin,grid);bank=dict(time_s=grid,position_km=pos[good],velocity_km_s=vel[good])
    return nums[good],bank,nums[~good].tolist()
