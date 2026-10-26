"""Read-only checks of subset-dependent candidate sets; no fitting or truth."""
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT=Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
OUT=Path(__file__).resolve().parent
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')


def read(path):return json.loads(path.read_text())


rows=[]
for inventory in read(OUT/'pipeline_invariants.json')['inventory']['cases']:
    case=inventory['case'];low=ROOT/'ch1_4';high=ROOT/'ch5_8'
    a=read(low/case/'algo02_result.json');b=read(high/case/'algo02_result.json')
    ma,mb=(r['hyperparameters_from_pre_RF_TLE_only'] for r in (a,b))
    model_parameters_equal=all(ma[k]==mb[k] for k in ('shrinkage','multiplier','nu'))
    assert model_parameters_equal
    row=dict(case=case,identical_inference_model_parameters=model_parameters_equal,
        identical_forecast_document=inventory['identical_forecast_document'],
        identical_bank=inventory['numerically_identical_orbit_banks'])
    if not row['identical_bank']:
        saved=read(high/'family_cavity/position'/f'{case}.json')
        selected=saved['selected'] if saved['accepted'] else None
        node=selected['node'] if selected else saved['baseline_node']
        entries=selected['entries'] if selected else saved['baseline_entries']
        mask=np.asarray(saved['original_mask'],bool)
        tracks={t['key']:t for t in read(high/case/'tracks.json')}
        active=set();cursor=0
        for record in node['seed']['rows']:
            if not record['active_curvature']:continue
            n=len(tracks[record['component']]['times'])
            if mask[cursor:cursor+n].any():active.add(record['candidate_index'])
            cursor+=n
        assert cursor==len(mask)
        active.update(e['candidate_index'] for e in entries)
        norads=np.load(high/case/'bank.npz')['norad']
        extras=set(inventory['high_only_norads'])
        owned={int(norads[j]) for j in active}
        nominations=read(high/'family_cavity'/f'{case}_nominations.json')
        offered={int(c['norad']) for f in nominations['families'] for c in f['candidates']}
        row.update(high_only_norads=sorted(extras),active_or_predictive_extras=sorted(extras&owned),
            refined_cavity_candidate_extras=sorted(extras&offered),
            low_max_graph_time_s=inventory['low_max_graph_time_s'],
            high_max_graph_time_s=inventory['high_max_graph_time_s'],
            low_candidates=inventory['low_bank_candidates'],high_candidates=inventory['high_bank_candidates'])
        assert not row['active_or_predictive_extras'] and not row['refined_cavity_candidate_extras']
    rows.append(row)

sources=[REPO/'tools'/f for f in ('evaluate_ds23_phase_refreshed.py','evaluate_ds22_merged_tracks.py',
    'evaluate_ds22_public_tracks.py','algo02_scan.py','dsx01_joint_marginal.py',
    'compare_dsx01_retention_localization.py','ds23_frequency_events.py',
    'probe_ds23_frequency_events.py','ds23_predictive_linear.py','probe_ds23_predictive_linear.py',
    'analyze_dsx01_fixed_site.py','run_dsx01_clean_region.py','prototype_dsx01_calibration_modes.py',
    'evaluate_ds23_family_weighting.py','ds23_radio_noise.py','ds23_height_problem.py')]
sources += [ROOT/'filtered_prepare.py',ROOT/'ch1_4/engine/ds24_engine.py',ROOT/'ch5_8/engine/ds24_engine.py',
    REPO/'src/leo/analysis/glrt_frequency_input.py',REPO/'src/leo/analysis/research/continuous_curve_fit.py',
    REPO/'src/leo/analysis/research/shared_orbit_phase_fit.py']
output=dict(all_assertions_passed=True,cases=rows,current_audited_source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    inference_parameters_equal_all_cases=True,no_refit=True,no_truth_input=True)
(OUT/'candidate_differences.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(dict(all_assertions_passed=True,cases=len(rows),different_banks=[r for r in rows if not r['identical_bank']]),indent=2))
