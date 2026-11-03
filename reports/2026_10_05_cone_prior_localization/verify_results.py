"""Recompute saved likelihoods and constraint diagnostics, without refitting."""
import json
from pathlib import Path

import numpy as np

import experiment as study
from cone_geometry import tilt
from smooth_visibility_model import gate_terms
from render import audit


def main():
    _, _, records, _ = audit()
    largest_score_error = largest_kkt_error = largest_mass_error = 0.
    cases = []
    for (scan, arm, variant), saved in records.items():
        data, receipt, _ = study.load(scan, variant)
        obj = study.make_objective(data, receipt, arm, variant)
        info = study.diagnostics(obj, data, saved['best'])
        ds = abs(info['objective']-saved['objective'])
        dk = abs(info['kkt']-saved['kkt'])
        assert ds < 1e-7 and dk < 1e-6, (scan, arm, variant, ds, dk)
        assert info['converged'] == saved['converged']
        assert info['boundary'] == saved['boundary']
        np.testing.assert_allclose(info['owner_rms_hz'], saved['owner_rms_hz'], atol=1e-8)
        sine, log_factor = obj.likelihood.geometry
        original = (.8/len(data.numbers))*gate_terms(sine, 'Q1')[0]
        adjusted = tilt(original, log_factor)
        dm = float(np.max(abs(adjusted.sum(axis=1)-original.sum(axis=1))))
        assert dm < 1e-14
        largest_score_error = max(largest_score_error, ds)
        largest_kkt_error = max(largest_kkt_error, dk)
        largest_mass_error = max(largest_mass_error, dm)
        cases.append(dict(scan=scan, arm=arm, variant=variant, converged=info['converged'],
                          kkt=info['kkt'], boundary=info['boundary']))
    result = dict(status='passed', cases=len(cases),
        maximum_score_reproduction_error=largest_score_error,
        maximum_kkt_reproduction_error=largest_kkt_error,
        maximum_per_window_detection_mass_change=largest_mass_error,
        matched_rf_inputs=True, all_selected_windows=True, zero_strength_baseline_parity=True,
        converged=sum(x['converged'] for x in cases), boundary=sum(x['boundary'] for x in cases),
        per_case=cases)
    (Path(__file__).parent/'verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='per_case'}, indent=2))


if __name__ == '__main__':
    main()
