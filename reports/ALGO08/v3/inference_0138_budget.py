"""Calculate disjoint savings ceilings from the frozen DS30-0138 profile."""

import gzip
from hashlib import sha256
import json
from math import fsum
from pathlib import Path


MEASUREMENTS = Path(__file__).resolve().parent/'measurements'
FILES = {
    'profile': ('inference-0138-functions.json.gz', '2e956fd46174dc499d04b252eda8616c3873208acfbda5ad08655bc37f1851aa'),
    'verification': ('inference-0138-verification.json', '5c1be77bed683d49df89810efd3f0f71c42816994700e29450722f17b1df58b9'),
    'pair': ('history-risk-0138.json.gz', '8bd0bbd2b6f2d9382f4bb9bd4ac0fdd216a16f38de73cdc2b68b2bb75f9f9b68'),
}


def source(label):
    name, expected = FILES[label]
    path = MEASUREMENTS/name
    data = path.read_bytes()
    if path.suffix == '.gz':
        data = gzip.decompress(data)
    if sha256(data).hexdigest() != expected:
        raise ValueError(f'Unexpected profile source: {name}')
    return json.loads(data)


def function(scope, file, name, *, line=None):
    row, = [r for r in scope['functions'] if Path(r['path']).name == file and r['name'] == name
            and (line is None or r['line'] == line)]
    return row


def totals(profile, verification, pair):
    cold, = profile['cold']
    grid, = profile['standard_evidence']
    rank, = cold['rank_calls']
    assoc = function(cold, 'scan.py', 'association')
    phases = function(cold, 'shared_orbit_phase_fit.py', 'profile_phases')
    reused, = [r for r in phases['callers'] if r['name'] == 'improve' and Path(r['path']).name == 'discovery.py']
    information = function(cold, 'shared_orbit_phase_fit.py', 'phase_information')
    phases_proposed = function(cold, 'shared_orbit_phase_fit.py', 'proposal_phases')
    response_reuse = fsum(row['repeat_cpu_ns'] for row in cold['responses'].values())/1e9
    phases_bound = fsum((reused['inclusive_s'], information['inclusive_s']))
    # Projection and selected-coordinate feature functions are separate calls from phase geometry.
    geometry = [function(grid, file, name) for file, name in (
        ('algo08_curved_design.py', 'direct_features'), ('algo08_curved_design.py', 'selected_design'),
        ('marginal.py', '_phase_geometry'))]
    geometry_cost = fsum(row['inclusive_s'] for row in geometry)
    native_cold = function(cold, 'algo08_posterior_handoff.py', 'run', line=125)
    native_grid = function(grid, 'algo08_posterior_handoff.py', 'run', line=67)
    native_sum = fsum(row['exclusive_s'] for row in (native_cold, native_grid))
    grid_cpu = grid['scope']['cpu_ns']/1e9
    distinct_grid = [native_grid['exclusive_s'], function(grid, 'predictive_linear.py', 'conditional_gaussian')['inclusive_s'],
                     function(grid, 'algo08_posterior_handoff.py', 'whiten')['inclusive_s']]
    if (not all(verification['parity'].values()) or cold['responses'] != verification['responses']
            or assoc['calls'] != 16 or native_grid['calls'] != 356 or phases['calls'] != reused['calls']+information['calls']
            or not 0 <= response_reuse <= assoc['inclusive_s'] <= rank['cpu_ns']/1e9
            or not 0 <= geometry_cost+fsum(distinct_grid) <= grid_cpu):
        raise ValueError('Unexpected stage or nested call accounting')
    required_wall = verification['clock']['elapsed_s']-.5*pair['archive_stock_clock']['elapsed_s']
    return dict(provenance=FILES, both_verified_publications=True, cold_clock=cold['scope'], rank_clock=rank,
                inside_cold_outside_rank_cpu_s=(cold['scope']['cpu_ns']-rank['cpu_ns'])/1e9,
                standard_evidence_clock=grid['scope'], curve_responses=cold['responses'],
                scan_full_association_inclusive_cpu_s=assoc['inclusive_s'],
                original_white_profiles_inclusive_cpu_s=function(cold, 'retained_track_likelihood.py', 'profile')['inclusive_s'],
                cold_phase_profile_direct_repeats=reused, cold_phase_information_inclusive=information,
                same_response_reuse_full_curve_ceiling_cpu_s=response_reuse,
                cold_phase_already_calculated_and_invariant_table_ceiling_cpu_s=phases_bound,
                extended_disjoint_rank_reuse_ceiling_cpu_s=fsum((response_reuse, phases_bound, phases_proposed['inclusive_s'])),
                grid_geometry_kernel_rows=geometry, grid_fixed_phase_geometry_ceiling_cpu_s=geometry_cost,
                grid_upper_left_after_distinct_numeric_portions_cpu_s=grid_cpu-fsum(distinct_grid),
                grid_distinct_numeric_portions_cpu_s=distinct_grid,
                whole_native_posterior_cold_and_evidence_exclusive_cpu_s=native_sum,
                targeted_two_seconds_fraction_whole_association=2/assoc['inclusive_s'],
                targeted_two_seconds_fraction_whole_native=2/native_sum,
                required_wall_saving_from_profiled_worker_to_half_fresh_named=required_wall,
                required_fraction_of_paid_rank_wall_to_half_fresh_named=required_wall/(rank['elapsed_ns']/1e9),
                saved_scopes=verification)


if __name__ == '__main__':
    print(json.dumps(totals(*(source(name) for name in ('profile','verification','pair'))),
                     sort_keys=True, indent=2, allow_nan=False))
