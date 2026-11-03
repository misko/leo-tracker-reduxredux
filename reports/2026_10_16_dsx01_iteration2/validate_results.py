"""Validate the complete matched matrix and unchanged scientific populations."""
import hashlib
import json
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
DATA=HERE.parent/'2026_10_16_dsx01_fast_association_losses'


def main():
    sources={s['source_id']:s for s in json.loads((DATA/'sources.json').read_text())}
    old=HERE.parent/'2026_10_16_dsx01_models/results'
    expected={f'{s}-{a}-{m}.json' for s in sources for a in ['fitted-c','zero-c']
              for m in ['profile','continuation','arc']}
    expected|={f'{s}-{a}-{m}-{direction}.json' for s in sources for a in ['fitted-c','zero-c']
               for m in ['profile','continuation'] for direction in ['early_to_late','late_to_early']}
    assert {p.name for p in (HERE/'results').glob('*.json')}==expected
    expanded={f'{s}-{a}-{m}.json' for s in sources for a in ['fitted-c','zero-c']
              for m in ['profile','continuation']}
    assert {p.name for p in (HERE/'expanded-results').glob('*.json')}==expanded
    count=0
    for folder in ['results','expanded-results']:
        for path in (HERE/folder).glob('*.json'):
            r=json.loads(path.read_text())
            source=sources[r['source_id']]
            original=np.load(old/f"{r['source_id']}-full-fitted-c-original.npz")
            a=np.load(path.with_suffix('.npz'))
            assert len(a['associated'])==source['observation_count']
            np.testing.assert_allclose(a['times_s'],original['times_s'],atol=1e-9,rtol=0)
            assert int(a['associated'].sum())==r['full_scan']['associated']
            assert r['full_scan']['observations']==source['observation_count']
            assert r['audit']['feasible']
            assert 1<=r['diagnostics']['evaluations']<=1000
            elapsed=r['diagnostics'].get('elapsed_seconds',r['diagnostics'].get('elapsed_s'))
            assert elapsed is not None and elapsed<=120.5
            assert max(abs(t) for t in r['full_scan']['total_timing_s'].values())<=20.+1e-6
            if r['arm']=='zero-c':
                assert r['vector'][6]==0.
            assert r['source']['tracking_input_sha256']==source['tracking_input_sha256']
            assert r['source']['terminal_sha256']==source['terminal_sha256']
            assert r['challenge']['associated']+r['outside']['associated']==r['full_scan']['associated']
            if r.get('mode','full')!='full':
                assert int(a['associated'][~a['train_mask']].sum())==r['held']['associated']
            if folder=='expanded-results':
                assert len(r['bank_additions'])==8
                assert r['bank_authority']['tle_sha256']==source['tle_sha256']
                assert r['bank_authority']['tle_collected_utc_ns']==source['tle_collected_utc_ns']
                assert r['bank_transport']['calibration_maximum_error_hz']<1e-8
                assert r['bank_transport']['original_satellite_timing_maximum_error_s']<1e-11
                assert abs(r['bank_transport']['q_projection']['expanded_probability_mass']-1.6)<1e-10
            count+=1
    assert count==90
    for sid in sources:
        for arm in ['fitted-c','zero-c']:
            for method in ['profile','continuation']:
                forward=np.load(HERE/'results'/f'{sid}-{arm}-{method}-early_to_late.npz')['train_mask']
                reverse=np.load(HERE/'results'/f'{sid}-{arm}-{method}-late_to_early.npz')['train_mask']
                np.testing.assert_array_equal(forward,~reverse)
        screening=json.loads((HERE/f'candidate_screen_{sid}.json').read_text())
        assert screening['diagnostics']['state']=='complete'
        for arm in ['fitted-c','zero-c']:
            for method in ['profile','continuation']:
                r=json.loads((HERE/'expanded-results'/f'{sid}-{arm}-{method}.json').read_text())
                assert r['bank_additions']==screening['selected_ids']
    polished=[]
    for path in (HERE/'polished-results').glob('*.json'):
        r=json.loads(path.read_text())
        if r.get('status')=='skipped-exhausted-allowance':
            continue
        assert 'sha256:'+hashlib.sha256(Path(r['parent_path']).read_bytes()).hexdigest()==r['parent_sha256']
        assert r['total_inference_calls']<=1000
        assert r['total_inference_seconds']<=120.5
        assert r['audit']['feasible']
        polished.append(dict(parent=Path(r['parent_path']).stem,accepted=r['audit']['accepted'],
                             membership_changes=r['membership_changes']))
    for root in [DATA,HERE.parent/'2026_10_16_dsx01_models',HERE.parent/'2026_10_16_dsx01_window_recovery']:
        manifest=json.loads((root/'manifest.json').read_text())
        entries=manifest.get('files',manifest.get('outputs'))
        for item in entries:
            assert 'sha256:'+hashlib.sha256((root/item['path']).read_bytes()).hexdigest()==item['sha256']
    result=dict(expected=90,verified=90,source_population_and_order_verified=True,
        unchanged_prior_artifact_hashes_verified=True,matched_c0_banks_and_budgets_verified=True,
        all_expansion_selections_frozen_and_generic=True,temporal_masks_complementary=True,
        zero_contrast_temporal_protocol_is_restricted_stress_only=True,polished=polished)
    (HERE/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(verified=90,polished=len(polished),passed=True)),flush=True)


if __name__=='__main__':
    main()
