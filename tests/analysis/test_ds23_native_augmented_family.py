import probe_ds23_native_augmented_family as study
from probe_ds23_native_augmented_family import choose_family


def test_choose_family_uses_new_RF_point_count_and_existing_curved_support_only():
    entries=[dict(candidate_index=9,points=200),dict(candidate_index=2,points=9),
        dict(candidate_index=2,points=18),dict(candidate_index=1,points=13)]
    assert choose_family(entries,{1,2})==2
    assert choose_family(list(reversed(entries)),{1,2})==2
    assert choose_family(entries,set()) is None
    assert choose_family([dict(candidate_index=2,points=13),dict(candidate_index=1,points=13)],{1,2})==1


def test_family_exclusion_adapter_supplies_the_nomination_target(monkeypatch):
    received=[]
    monkeypatch.setattr(study.cavity,'family_data',lambda data,target: received.append((data,target)) or dict(held_ids=['a'],calibration_mask=[False,True]))
    held=study.family_evidence({'context':'original'},7)
    assert received==[({'context':'original'},7)]
    assert held['target']==7 and held['held_ids']==['a'] and held['calibration_mask']==[False,True]
