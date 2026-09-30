from initialization_execution import FIRMWARE, execute


def test_connected_initialization_distinguishes_register_and_table_modes():
    binary = (FIRMWARE / "catson-bin--phyfw").read_bytes()
    two, three, four = [execute(binary, mode) for mode in (2, 3, 4)]
    assert two["selected_cgm"] == four["selected_cgm"] != three["selected_cgm"]
    assert two["final_register_writes"]["0x2004"] != four["final_register_writes"]["0x2004"]
    assert two["final_register_writes"]["0x1020"] == three["final_register_writes"]["0x1020"]
    assert [c["role_label"] for c in (two, three, four)] == ["SAT-TX", "SAT-RX", "UT-TRX"]
