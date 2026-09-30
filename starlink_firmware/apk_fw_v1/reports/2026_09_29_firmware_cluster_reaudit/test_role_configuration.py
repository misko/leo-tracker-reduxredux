from role_configuration import FIRMWARE, execute


def test_reciprocal_roles_and_packed_configuration_argument():
    binary = (FIRMWARE / "catson-bin--phyfw").read_bytes()
    sat_tx = execute(binary, "tx", 2, 0, 0, 0)["fields"]
    ut_rx = execute(binary, "rx", 4, 0, 7, 1)["fields"]
    assert sat_tx["0xf0"] == ut_rx["0xf0"] == 3
    assert sat_tx["0xf4"] == ut_rx["0xf4"] == 4
    assert sat_tx["0x104"] == ut_rx["0x104"] == 51
    assert sat_tx["0xfc"] - ut_rx["0xfc"] == 7
    assert ut_rx["0x100"] == 1
    assert [sat_tx["0x48"], ut_rx["0x48"]] == [18, 16]
