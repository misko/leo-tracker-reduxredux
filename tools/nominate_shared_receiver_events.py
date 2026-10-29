"""Nominate multi-family receiver events from saved residuals without GPS."""
import argparse
import hashlib
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from leo.analysis.research.shared_receiver_events import step_candidates


def run(args):
    gates=read(args.curved_diagnostics);witnesses=read(args.witness_predictions);source=read(args.witness_source)
    metadata={r['track']['key']:r['track'] for r in source['rows']};results={};grid=np.arange(10.,290.1,2.)
    for arm in ['c0','fitted_c']:
        curves=[dict(t,sigma_hz=150.) for t in gates['variants']['combined'][arm]['tracks']];extra=[]
        for row in witnesses['arms'][arm]['witnesses']:
            track=metadata[row['component']]
            extra.append(dict(row,receiver=track['receiver'],channel=track['channel'],rf_hz=track['rf_hz'],sigma_hz=150.))
        results[arm]={name:step_candidates(rows,grid) for name,rows in [('graph_only',curves),('with_provisional_witnesses',curves+extra)]}
    paths=[args.curved_diagnostics,args.witness_predictions,args.witness_source]
    write(args.output,dict(rows=results,noise_hz=150,prior_sigma_hz=200,event_grid_s=grid,family_support_required=2,
        discovery_only=True,GPS_used=False,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['curved-diagnostics','witness-predictions','witness-source','output']:p.add_argument('--'+k,type=Path,required=True)
    run(p.parse_args())
