"""Summarize the read-only association checkpoint against final model penalties."""
import json
from collections import Counter
from pathlib import Path
import numpy as np
from leo.analysis.regional_position_score import zero_sum_basis

p=Path(__file__).resolve().parent
a=json.loads((p/'association.json').read_text());d=json.loads((p/'results.json').read_text())
b=d['cases']['near-original-free'];v=np.asarray(a['initial_vector']);relative=zero_sum_basis(b['bank_count'])@v[8:]
counts=Counter(x['catalog_number'] for x in a['selection']['final']['assignments'])
out=dict(mode_count=a['mode_count'],assigned=a['selection']['final']['assigned'],common_timing_s=float(v[7]),initial_v16_relative_penalty=float(.5*np.sum((relative/.15)**2)),satellites=[dict(number=n,initial_relative_s=float(relative[i]),initial_absolute_s=float(v[7]+relative[i]),upstream_assignment_count=counts[n],final_original_relative_s=b['relative_timing_s'][i],final_improved_relative_s=d['cases']['near-improved-free']['relative_timing_s'][i]) for i,n in enumerate(b['bank_numbers'])])
(p/'association_summary.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
