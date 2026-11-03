"""Confirm the unchanged asymmetric prior on 20 separate DS23 recordings."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/'reports/2026_10_20_ds23_skew_phase_validation'


def initialize():
    destination=OUT/'protocol.json'
    if destination.exists():return read(destination)
    (OUT/'qualification').mkdir(parents=True,exist_ok=True)
    (OUT/'position').mkdir(parents=True,exist_ok=True)
    original=ROOT/'reports/2026_10_20_ds23_causal_phase_location_validation/protocol.json'
    cases=read(original)['cases']
    sources=[ROOT/'tools'/name for name in ('ds23_skew_phase_prior.py','ds23_skew_bound.py',
        'ds23_skew_phase_problem.py','probe_ds23_skew_phase_prior.py','probe_ds23_skew_phase_position.py')]
    protocol=dict(cases=cases,original_recording_selection_sha256=sha(original),
        these_are_separate_recordings_not_an_untouched_or_new_location_corpus=True,
        fixed_before_reading_new_skew_position_errors=True,
        exact_same_prior_qualification_and_scalar_optimizer_as_development=True,
        no_parameter_or_gate_changes=True,no_GPS_or_RF_in_prior_qualification=True,
        scalar_symmetric_control_included=True,all_failures_retain_original_ALGO02_and_denominator=True,
        workers=12,source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
        confirmation_requires_lower_mean_and_median_in_both_c_arms_than_original_and_signed_mean=True)
    write(destination,protocol);return protocol


def job(case):
    # Each task runs in a separate worker process. Only artifact destinations
    # differ; the frozen learner and inference functions themselves are reused.
    import probe_ds23_skew_phase_prior as prior
    import probe_ds23_skew_phase_position as position
    prior.OUT=OUT/'qualification'
    position.OUT=OUT/'position';position.QUALIFICATION=prior.OUT
    prior.run_case(case)
    return position.run_case(case)


def main():
    protocol=initialize();results=[]
    with ProcessPoolExecutor(max_workers=12) as executor:
        futures={executor.submit(job,case):case for case in protocol['cases']}
        for future in as_completed(futures):
            try:results.append(future.result())
            except Exception as exc:results.append(dict(case=futures[future],error=repr(exc)))
            write(OUT/'progress.json',dict(completed=len(results),total=len(futures),results=results))
    write(OUT/'execution.json',dict(results=results,all_terminal=True))


if __name__=='__main__':main()
