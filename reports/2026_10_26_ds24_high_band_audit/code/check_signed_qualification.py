"""Recompute historical qualification only; no RF, truth, or position fitting.

PYTHONPATH=/tmp/algo03-feasible-deps:src:tools:/srv/bulk/leo/research/ds24-movement-policy-r01/recovery .venv/bin/python /srv/bulk/leo/research/ds24-high-band-audit-20261026/code/check_signed_qualification.py
"""
import json
from pathlib import Path
from ds23_causal_phase_location import qualify

ROOT=Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
rows=[]
for case in ('DS24-0014','DS24-0093'):
    for subset in ('ch1_4','ch5_8'):
        forecast=json.loads((ROOT/subset/'causal_phase_history'/f'{case}_forecast.json').read_text())
        original=json.loads((ROOT/subset/case/'algo02_result.json').read_text())
        result=qualify(forecast['transitions'],forecast['temporal_split_boundary_ns'],
            forecast['prefix_distribution'],original['hyperparameters_from_pre_RF_TLE_only'])
        rows.append(dict(case=case,subset=subset,qualification=result))
print(json.dumps(rows,indent=2))
Path(__file__).with_name('signed_qualification.json').write_text(json.dumps(rows,indent=2)+'\n')
