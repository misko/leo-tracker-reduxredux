from transmit_descriptor_lengths import run


def test_descriptor_lengths_exclude_form_dependent_reserved_suffixes():
    result = run()
    assert len(result["cases"]) == 72
    for case in result["cases"]:
        if case["mode"] == 1:
            assert case["omitted_bytes"] == case["buffer_index"]
        elif case["buffer_index"] == 1:
            assert case["omitted_bytes"] == 2 + case["form"]
        else:
            assert case["omitted_bytes"] == 1
