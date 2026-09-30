from tx_sysinfo_ipc import run


def test_sysinfo_ipc_header_and_vectors():
    result = run()
    assert len(result['cases']) == 12
    assert all(sum(c['vector_lengths']) == 944 for c in result['cases'])
