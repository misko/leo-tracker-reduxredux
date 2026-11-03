"""Public passing-peak projection and original-winner grouping checks."""
from dataclasses import replace
from types import SimpleNamespace
import numpy as np
from leo.application.scanner_trajectory import project_scanner_candidates
from leo.application.channel_group_refinement import objective
from leo.cli.shared_fast_position import load_input
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.contracts.regional_position import PositionObservations
from leo.analysis.sequential_group_calibration import fixed_shift_objective
from mixture_model import PeakMixtureObjective


def all_peaks(context,shift):
    job,document,terminal,_=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2').plot_evidence(context.source['job_id'])
    if (job['input_sha256']!=context.source['tracking_input_sha256'] or
        job['terminal']['sha256']!=context.source['terminal_sha256']):
        raise ValueError('Frozen source receipts changed')
    points=sorted(project_scanner_candidates(load_input(document)),
        key=lambda p:(p.support_center_utc_ns,p.source_group_id,p.candidate_rank))
    origin=context.source['first_sample_estimate_utc_ns']
    obs=PositionObservations(tuple(p.candidate_id for p in points),
        np.array([(p.support_center_utc_ns-origin)/1e9 for p in points]),
        np.array([p.measured_cfo_hz for p in points]),np.array([p.actual_rf_hz for p in points]),
        np.array([p.receiver_id for p in points]),np.array([p.channel for p in points]),
        np.array([p.margin for p in points]))
    lookup={key:i for i,key in enumerate(context.observations.window_ids)}
    if set(p.source_group_id for p in points)!=set(lookup):
        raise ValueError('Passing peaks must cover exactly the original winner groups')
    group=np.array([lookup[p.source_group_id] for p in points])
    winners=[]
    for g in range(len(lookup)):
        rows=np.flatnonzero(group==g)
        winners.append(min(rows,key=lambda i:(-points[i].margin,points[i].candidate_rank,points[i].candidate_id)))
    winner=np.asarray(winners)
    for name in ['times_s','measured_hz','rf_hz','receiver','channel','margin']:
        np.testing.assert_array_equal(getattr(obs,name)[winner],getattr(context.observations,name))
    joint=objective(SimpleNamespace(observations=obs),context.bank,context.prior,context.nodes)
    raw=fixed_shift_objective(joint.base,shift)
    model=PeakMixtureObjective(raw,shift,group)
    return replace(context,model=model,full_model=model,observations=obs,
        train_mask=np.ones(len(obs.times_s),bool)),group,winner


def lane_permutation(obs):
    """Fixed within-RX/channel half rotation; diagnostic, not a p-value."""
    measured=obs.measured_hz.copy()
    for rx,ch in sorted(set(zip(obs.receiver,obs.channel))):
        rows=np.flatnonzero((obs.receiver==rx)&(obs.channel==ch))
        measured[rows]=np.roll(measured[rows],max(1,len(rows)//2))
    return replace(obs,measured_hz=measured)
