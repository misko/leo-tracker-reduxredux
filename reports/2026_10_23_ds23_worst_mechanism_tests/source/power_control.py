"""Matched 0326 unit-power sensitivity; no GPS-selected adoption."""
from pathlib import Path
import numpy as np
from probe_ds23_worst_association_bottleneck import setup
from probe_ds23_frequency_events import refit
from probe_ds23_synthetic_noise import gate_counts
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import write

OUT=Path(__file__).resolve().parents[1]


def main():
    d=setup('DS23-0326');powers=d['powers'].copy()
    active=np.unique(d['base'].noise_groups[d['keep']]);powers[active]=1.
    pair={a:refit(d['scan'],d['node'],d['keep'],a,powers,d['means'],d['model'],[],d['entries'])
          for a in ('c0','fitted_c')}
    for r in pair.values():r['original_gate_counts']=gate_counts(r)
    write(OUT/'evidence/DS23-0326_unit_power.json',dict(case='DS23-0326',arms=pair,
        paired_qualified=valid(pair),original_powers=d['powers'],trial_powers=powers,
        original_arms=d['arms'],same_points_candidates_aliases_other_priors_budget=True,
        cold_start=[0.,0.],diagnostic_only_no_adoption=True,
        cross_power_absolute_loss_not_a_model_selection_score=True))
    for a,r in pair.items():print(a,r['endpoint_east_north_km'],r['original_gate_counts'],flush=True)


if __name__=='__main__':main()
