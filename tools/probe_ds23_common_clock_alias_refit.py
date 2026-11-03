"""Shared-clock replication after training-only native carrier branch search."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from ds23_rf_carrier_alias_grid import AliasBranchWorkspace
import probe_ds23_common_receiver_clock as engine
from inventory_ds23_common_clock import OUT as INVENTORY
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_common_clock_alias_refit'
BULK = Path('/srv/bulk/leo/research/ds23-common-clock-alias-refit-20261021')


def configure():
    engine.OUT = OUT
    engine.BULK = BULK
    engine.JointComponentWorkspace = AliasBranchWorkspace


def main():
    OUT.mkdir(exist_ok=True)
    BULK.mkdir(exist_ok=True)
    inventory = INVENTORY/'inventory.json'
    jobs = [dict(index=k, entry=e) for k, e in enumerate(read(inventory)['selected'])]
    protocol = dict(jobs=jobs, inventory_sha256=sha(inventory), workers=9, per_window_seconds=180,
        source_sha256={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,
            'ds23_rf_carrier_alias_grid.py', 'probe_ds23_common_receiver_clock.py',
            'ds23_common_receiver_clock.py', 'ds23_joint_component_rf.py', 'ds23_training_channel_rf.py']},
        matched_previous_clock_protocol_sha256=sha(ROOT/'reports/2026_10_21_ds23_common_receiver_clock_v2/protocol.json'),
        native_carrier_alias_grid=[-1, 0, 1], joint_two_component_grid_size=9,
        branch_selection='maximum training IQ profile score; same24iterations per branch; no held IQ selection',
        same_frame_masks_RF_seed_clock_models_priors_and_allfold_direction_checks_as_v2=True,
        full_complex_covariance_and_raw_carrier_frame_ambiguity_preserved=True,
        no_GPS_TLE_satellite_ID_or_position_used=True,
        more_RF_search_than_single_branch_control_but_identical_RF_support=True,
        no_absolute_CFO_uncertainty_or_position_improvement_established=True)
    target = OUT/'protocol.json'
    if target.exists() and read(target) != protocol:
        raise ValueError('frozen carrier-branch RF experiment changed')
    if not target.exists():
        write(target, protocol)
    with ProcessPoolExecutor(max_workers=9, initializer=configure) as pool:
        rows = [f.result() for f in as_completed([pool.submit(engine.one, j) for j in jobs])]
    write(OUT/'evaluation.json', dict(rows=sorted(rows, key=lambda r:r['index']), all_terminal=True,
        protocol_sha256=sha(target), conditional_candidates=[r['index'] for r in rows if r.get('conditional_common_clock_candidate')],
        no_position_algorithm_promoted=True))


if __name__ == '__main__':
    main()
