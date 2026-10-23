import run_followup as f

def test_exact_new_path_only_and_all_parent_ids_preserved():
    result=f.s.read(f.OUT/'results.json');before=f.s.read(f.s.OUT/'DS23-0365.json')
    assert result['removed_entry']['component']==f.KEY
    assert result['remaining_entries']==[e for e in before['entries'] if e['component']!=f.KEY]
    removed=set(result['removed_entry']['observation_ids'])
    for arm,row in result['ablation'].items():
        parent=set(result['original_parent_coverage'][arm]['accepted_observation_ids'])
        assert not removed&parent
        assert row['original_parent_ids_preserved']
        assert parent<=set(row['coverage']['accepted_observation_ids'])
        assert len(row['summary']['history'])==5
        assert row['summary']['qualified']

def test_actual_lag1_threshold_and_residual_lengths():
    result=f.s.read(f.OUT/'results.json')
    for arm,rows in result['path_endpoint_diagnostics'].items():
        for solver,row in rows.items():
            n=row['points'];assert n==40
            assert row['thresholds']['abs_lag1_acf']==4/n**.5
            assert len(row['raw_measured_cfo_hz'])==len(row['raw_prediction_residual_hz'])==n
            stat=abs(row['noise_statistics']['lag1_acf'][0])
            assert (stat>row['thresholds']['abs_lag1_acf'])==(solver=='ordinary')
