"""Replay phase screening with fractional frame templates and RF information."""

from pathlib import Path
import numpy as np
import probe_ds23_differential_frame_phase as base
from ds23_fractional_differential_phase import extract_fractional_phases
from run_algo01_ds23_sample import ROOT, read, write, sha

OUT = ROOT/'reports/2026_10_21_ds23_fractional_differential_phase'
BULK = Path('/srv/bulk/leo/research/ds23-fractional-differential-phase-20261021')
ORIGINAL_ONE = base.one
LATEST = {}


def extract(*args):
    result = extract_fractional_phases(*args)
    LATEST.clear(); LATEST.update(result)
    return result


def one(item):
    job = item['job']; target = BULK/(job['group']+f"_probe{job['probe']:06d}.json")
    if target.exists(): return read(target)
    result = ORIGINAL_ONE(item)
    if result['status'] == 'complete':
        sigma = LATEST['differential_frequency_sigma_proxy_hz']; d = result['models']['differential']
        best = next(h for h in d['harmonics'] if h['harmonic'] == d['best_harmonic'])
        result.update(differential_frequency_sigma_proxy_hz=sigma,
            within_frame_frequency_covariance_hz2=LATEST['within_frame_frequency_covariance_hz2'],
            phase_correction_in_within_frame_sigma=abs(best['residual_frequency_hz'])/sigma,
            phase_continuity_and_small_RF_correction_candidate=bool(d['candidate_for_independent_replication']
                and abs(best['residual_frequency_hz']) <= 3*sigma),
            conditional_local_Gaussian_frequency_proxy_not_validated_error_distribution=True)
        write(target, result)
    return result


def main():
    OUT.mkdir(exist_ok=True); BULK.mkdir(exist_ok=True)
    workflow = dict(rounded_control_sha256=sha(ROOT/'reports/2026_10_21_ds23_differential_frame_phase_v2/evaluation.json'),
        same_jobs_and_held_frame_phase_controls=True, isolated_frame_interpolation=True,
        original_CFO_timing_rate_conditioned_not_reestimated=True,
        no_RF_or_position_correction_applied=True,
        source_sha256={p.name: sha(p) for p in [Path(__file__), ROOT/'tools/ds23_fractional_differential_phase.py',
            ROOT/'tools/probe_ds23_differential_frame_phase.py', ROOT/'tools/ds23_differential_frame_phase.py']})
    path = OUT/'workflow_protocol.json'
    if path.exists() and read(path) != workflow: raise ValueError('fractional differential workflow changed')
    if not path.exists(): write(path, workflow)
    base.OUT, base.BULK, base.extract_phases, base.one = OUT, BULK, extract, one
    base.main()
    evaluation = read(OUT/'evaluation.json'); rows = [r for r in evaluation['rows'] if r['status'] == 'complete']
    write(OUT/'frequency_consistency_audit.json', dict(
        probes=len(rows), uncorrected_reference_frequencies=True,
        phase_screen_candidates=sum(r['models']['differential']['candidate_for_independent_replication'] for r in rows),
        small_RF_correction_candidates=[dict(case=r['case'], group=r['group'], probe=r['probe'])
            for r in rows if r['phase_continuity_and_small_RF_correction_candidate']],
        median_phase_frequency_sigma=float(np.median([r['differential_frequency_sigma_proxy_hz'] for r in rows])),
        large_phase_corrections_may_be_transmitter_frame_phase_not_carrier_Doppler=True,
        no_localization_gain_claim=True, evaluation_sha256=sha(OUT/'evaluation.json')))


if __name__ == '__main__': main()
