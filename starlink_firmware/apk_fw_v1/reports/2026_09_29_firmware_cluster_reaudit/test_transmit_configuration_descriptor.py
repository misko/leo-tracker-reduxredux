from transmit_configuration_descriptor import run


def test_configuration_fields_transfer_and_count_like_transform():
    result = run()
    assert len(result["cases"]) == 942
    assert {c["fields"][1] for c in result["cases"]} == set(range(256))
    by_config = {c["config_word"]: c for c in result["cases"]
                 if c["initial_descriptor"] == 0}
    for bit in range(31, 64):
        assert by_config[1 << bit]["descriptor_word"] == by_config[0]["descriptor_word"]
