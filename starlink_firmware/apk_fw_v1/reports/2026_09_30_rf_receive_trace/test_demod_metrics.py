from demod_metrics import run


def test_demod_metrics_all_snr_codes_and_body_bit_basis():
    result = run()
    assert len(result['cases']) == 2181
    snr = [case['snr'] for case in result['cases'][:2048]]
    assert all(abs(b - a - 1 / 32) < 1e-12 for a, b in zip(snr[:-1], snr[1:], strict=True))
