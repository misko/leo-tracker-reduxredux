from ablate_ds23_new_family_prediction import ablation_entries


def test_family_ablation_removes_all_owners_of_one_family_and_preserves_other_ids():
    entries=[dict(norad=1,observation_ids=['a']),dict(norad=2,observation_ids=['b']),dict(norad=1,observation_ids=['c'])]
    kept=ablation_entries(entries,1)
    assert kept==entries[1:2]
    assert entries[0]['observation_ids']==['a']
    assert ablation_entries(entries[:1],1)==[]
