"""Confirm the predeclared fixed drift prior after development-only gains.

The curvature-only selector did not qualify. This follow-up prospectively tests
the fixed independent-band alternative, whose parameter value and confirmation
scan identities were frozen before development position errors were reported.
It does not change the original selector or its negative result.
"""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import probe_ds23_band_drift_correlation as inference
from run_algo01_ds23_sample import ROOT,read,write,sha


def main():
    protocol=inference.freeze();evaluation=read(inference.OUT/'development_independent_replay.json')
    old=evaluation['statistics']['incumbent']['fitted_c'];new=evaluation['statistics']['independent_band_drift']['fitted_c']
    if any(new[k]>=old[k] for k in ['mean_km','median_km']):raise ValueError('fixed alternative does not qualify for confirmation')
    workflow=dict(followup_to_negative_RF_selected_development=True,
        candidate='fixed independent band drift covariance, same marginal variance',
        candidate_value_and_confirmation_cases_frozen_before_development_position_errors=True,
        stage_selection_uses_development_errors_only_not_confirmation_errors=True,
        original_RF_selected_confirmation_trigger_did_not_qualify=True,
        no_change_to_inference_or_original_RF_selector=True,
        cases=protocol['confirmation_cases'],development_sha256=sha(inference.OUT/'development_independent_replay.json'),
        original_protocol_sha256=sha(inference.OUT/'protocol.json'),
        source_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_band_drift_correlation.py',
            ROOT/'tools/ds23_band_drift_correlation.py']})
    target=inference.OUT/'fixed_prior_confirmation_workflow.json'
    if target.exists() and read(target)!=workflow:raise ValueError('fixed prior follow-up changed')
    if not target.exists():write(target,workflow)
    rows=[]
    with ProcessPoolExecutor(max_workers=10) as pool:
        for future in as_completed([pool.submit(inference.run,c) for c in protocol['confirmation_cases']]):
            r=future.result();rows.append(r)
            write(inference.OUT/'confirmation_progress.json',dict(terminal=len(rows),total=len(protocol['confirmation_cases'])))
    write(inference.OUT/'confirmation_execution.json',dict(rows=rows,all_terminal=True,
        failures=[r for r in rows if r['status']!='complete'],fixed_prior_followup_workflow_sha256=sha(target)))


if __name__=='__main__':main()
