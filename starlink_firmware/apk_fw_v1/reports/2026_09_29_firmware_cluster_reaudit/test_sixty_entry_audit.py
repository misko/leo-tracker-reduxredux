from sixty_entry_audit import FIRMWARE, compare, execute, transitions


def test_sixty_entry_boundary_and_no_nonconstant_t_code_identity():
    binary = (FIRMWARE / "catson-bin--phyfw").read_bytes()
    assert execute(binary, 16, 1)["table"] == [0] * 16 + [6] * 44
    assert execute(binary, 60, 0)["table"] == [0] * 60
    assert transitions([0, 0, 1, 1]) == 2
    result = compare()
    assert result["exact_matching_states"] == [0]
    assert min(s["cyclic_transitions"] for s in result["states"][1:]) == 22
