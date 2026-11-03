from export_ds23_support_audit import support_reasons


def valid():
    return dict(sample_count=50000,receiver_count=2,acquisition=dict(complete=True,
        validity_authority='provider_attested',validity_includes_guard=True,quality_flags=[],
        actual_if_center_hz=1_000_000_000,sample_start=123,sample_end=50123,generation=9))


def test_valid_metadata_is_distinct_from_proof_of_payload_support():
    assert support_reasons(valid())==[]


def test_partial_support_and_flags_are_preserved_as_separate_failures():
    row=valid();row['sample_count']=100
    row['acquisition'].update(complete=False,sample_end=223,quality_flags=['source_counter_regressed'])
    assert set(support_reasons(row))=={'sample_geometry','incomplete','sample_end','quality_flags'}


def test_missing_counter_fields_are_rejected_without_inventing_samples():
    row=valid();row['acquisition'].update(sample_start=None,generation=None)
    assert set(support_reasons(row))=={'sample_start','generation'}
